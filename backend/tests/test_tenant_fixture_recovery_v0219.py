"""v0.2.19 synthetic account-bound provider fixture and recovery tests.

No real Public API is called. Passing results are NOT proof of account
ownership on the real Public platform. All database files on verified tmpfs.
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet
from engine import (
    account_scope, tenant_foundation, identity_auth, tenant_api_gateway,
    tenant_history, tenant_history_details, tenant_monitor_blueprint,
    tenant_worker_boundary, tenant_test_public_binding, tenant_test_recovery,
    tenant_test_binding_rehearsal, tenant_legacy_dependency_audit,
    tenant_route_audit,
)

ROOT=Path(__file__).resolve().parents[2]


class ProviderBindingRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir="/dev/shm")
        self.db=Path(self.temp.name)/"synthetic-bindings.db"
        tenant_foundation.setup(self.db)
        identity_auth.setup(self.db)
        account_scope.setup(self.db)
        tenant_api_gateway.setup(self.db)
        with account_scope._db(self.db) as con:
            tenant_history.prepare(con)
            tenant_history_details.prepare(con)
            con.execute("CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT)")
            con.execute("INSERT INTO settings VALUES('account_id','LEGACY-UNMODIFIED')")
        self.store=tenant_foundation.TenantStore(self.db,
            credential_key=Fernet.generate_key().decode())
        self.auser=self.store.provision_user("A owner","owner")
        self.buser=self.store.provision_user("B owner","owner")
        self.aconn=self.store.add_connection(self.auser,
            "SYNTHETIC-FAKE-NO-REAL-CREDENTIAL-A")
        self.bconn=self.store.add_connection(self.buser,
            "SYNTHETIC-FAKE-NO-REAL-CREDENTIAL-B")
        self.a1=self.store.link_account(self.auser,self.aconn,"FAKE-A1","Alpha 1")
        self.a2=self.store.link_account(self.auser,self.aconn,"FAKE-A2","Alpha 2")
        self.b1=self.store.link_account(self.buser,self.bconn,"FAKE-B1","Beta 1")
        self.store.account_setting(self.auser,self.a1,"watchlist_csv","SPY,QQQ")
        self.store.account_setting(self.auser,self.a2,"watchlist_csv","IWM")
        self.store.account_setting(self.buser,self.b1,"watchlist_csv","AAPL")
        self.planner=tenant_monitor_blueprint.DormantAccountMonitorPlanner(self.db)
        self.boundary=tenant_worker_boundary.DormantWorkerBoundary(self.planner)
        self.recovery=tenant_test_recovery.OfflineRecoveryGate(self.db)
        self.recovery.setup()
        self.fake=tenant_test_public_binding.FakePublicAccountSource({
            self.aconn:("FAKE-A1",),self.bconn:("FAKE-B1",)
        })
        self.adapter=tenant_test_public_binding.ControlledFixtureBinding(
            self.db,self.fake)
        self.runner=tenant_test_binding_rehearsal.IsolatedPublicAccountRehearsal(
            self.boundary,self.adapter,self.recovery)

    def tearDown(self):
        self.temp.cleanup()

    def plan(self):
        return self.boundary.admission(maximum_accounts=3,per_owner_limit=2)

    def legacy(self):
        with sqlite3.connect(self.db) as con:
            return con.execute("SELECT v FROM settings WHERE k='account_id'").fetchone()[0]

    def test_fake_binding_never_proves_real_public_ownership(self):
        a=self.adapter.verify_for(self.auser,self.a1)
        b=self.adapter.verify_for(self.buser,self.b1)
        for ev in (a,b):
            self.assertTrue(ev.fixture_account_matches)
            self.assertTrue(ev.fixture_connection_matches)
            self.assertFalse(ev.real_public_ownership_verified)
            self.assertFalse(ev.broker_credential_used)
            self.assertEqual(ev.provider_network_requests,0)
            self.assertEqual(ev.orders_submitted,0)
        self.assertEqual(self.fake.network_requests,0)
        with self.assertRaises(tenant_test_public_binding.FixtureBindingRejected):
            self.adapter.verify_real_ownership(self.auser,self.a1)
        with self.assertRaises(tenant_test_public_binding.FixtureBindingRejected):
            self.adapter.fetch_real_quotes(self.auser,self.a1)
        with self.assertRaises(tenant_test_public_binding.FixtureBindingRejected):
            self.adapter.submit_order(self.auser,self.a1)
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.adapter.verify_for(self.auser,self.b1)
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.adapter.verify_for(self.buser,self.a1)
        with self.assertRaises(tenant_test_public_binding.FixtureBindingRejected):
            self.adapter.verify_for(self.auser,self.a2)
        self.assertEqual(self.legacy(),"LEGACY-UNMODIFIED")

    def test_one_bad_binding_pauses_only_that_account_without_fake_ownership(self):
        plan=self.plan()
        with self.assertRaises(tenant_test_binding_rehearsal.FixtureRehearsalDenied):
            self.runner.run_once(plan,approval="not approved")
        result=self.runner.run_once(plan,
            approval=tenant_test_binding_rehearsal.APPROVAL)
        self.assertEqual(result.attempted,3)
        self.assertEqual(result.synthetic_cycles,2)
        self.assertEqual(result.failed_bindings,1)
        self.assertEqual(result.paused_accounts,0)
        self.assertEqual(result.unavailable_accounts,0)
        self.assertEqual(result.deferred_accounts,0)
        self.assertFalse(result.real_public_ownership_verified)
        self.assertEqual((result.provider_calls,result.trades_submitted),(0,0))
        self.assertEqual(self.recovery.status(self.auser,self.a2).state,"PAUSED")
        self.assertEqual(self.recovery.status(self.auser,self.a1).state,"NO_FAILURE")
        self.assertEqual(self.recovery.status(self.buser,self.b1).state,"NO_FAILURE")
        with account_scope._db(self.db) as con:
            rows=con.execute("""SELECT user_id,account_id,COUNT(*) AS count
                FROM tenant_observation_cycles
                GROUP BY user_id,account_id""").fetchall()
            self.assertEqual({(r["user_id"],r["account_id"]):r["count"] for r in rows},
                             {(self.auser,self.a1):1,(self.buser,self.b1):1})
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tenant_worker_leases").fetchone()[0],0)
        self.assertEqual(self.legacy(),"LEGACY-UNMODIFIED")

    def test_paused_account_does_not_auto_resume_even_after_fixture_corrected(self):
        plan=self.plan()
        self.runner.run_once(plan,approval=tenant_test_binding_rehearsal.APPROVAL)
        # Correct the test-only mock; still must obtain manual recovery approval.
        corrected=tenant_test_public_binding.FakePublicAccountSource({
            self.aconn:("FAKE-A1","FAKE-A2"),self.bconn:("FAKE-B1",)
        })
        runner=tenant_test_binding_rehearsal.IsolatedPublicAccountRehearsal(
            self.boundary,tenant_test_public_binding.ControlledFixtureBinding(self.db,corrected),
            self.recovery)
        denied=runner.run_once(plan,approval=tenant_test_binding_rehearsal.APPROVAL)
        self.assertEqual((denied.synthetic_cycles,denied.paused_accounts),(2,1))
        state=self.recovery.status(self.auser,self.a2)
        self.assertEqual((state.state,state.revision),("PAUSED",1))
        with self.assertRaises(tenant_test_recovery.OfflineRecoveryDenied):
            self.recovery.review_for_synthetic(self.auser,self.a2,
                revision=1,phrase="wrong")
        with self.assertRaises(tenant_test_recovery.OfflineRecoveryDenied):
            self.recovery.review_for_synthetic(self.auser,self.a2,
                revision=0,phrase="REVIEW SYNTHETIC ACCOUNT ONLY")
        cleared=self.recovery.review_for_synthetic(self.auser,self.a2,
            revision=1,phrase="REVIEW SYNTHETIC ACCOUNT ONLY")
        self.assertEqual(cleared.state,"CLEARED_SYNTHETIC_ONLY")
        self.assertEqual(cleared.revision,2)
        self.assertFalse(cleared.automatic_resume)
        self.assertFalse(cleared.real_public_recheck_passed)
        with self.assertRaises(tenant_test_recovery.OfflineRecoveryDenied):
            self.recovery.review_for_synthetic(self.auser,self.a2,
                revision=1,phrase="REVIEW SYNTHETIC ACCOUNT ONLY")
        final=runner.run_once(plan,approval=tenant_test_binding_rehearsal.APPROVAL)
        self.assertEqual((final.synthetic_cycles,final.paused_accounts,final.failed_bindings),
                         (3,0,0))
        self.assertEqual(self.legacy(),"LEGACY-UNMODIFIED")

    def test_revoked_connection_aborts_only_affected_owner(self):
        plan=self.plan()
        with account_scope._db(self.db) as con:
            con.execute("UPDATE tenant_connections SET revoked_at='2026-11-09' WHERE connection_id=?",
                        (self.aconn,))
        result=self.runner.run_once(plan,approval=tenant_test_binding_rehearsal.APPROVAL)
        self.assertEqual((result.attempted,result.synthetic_cycles,result.unavailable_accounts),
                         (3,1,2))
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.adapter.verify_for(self.auser,self.a1)
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.recovery.status(self.auser,self.a2)
        with account_scope._db(self.db) as con:
            row=con.execute("SELECT account_id FROM tenant_observation_cycles").fetchone()
            self.assertEqual(row["account_id"],self.b1)
        self.assertEqual(self.legacy(),"LEGACY-UNMODIFIED")

    def test_recovery_revision_fencing_and_second_failure(self):
        first=self.recovery.record_failure(self.auser,self.a1,"BINDING_MISMATCH")
        second=self.recovery.record_failure(self.auser,self.a1,"FAKE_PROVIDER_UNAVAILABLE")
        self.assertEqual((first.revision,second.revision),(1,2))
        with self.assertRaises(tenant_test_recovery.OfflineRecoveryDenied):
            self.recovery.review_for_synthetic(self.auser,self.a1,
                revision=1,phrase="REVIEW SYNTHETIC ACCOUNT ONLY")
        self.assertEqual(self.recovery.status(self.auser,self.a1).state,"PAUSED")
        cleared=self.recovery.review_for_synthetic(self.auser,self.a1,
            revision=2,phrase="REVIEW SYNTHETIC ACCOUNT ONLY")
        self.assertEqual(cleared.revision,3)
        self.assertFalse(cleared.live_worker_enabled)
        new=self.recovery.record_failure(self.auser,self.a1,"STALE_ACCOUNT_PLAN")
        self.assertEqual((new.state,new.revision),("PAUSED",4))
        with self.assertRaises(tenant_test_recovery.OfflineRecoveryDenied):
            self.recovery.ensure_test_replay_allowed(self.auser,self.a1)
        self.assertEqual(self.recovery.status(self.buser,self.b1).state,"NO_FAILURE")
        for meth in (self.recovery.resume_real_worker,self.recovery.connect_public,
                     self.recovery.submit_order):
            with self.assertRaises(tenant_test_recovery.OfflineRecoveryDenied):
                meth(self.auser,self.a1)

    def test_no_cross_fixture_database_or_production_use(self):
        with tempfile.TemporaryDirectory() as regular_dir:
            foreign=Path(regular_dir)/"not-memory.db"
            foreign.write_bytes(self.db.read_bytes())
            with self.assertRaises(Exception):
                tenant_test_recovery.OfflineRecoveryGate(foreign)
            with self.assertRaises(Exception):
                tenant_test_public_binding.ControlledFixtureBinding(foreign,self.fake)
        with tempfile.TemporaryDirectory(dir="/dev/shm") as another_dir:
            otherdb=Path(another_dir)/"another-db.sqlite"
            with sqlite3.connect(self.db) as src,sqlite3.connect(otherdb) as dest:
                src.backup(dest)
            other_gate=tenant_test_recovery.OfflineRecoveryGate(otherdb)
            other_gate.setup()
            with self.assertRaises(tenant_test_binding_rehearsal.FixtureRehearsalDenied):
                tenant_test_binding_rehearsal.IsolatedPublicAccountRehearsal(
                    self.boundary,self.adapter,other_gate)

    def test_static_global_dependency_inventory_blocks_cutover(self):
        report=tenant_legacy_dependency_audit.inspect_repo()
        self.assertGreater(report["legacyFlaskDirectSelectedAccountCalls"],5)
        self.assertGreaterEqual(report["legacyWorkerGlobalSelectedAccountCalls"],1)
        self.assertFalse(report["legacyHttpRoutesRefactored"])
        self.assertFalse(report["legacyWorkerRefactored"])
        self.assertFalse(report["realPublicOwnershipVerified"])
        self.assertFalse(report["cutoverReady"])
        live_app=(ROOT/"backend/app.py").read_text()
        live_worker=(ROOT/"backend/engine/automation_worker.py").read_text()
        audit=tenant_route_audit.inspect_sources(live_app,live_worker)
        self.assertFalse(audit["crossAccountProductionCutoverAllowed"])
        for module in (
            "tenant_test_public_binding","tenant_test_recovery",
            "tenant_test_binding_rehearsal","tenant_legacy_dependency_audit",
        ):
            self.assertNotIn(module,live_app)
            self.assertNotIn(module,live_worker)
            with self.assertRaises(tenant_route_audit.ApiBoundaryError):
                tenant_route_audit.inspect_sources(
                    live_app+"\nfrom engine import "+module+"\n",live_worker)
            with self.assertRaises(tenant_route_audit.ApiBoundaryError):
                tenant_route_audit.inspect_sources(
                    live_app,live_worker+"\nfrom engine import "+module+"\n")


if __name__=="__main__":
    unittest.main()
