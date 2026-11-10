"""v0.2.20: mock Public token/list-account transcript and recovery isolation.

All provider replies, account IDs and secret keys here are SYNTHETIC.
No actual provider HTTP, real account access, orders, or production changes.
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet
from engine import (
    tenant_foundation, identity_auth, account_scope, tenant_api_gateway,
    tenant_history, tenant_history_details, tenant_monitor_blueprint,
    tenant_worker_boundary, tenant_test_recovery,
    tenant_public_readonly_preflight as api,
    tenant_public_preflight_batch as batch,
    tenant_route_audit,
)

ROOT=Path(__file__).resolve().parents[2]


def transcript(token,accounts,*,auth_status=200,accounts_status=200):
    return {
        "auth":api.RecordedResponse(auth_status,{"accessToken":token}),
        "accounts":api.RecordedResponse(accounts_status,{"accounts":accounts}),
    }


class PublicRecordedAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir="/dev/shm")
        self.path=Path(self.temp.name)/"public-readonly-test.db"
        tenant_foundation.setup(self.path)
        identity_auth.setup(self.path)
        account_scope.setup(self.path)
        tenant_api_gateway.setup(self.path)
        with account_scope._db(self.path) as con:
            tenant_history.prepare(con)
            tenant_history_details.prepare(con)
            con.execute("CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT)")
            con.execute("INSERT INTO settings VALUES('account_id','LEGACY-DO-NOT-CHANGE')")
        self.key=Fernet.generate_key()
        self.store=tenant_foundation.TenantStore(self.path,credential_key=self.key)
        self.owner_a=self.store.provision_user("Owner A","owner")
        self.owner_b=self.store.provision_user("Owner B","owner")
        self.secret_a="SYNTHETIC-SECRET-FOR-OWNER-A-ONLY"
        self.secret_b="SYNTHETIC-SECRET-FOR-OWNER-B-ONLY"
        self.connection_a=self.store.add_connection(self.owner_a,self.secret_a)
        self.connection_b=self.store.add_connection(self.owner_b,self.secret_b)
        self.account_a=self.store.link_account(self.owner_a,self.connection_a,"PUBLIC-A-ONE","Alpha 1")
        self.account_a2=self.store.link_account(self.owner_a,self.connection_a,"PUBLIC-A-TWO","Alpha 2")
        self.account_b=self.store.link_account(self.owner_b,self.connection_b,"PUBLIC-B-ONE","Beta")
        self.planner=tenant_monitor_blueprint.DormantAccountMonitorPlanner(self.path)
        self.worker=tenant_worker_boundary.DormantWorkerBoundary(self.planner)
        self.recovery=tenant_test_recovery.OfflineRecoveryGate(self.path)
        self.recovery.setup()
        self.records={
            self.secret_a:transcript("SYNTHETIC-TOKEN-A",[
                {"accountId":"PUBLIC-A-ONE","accountType":"BROKERAGE","tradePermissions":"BUY_AND_SELL"}
            ]),
            self.secret_b:transcript("SYNTHETIC-TOKEN-B",[
                {"accountId":"PUBLIC-B-ONE","accountType":"BROKERAGE"}
            ]),
        }
        self.make_preflight()

    def tearDown(self):
        self.temp.cleanup()

    def make_preflight(self,records=None):
        self.transport=api.RecordedPublicTransport(
            self.records if records is None else records)
        self.preflight=api.IsolatedPublicReadOnlyPreflight(
            self.path,self.key,self.transport)
        self.batch=batch.OfflineRecordedPublicBatch(
            self.worker,self.preflight,self.recovery)
        return self.preflight

    def legacy(self):
        with sqlite3.connect(self.path) as con:
            return con.execute("SELECT v FROM settings WHERE k='account_id'").fetchone()[0]

    def test_documented_auth_and_accounts_paths_are_recorded_no_network_or_secret(self):
        result=self.preflight.check(self.owner_a,self.account_a)
        self.assertTrue(result.fake_credential_access_matches)
        self.assertTrue(result.provider_account_list_matched)
        self.assertFalse(result.verified_by_real_public)
        self.assertFalse(result.verified_legal_owner)
        self.assertFalse(result.authorized_for_trading)
        self.assertFalse(result.account_activated)
        self.assertEqual(result.external_network_requests,0)
        self.assertEqual(self.transport.recorded_calls,[
            ("POST",api.AUTH_PATH),("GET",api.ACCOUNTS_PATH)])
        self.assertEqual(self.transport.network_requests,0)
        self.assertNotIn(self.secret_a,repr(result))
        self.assertNotIn("SYNTHETIC-TOKEN-A",repr(result))
        self.assertNotIn(self.secret_a,repr(self.transport.recorded_calls))
        with account_scope._db(self.path) as con:
            row=con.execute("SELECT credential_ciphertext FROM tenant_connections WHERE connection_id=?",
                (self.connection_a,)).fetchone()
            self.assertNotIn(self.secret_a.encode(),row["credential_ciphertext"])
        self.assertEqual(self.legacy(),"LEGACY-DO-NOT-CHANGE")

    def test_no_fake_transcript_can_prove_cross_owner_account(self):
        for uid,aid in ((self.owner_a,self.account_b),(self.owner_b,self.account_a),
                        (self.owner_b,self.account_a2)):
            with self.assertRaises(tenant_foundation.TenantAccessError):
                self.preflight.check(uid,aid)
        with self.assertRaises(api.PublicPreflightDenied) as caught:
            self.preflight.check(self.owner_a,self.account_a2)
        self.assertEqual(caught.exception.code,"ACCOUNT_NOT_ACCESSIBLE")
        self.assertEqual(self.transport.network_requests,0)
        self.assertEqual(self.legacy(),"LEGACY-DO-NOT-CHANGE")

    def test_status_codes_fail_closed_and_never_return_provider_error_body(self):
        cases=((401,200,"AUTH_REJECTED"),(403,200,"AUTH_REJECTED"),
               (429,200,"PROVIDER_RATE_LIMIT"),(503,200,"PROVIDER_UNAVAILABLE"),
               (200,401,"AUTH_REJECTED"),(200,429,"PROVIDER_RATE_LIMIT"),
               (200,500,"PROVIDER_UNAVAILABLE"),(200,418,"BAD_PROVIDER_RESPONSE"))
        for auth_status,accounts_status,expected in cases:
            with self.subTest(auth=auth_status,accounts=accounts_status):
                modified=dict(self.records)
                modified[self.secret_a]=transcript("SYNTHETIC-TOKEN-A",[
                    {"accountId":"PUBLIC-A-ONE"}
                ],auth_status=auth_status,accounts_status=accounts_status)
                checker=self.make_preflight(modified)
                with self.assertRaises(api.PublicPreflightDenied) as caught:
                    checker.check(self.owner_a,self.account_a)
                self.assertEqual(caught.exception.code,expected)
                self.assertNotIn(self.secret_a,str(caught.exception))

    def test_malformed_provider_responses_and_account_mismatch_deny(self):
        malformed=(
            {"accounts":[]},
            {"accounts":[{"accountId":"PUBLIC-A-ONE"},{"accountId":"PUBLIC-A-ONE"}]},
            {"accounts":[{"accountId":123}]},
            {"accounts":[{"accountId":" PUBLIC-A-ONE"}]},
            {"accounts":[{"id":"PUBLIC-A-ONE"}]},
            {"accounts":"PUBLIC-A-ONE"},
            {"accounts":[{"accountId":"PUBLIC-B-ONE"}]},
            {"accounts":[{"accountId":"PUBLIC-A-ONE"}]*26},
        )
        for body in malformed:
            with self.subTest(body=repr(body)[:60]):
                modified=dict(self.records)
                modified[self.secret_a]={
                    "auth":api.RecordedResponse(200,{"accessToken":"SYNTHETIC-TOKEN-A"}),
                    "accounts":api.RecordedResponse(200,body),
                }
                checker=self.make_preflight(modified)
                with self.assertRaises(api.PublicPreflightDenied):
                    checker.check(self.owner_a,self.account_a)
        modified=dict(self.records)
        modified[self.secret_a]={
            "auth":api.RecordedResponse(200,{"accessToken":"actual-secret-or-unexpected-token"}),
            "accounts":api.RecordedResponse(200,{"accounts":[{"accountId":"PUBLIC-A-ONE"}]}),
        }
        checker=self.make_preflight(modified)
        with self.assertRaises(api.PublicPreflightDenied):
            checker.check(self.owner_a,self.account_a)
        self.assertEqual(checker._transport.recorded_calls,[("POST",api.AUTH_PATH)])

    def test_real_credentials_wrong_key_and_network_transport_are_rejected(self):
        with self.assertRaises(TypeError):
            api.IsolatedPublicReadOnlyPreflight(self.path,self.key,object())
        with self.assertRaises(api.PublicPreflightDenied):
            api.IsolatedPublicReadOnlyPreflight(
                self.path,Fernet.generate_key(),self.transport).check(
                self.owner_a,self.account_a)
        with self.assertRaises(api.PublicPreflightDenied):
            self.transport.exchange_access_token(
                "REAL-SECRET-MUST-BE-REFUSED")
        with self.assertRaises(api.PublicPreflightDenied):
            self.transport.list_authenticated_accounts("REAL-ACCESS-TOKEN")
        with self.assertRaises(api.PublicPreflightDenied):
            self.transport.submit_order()
        with self.assertRaises(api.PublicPreflightDenied):
            self.transport.transfer_funds()
        with account_scope._db(self.path) as con:
            con.execute("UPDATE tenant_connections SET credential_ciphertext=? WHERE connection_id=?",
                        (Fernet(self.key).encrypt(b"REAL-NOT-AN-ALLOWED-TEST-SECRET"),self.connection_a))
        with self.assertRaises(api.PublicPreflightDenied) as caught:
            self.preflight.check(self.owner_a,self.account_a)
        self.assertEqual(caught.exception.code,"CREDENTIAL_NOT_SYNTHETIC")

    def test_batch_pauses_one_account_without_affecting_second_owner(self):
        admission=self.worker.admission(maximum_accounts=3,per_owner_limit=2)
        with self.assertRaises(batch.OfflinePreflightDenied):
            self.batch.run_once(admission,approval="wrong")
        report=self.batch.run_once(admission,approval=batch.APPROVAL)
        self.assertEqual((report.attempted,report.matching_synthetic_accounts,
                          report.preflight_failures,report.paused_accounts,
                          report.unavailable_accounts,report.deferred_accounts),
                         (3,2,1,0,0,0))
        self.assertEqual(report.provider_network_requests,0)
        self.assertEqual(report.trades_submitted,0)
        self.assertFalse(report.real_public_account_access_proved)
        self.assertFalse(report.production_database_changed)
        self.assertEqual(self.recovery.status(self.owner_a,self.account_a2).state,"PAUSED")
        self.assertEqual(self.recovery.status(self.owner_a,self.account_a).state,"NO_FAILURE")
        self.assertEqual(self.recovery.status(self.owner_b,self.account_b).state,"NO_FAILURE")
        # Correct the synthetic response but do NOT auto-unpause the account.
        corrected=dict(self.records)
        corrected[self.secret_a]=transcript("SYNTHETIC-TOKEN-A",[
            {"accountId":"PUBLIC-A-ONE"},{"accountId":"PUBLIC-A-TWO"}])
        self.make_preflight(corrected)
        still=self.batch.run_once(admission,approval=batch.APPROVAL)
        self.assertEqual((still.matching_synthetic_accounts,still.paused_accounts),(2,1))
        status=self.recovery.status(self.owner_a,self.account_a2)
        with self.assertRaises(tenant_test_recovery.OfflineRecoveryDenied):
            self.recovery.review_for_synthetic(
                self.owner_a,self.account_a2,revision=0,phrase="REVIEW SYNTHETIC ACCOUNT ONLY")
        clear=self.recovery.review_for_synthetic(
            self.owner_a,self.account_a2,revision=status.revision,
            phrase="REVIEW SYNTHETIC ACCOUNT ONLY")
        self.assertFalse(clear.real_public_recheck_passed)
        final=self.batch.run_once(admission,approval=batch.APPROVAL)
        self.assertEqual((final.matching_synthetic_accounts,final.paused_accounts),(3,0))
        with account_scope._db(self.path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tenant_observation_cycles").fetchone()[0],0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tenant_worker_leases").fetchone()[0],0)
        self.assertEqual(self.legacy(),"LEGACY-DO-NOT-CHANGE")

    def test_revocation_and_production_db_rejection(self):
        admission=self.worker.admission(maximum_accounts=3,per_owner_limit=2)
        with account_scope._db(self.path) as con:
            con.execute("UPDATE tenant_connections SET revoked_at='2026-11-09' WHERE connection_id=?",
                        (self.connection_a,))
        report=self.batch.run_once(admission,approval=batch.APPROVAL)
        self.assertEqual((report.matching_synthetic_accounts,report.unavailable_accounts),(1,2))
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.preflight.check(self.owner_a,self.account_a)
        with tempfile.TemporaryDirectory() as normal:
            another=Path(normal)/"production-like.db"
            with sqlite3.connect(self.path) as src,sqlite3.connect(another) as dst:
                src.backup(dst)
            with self.assertRaises(Exception):
                api.IsolatedPublicReadOnlyPreflight(another,self.key,self.transport)
        self.assertEqual(self.transport.network_requests,0)

    def test_static_guards_block_any_live_wiring(self):
        app=(ROOT/"backend/app.py").read_text()
        worker=(ROOT/"backend/engine/automation_worker.py").read_text()
        audit=tenant_route_audit.inspect_sources(app,worker)
        self.assertFalse(audit["crossAccountProductionCutoverAllowed"])
        self.assertFalse(audit["readOnlyPublicPreflightConnectedToLive"])
        for module in ("tenant_public_readonly_preflight","tenant_public_preflight_batch"):
            self.assertNotIn(module,app)
            self.assertNotIn(module,worker)
            with self.assertRaises(tenant_route_audit.ApiBoundaryError):
                tenant_route_audit.inspect_sources(
                    app+"\nfrom engine import "+module+"\n",worker)
            with self.assertRaises(tenant_route_audit.ApiBoundaryError):
                tenant_route_audit.inspect_sources(
                    app,worker+"\nfrom engine import "+module+"\n")

if __name__=="__main__":
    unittest.main()
