"""v0.2.22: authenticated offline-only consent, fake rotation and safety tests.

All identities/keys are synthetic; DB must be tmpfs. No Public requests.
"""
from __future__ import annotations

import math
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from cryptography.fernet import Fernet

from engine import (
    tenant_foundation,identity_auth,account_scope,tenant_api_gateway,
    tenant_public_offline_consent as consent,
    tenant_public_safety_state as safety,
    tenant_public_synthetic_rotation as rotation,
    tenant_public_connection_readiness as readiness,
    tenant_public_https_wire as wire,
    tenant_route_audit,
)

ROOT=Path(__file__).resolve().parents[2]


class OfflinePublicControlsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir="/dev/shm")
        self.path=Path(self.temp.name)/"fake-public-authorization.sqlite"
        tenant_foundation.setup(self.path)
        identity_auth.setup(self.path)
        account_scope.setup(self.path)
        tenant_api_gateway.setup(self.path)
        with account_scope._db(self.path) as con:
            con.execute("CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT)")
            con.execute("INSERT INTO settings VALUES('account_id','ORIGINAL-UNTOUCHED')")
        self.key=Fernet.generate_key()
        self.store=tenant_foundation.TenantStore(self.path,credential_key=self.key)
        self.ua=self.store.provision_user("Fake Owner A","owner")
        self.ub=self.store.provision_user("Fake Owner B","owner")
        self.secret_a="SYNTHETIC-SECRET-INITIAL-OWNER-A"
        self.secret_b="SYNTHETIC-SECRET-INITIAL-OWNER-B"
        self.conn_a=self.store.add_connection(self.ua,self.secret_a)
        self.conn_b=self.store.add_connection(self.ub,self.secret_b)
        self.a1=self.store.link_account(self.ua,self.conn_a,"PUBLIC-FAKE-A1","A1")
        self.a2=self.store.link_account(self.ua,self.conn_a,"PUBLIC-FAKE-A2","A2")
        self.b1=self.store.link_account(self.ub,self.conn_b,"PUBLIC-FAKE-B1","B1")
        self.auth=identity_auth.IdentityStore(str(self.path))
        self.auth.provision(self.ua,"owner_a","fake-owner-a-passphrase-123456")
        self.auth.provision(self.ub,"owner_b","fake-owner-b-passphrase-123456")
        self.sa=self.auth.authenticate("owner_a","fake-owner-a-passphrase-123456","android-a")
        self.sa2=self.auth.authenticate("owner_a","fake-owner-a-passphrase-123456","android-a2")
        self.sb=self.auth.authenticate("owner_b","fake-owner-b-passphrase-123456","android-b")
        self.now=[float(int(time.time()))]
        self.safety=safety.OfflinePersistentSafety(self.path,clock=lambda:self.now[0])
        self.safety.setup()
        self.consent=consent.OfflineConsentCeremony(
            self.path,self.auth,self.safety,clock=lambda:self.now[0])
        self.consent.setup()
        self.rotation=rotation.OfflineCredentialRotation(
            self.path,self.key,self.auth,self.consent,self.safety)
        self.rotation.setup()
        self.readiness=readiness.OfflineConnectionReadiness(
            self.path,self.auth,self.consent,self.safety)

    def tearDown(self):
        self.temp.cleanup()

    def legacy(self):
        with sqlite3.connect(self.path) as con:
            return con.execute("SELECT v FROM settings WHERE k='account_id'").fetchone()[0]

    def authorize(self,session,account):
        req=self.consent.request(session["token"],session["csrf"],account)
        confirmed=self.consent.confirm(session["token"],session["csrf"],
            req["approvalId"],revision=req["revision"],
            confirmation=consent.CONFIRM_TEXT)
        self.assertFalse(confirmed["livePublicApproved"])
        return req["approvalId"]

    def test_two_step_session_csrf_scope_expiry_and_one_time_confirmation(self):
        draft=self.consent.request(self.sa["token"],self.sa["csrf"],self.a1)
        self.assertEqual(draft["scope"],consent.SCOPE)
        self.assertFalse(draft["livePublicApproved"])
        with self.assertRaises(consent.OfflineConsentDenied):
            self.consent.confirm(self.sa["token"],self.sb["csrf"],
                draft["approvalId"],revision=1,confirmation=consent.CONFIRM_TEXT)
        with self.assertRaises(consent.OfflineConsentDenied):
            self.consent.confirm(self.sa2["token"],self.sa2["csrf"],
                draft["approvalId"],revision=1,confirmation=consent.CONFIRM_TEXT)
        with self.assertRaises(consent.OfflineConsentDenied):
            self.consent.confirm(self.sa["token"],self.sa["csrf"],
                draft["approvalId"],revision=1,confirmation="yes")
        ok=self.consent.confirm(self.sa["token"],self.sa["csrf"],
            draft["approvalId"],revision=1,confirmation=consent.CONFIRM_TEXT)
        self.assertEqual(ok["revision"],2)
        self.assertTrue(self.consent.assert_confirmed(self.sa["token"],self.a1,draft["approvalId"])["offlineConsentVerified"])
        for token,account in ((self.sa2["token"],self.a1),
                              (self.sa["token"],self.a2),
                              (self.sb["token"],self.b1)):
            with self.assertRaises(consent.OfflineConsentDenied):
                self.consent.assert_confirmed(token,account,draft["approvalId"])
        with self.assertRaises(consent.OfflineConsentDenied):
            self.consent.confirm(self.sa["token"],self.sa["csrf"],
                draft["approvalId"],revision=1,confirmation=consent.CONFIRM_TEXT)
        self.now[0]+=consent.EXPIRES_SECONDS+1
        with self.assertRaises(consent.OfflineConsentDenied):
            self.consent.assert_confirmed(self.sa["token"],self.a1,draft["approvalId"])

    def test_nonowner_and_revoked_session_cannot_authorize(self):
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.consent.request(self.sb["token"],self.sb["csrf"],self.a1)
        draft=self.consent.request(self.sa["token"],self.sa["csrf"],self.a1)
        self.auth.revoke(self.sa["token"])
        with self.assertRaises(consent.OfflineConsentDenied):
            self.consent.confirm(self.sa["token"],self.sa["csrf"],
                draft["approvalId"],revision=1,confirmation=consent.CONFIRM_TEXT)
        with self.assertRaises(consent.OfflineConsentDenied):
            self.consent.assert_confirmed(self.sa["token"],self.a1,draft["approvalId"])

    def test_shared_credential_rotation_requires_both_account_approvals(self):
        approval_a1=self.authorize(self.sa,self.a1)
        with self.assertRaises(rotation.SyntheticRotationDenied) as caught:
            self.rotation.rotate_synthetic(
                self.sa["token"],self.sa["csrf"],self.a1,
                approval_ids={self.a1:approval_a1},
                expected_generation=0,
                new_synthetic_secret="SYNTHETIC-REPLACEMENT-OWNER-A-123")
        self.assertEqual(caught.exception.code,"MISSING_ACCOUNT_APPROVAL")
        approval_a2=self.authorize(self.sa,self.a2)
        before=self.store._fernet()
        with account_scope._db(self.path) as con:
            old=con.execute("""SELECT credential_ciphertext
                FROM tenant_connections WHERE connection_id=?""",(self.conn_a,)).fetchone()[0]
            other=con.execute("""SELECT credential_ciphertext
                FROM tenant_connections WHERE connection_id=?""",(self.conn_b,)).fetchone()[0]
        self.assertEqual(before.decrypt(old).decode(),self.secret_a)
        result=self.rotation.rotate_synthetic(
            self.sa["token"],self.sa["csrf"],self.a1,
            approval_ids={self.a1:approval_a1,self.a2:approval_a2},
            expected_generation=0,
            new_synthetic_secret="SYNTHETIC-REPLACEMENT-OWNER-A-123")
        self.assertEqual(result["syntheticGeneration"],1)
        self.assertEqual(result["affectedAccountCount"],2)
        self.assertFalse(result["providerCredentialActuallyRotated"])
        with account_scope._db(self.path) as con:
            changed=con.execute("""SELECT credential_ciphertext FROM tenant_connections
                WHERE connection_id=?""",(self.conn_a,)).fetchone()[0]
            other_after=con.execute("""SELECT credential_ciphertext FROM tenant_connections
                WHERE connection_id=?""",(self.conn_b,)).fetchone()[0]
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tenant_test_rotation_audit").fetchone()[0],1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tenant_test_safety_pauses WHERE paused=1").fetchone()[0],2)
        self.assertNotEqual(changed,old)
        self.assertEqual(self.store._fernet().decrypt(changed).decode(),
                         "SYNTHETIC-REPLACEMENT-OWNER-A-123")
        self.assertEqual(other_after,other)
        for aid,appr in ((self.a1,approval_a1),(self.a2,approval_a2)):
            with self.assertRaises(consent.OfflineConsentDenied):
                self.consent.assert_confirmed(self.sa["token"],aid,appr)
            with self.assertRaises(safety.SafetyGateDenied):
                self.safety.require_ready(self.ua,aid)
        self.assertTrue(self.safety.require_ready(self.ub,self.b1))
        self.assertEqual(self.legacy(),"ORIGINAL-UNTOUCHED")

    def test_stale_generation_duplicate_secret_and_wrong_key_fail_closed(self):
        approvals={self.a1:self.authorize(self.sa,self.a1),
                   self.a2:self.authorize(self.sa,self.a2)}
        for expected,new_secret in (
            (1,"SYNTHETIC-NEW-SOMETHING-12345"),
            (0,self.secret_a),
            (0,"REAL-PUBLIC-TOKEN-NO-GO"),
        ):
            with self.assertRaises(rotation.SyntheticRotationDenied):
                self.rotation.rotate_synthetic(self.sa["token"],self.sa["csrf"],
                    self.a1,approval_ids=approvals,
                    expected_generation=expected,new_synthetic_secret=new_secret)
        wrong=rotation.OfflineCredentialRotation(
            self.path,Fernet.generate_key(),self.auth,self.consent,self.safety)
        with self.assertRaises(rotation.SyntheticRotationDenied):
            wrong.rotate_synthetic(self.sa["token"],self.sa["csrf"],
                self.a1,approval_ids=approvals,expected_generation=0,
                new_synthetic_secret="SYNTHETIC-NEW-SOMETHING-12345")
        self.assertEqual(self.rotation.generation(self.sa["token"],self.a1),0)
        with account_scope._db(self.path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tenant_test_rotation_audit").fetchone()[0],0)

    def test_atomic_budget_shared_between_controller_instances_and_reset(self):
        self.safety.acquire_simulated(self.ua,self.a1)
        second=safety.OfflinePersistentSafety(self.path,clock=lambda:self.now[0])
        second.acquire_simulated(self.ua,self.a1)
        with self.assertRaises(safety.SafetyGateDenied) as caught:
            second.acquire_simulated(self.ua,self.a1)
        self.assertEqual(caught.exception.code,"BUDGET_EXHAUSTED")
        self.safety.acquire_simulated(self.ua,self.a2)
        self.safety.acquire_simulated(self.ub,self.b1)
        self.now[0]+=61
        second.acquire_simulated(self.ua,self.a1)
        self.assertEqual(self.legacy(),"ORIGINAL-UNTOUCHED")

    def test_global_budget_and_clock_regression_fail_closed(self):
        # Five different eligible accounts x two requests each = global cap.
        extra=[]
        for i in range(3):
            extra.append(self.store.link_account(self.ua,self.conn_a,
                "SYNTHETIC-ADDITIONAL-"+str(i),"Extra "+str(i)))
        accounts=[(self.ua,self.a1),(self.ua,self.a2),(self.ub,self.b1)]
        accounts.extend((self.ua,a) for a in extra)
        for pair in accounts[:5]:
            self.safety.acquire_simulated(*pair)
            self.safety.acquire_simulated(*pair)
        with self.assertRaises(safety.SafetyGateDenied) as caught:
            self.safety.acquire_simulated(*accounts[5])
        self.assertEqual(caught.exception.code,"BUDGET_EXHAUSTED")
        self.now[0]-=5
        with self.assertRaises(safety.SafetyGateDenied) as caught:
            self.safety.acquire_simulated(*accounts[5])
        self.assertEqual(caught.exception.code,"CLOCK_INVALID")
        self.now[0]=float("nan")
        with self.assertRaises(safety.SafetyGateDenied):
            self.safety.acquire_simulated(*accounts[5])

    def test_emergency_stop_persists_reinitialization_and_never_resets(self):
        self.assertFalse(self.safety.is_stopped())
        self.safety.emergency_stop()
        fresh=safety.OfflinePersistentSafety(self.path)
        fresh.setup()
        self.assertTrue(fresh.is_stopped())
        for action in (
            lambda:fresh.acquire_simulated(self.ua,self.a1),
            lambda:fresh.require_ready(self.ua,self.a1),
            lambda:self.consent.request(self.sa["token"],self.sa["csrf"],self.a1),
            lambda:self.rotation.rotate_synthetic(
                self.sa["token"],self.sa["csrf"],self.a1,
                approval_ids={},expected_generation=0,
                new_synthetic_secret="SYNTHETIC-NEW-TEST-SECRET-123"),
        ):
            with self.assertRaises((safety.SafetyGateDenied,
                                    rotation.SyntheticRotationDenied)):
                action()
        self.assertTrue(fresh.is_stopped())
        self.assertEqual(self.legacy(),"ORIGINAL-UNTOUCHED")

    def test_readiness_report_never_authorizes_real_account_or_multiowner(self):
        approval=self.authorize(self.sa,self.a1)
        report=self.readiness.assess(self.sa["token"],self.a1,approval)
        self.assertTrue(report.offline_consent_valid)
        self.assertEqual(report.active_distinct_owners,2)
        self.assertTrue(report.external_terms_review_required)
        self.assertFalse(report.real_public_connection_ready)
        self.assertFalse(report.actual_public_network_authorized)
        self.assertFalse(report.legal_owner_verified)
        self.assertFalse(report.persistent_production_kill_switch_available)
        self.assertFalse(report.production_api_account_isolated)
        self.assertFalse(report.production_worker_account_isolated)
        self.assertFalse(report.trading_or_funds_enabled)
        self.assertFalse(wire.NETWORK_ENABLED)
        with self.assertRaises(PermissionError):
            self.readiness.enable_public(self.sa["token"],self.a1)
        with self.assertRaises(consent.OfflineConsentDenied):
            self.readiness.assess(self.sb["token"],self.a1,approval)

    def test_revoked_connection_and_disabled_user_deny_all_operations(self):
        self.authorize(self.sa,self.a1)
        with account_scope._db(self.path) as con:
            con.execute("UPDATE tenant_connections SET revoked_at='2026-11-09' WHERE connection_id=?",
                        (self.conn_a,))
        for action in (
            lambda:self.safety.acquire_simulated(self.ua,self.a1),
            lambda:self.consent.request(self.sa["token"],self.sa["csrf"],self.a1),
            lambda:self.rotation.generation(self.sa["token"],self.a1),
        ):
            with self.assertRaises(tenant_foundation.TenantAccessError):
                action()
        self.assertTrue(self.safety.require_ready(self.ub,self.b1))
        with account_scope._db(self.path) as con:
            con.execute("UPDATE tenant_users SET disabled_at='2026-11-09' WHERE user_id=?",
                        (self.ub,))
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.safety.require_ready(self.ub,self.b1)

    def test_dormant_modules_cannot_be_wired_into_live_api_or_worker(self):
        app=(ROOT/"backend/app.py").read_text()
        worker=(ROOT/"backend/engine/automation_worker.py").read_text()
        audited=tenant_route_audit.inspect_sources(app,worker)
        self.assertFalse(audited["crossAccountProductionCutoverAllowed"])
        self.assertFalse(audited["publicSafetyAndConsentActiveInProduction"])
        for module in ("tenant_public_safety_state","tenant_public_offline_consent",
                       "tenant_public_synthetic_rotation","tenant_public_connection_readiness"):
            self.assertNotIn(module,app)
            self.assertNotIn(module,worker)
            with self.assertRaises(tenant_route_audit.ApiBoundaryError):
                tenant_route_audit.inspect_sources(app+"\nfrom engine import "+module+"\n",worker)
            with self.assertRaises(tenant_route_audit.ApiBoundaryError):
                tenant_route_audit.inspect_sources(app,worker+"\nfrom engine import "+module+"\n")


if __name__=="__main__":
    unittest.main()
