"""v0.2.16: session-local account choice and offline account worker isolation."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet

from engine import (
    account_scope, identity_auth, tenant_api_gateway, tenant_foundation,
    tenant_history, tenant_history_details, tenant_monitor_blueprint,
)

ROOT=Path(__file__).resolve().parents[2]


class AccountSessionIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir="/dev/shm")
        self.path=Path(self.temp.name)/"synthetic-tenant.db"
        tenant_foundation.setup(str(self.path))
        identity_auth.setup(str(self.path))
        account_scope.setup(str(self.path))
        tenant_api_gateway.setup(str(self.path))
        with account_scope._db(self.path) as con:
            tenant_history.prepare(con)
            tenant_history_details.prepare(con)
            # The global selected account is intentionally independent.
            con.execute("CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT)")
            con.execute("INSERT INTO settings VALUES('account_id','LEGACY-UNCHANGED')")
        self.store=tenant_foundation.TenantStore(
            self.path,credential_key=Fernet.generate_key().decode())
        self.owner=self.store.provision_user("Owner A","owner")
        self.another=self.store.provision_user("Owner B","owner")
        self.ca=self.store.add_connection(self.owner,"fake-synthetic-Public-credential-for-A-1")
        self.cb=self.store.add_connection(self.another,"fake-synthetic-Public-credential-for-B-1")
        self.aa=self.store.link_account(self.owner,self.ca,"Public-A1","Primary account")
        self.a2=self.store.link_account(self.owner,self.ca,"Public-A2","Secondary account")
        self.bb=self.store.link_account(self.another,self.cb,"Public-B1","Other owner")
        self.auth=identity_auth.IdentityStore(str(self.path))
        self.auth.provision(self.owner,"owner_a","correct-horse-battery-staple-A")
        self.auth.provision(self.another,"owner_b","correct-horse-battery-staple-B")
        a=self.auth.authenticate("owner_a","correct-horse-battery-staple-A","android-A")
        b=self.auth.authenticate("owner_a","correct-horse-battery-staple-A","android-B")
        c=self.auth.authenticate("owner_b","correct-horse-battery-staple-B","android-C")
        self.a,self.b,self.c=a,b,c
        self.api=tenant_api_gateway.DormantAccountGateway(self.path,self.auth)
        self.planner=tenant_monitor_blueprint.DormantAccountMonitorPlanner(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def _legacy(self):
        with sqlite3.connect(self.path) as con:
            return con.execute(
                "SELECT v FROM settings WHERE k='account_id'").fetchone()[0]

    def test_independent_selection_per_session_and_owner(self):
        self.assertIsNone(self.api.selected_account(self.a["token"]))
        self.assertIsNone(self.api.selected_account(self.b["token"]))
        self.api.select_account(self.a["token"],self.a["csrf"],self.aa)
        self.api.select_account(self.b["token"],self.b["csrf"],self.a2)
        self.api.select_account(self.c["token"],self.c["csrf"],self.bb)
        self.assertEqual(self.api.selected_account(self.a["token"]),self.aa)
        self.assertEqual(self.api.selected_account(self.b["token"]),self.a2)
        self.assertEqual(self.api.selected_account(self.c["token"]),self.bb)
        self.assertEqual(self._legacy(),"LEGACY-UNCHANGED")
        self.assertEqual(self.api.selected_summary(self.a["token"])["account"]["id"],self.aa)
        self.assertEqual(self.api.selected_summary(self.b["token"])["account"]["id"],self.a2)
        self.assertEqual(self.api.selected_history_summary(self.a["token"])["referenceCount"],0)
        self.assertEqual(len(self.api.list_accounts(self.a["token"])),2)
        self.assertEqual(len(self.api.list_accounts(self.c["token"])),1)

    def test_cross_owner_selection_and_guessed_accounts_denied(self):
        for token,csrf,bad in ((self.a["token"],self.a["csrf"],self.bb),
                               (self.c["token"],self.c["csrf"],self.aa),
                               (self.b["token"],self.b["csrf"],"fabricated-uuid")):
            with self.subTest(bad=bad):
                with self.assertRaises(tenant_foundation.TenantAccessError):
                    self.api.select_account(token,csrf,bad)
                with self.assertRaises(tenant_foundation.TenantAccessError):
                    self.api.account_summary(token,bad)
                with self.assertRaises(tenant_foundation.TenantAccessError):
                    self.api.history_summary(token,bad)
                with self.assertRaises(tenant_foundation.TenantAccessError):
                    self.api.details_summary(token,bad)
                with self.assertRaises(tenant_foundation.TenantAccessError):
                    self.api.page_history(token,bad)
        self.assertIsNone(self.api.selected_account(self.a["token"]))
        self.assertEqual(self._legacy(),"LEGACY-UNCHANGED")

    def test_identity_csrf_token_validation_and_session_revocation(self):
        for csrf in (None,"bad-csrf",self.c["csrf"]):
            with self.assertRaises(tenant_api_gateway.AccountSelectionError):
                self.api.select_account(self.a["token"],csrf,self.aa)
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.api.select_account(self.c["token"],self.a["csrf"],self.bb)
        self.api.select_account(self.a["token"],self.a["csrf"],self.aa)
        self.api.select_account(self.b["token"],self.b["csrf"],self.a2)
        self.auth.revoke(self.a["token"])
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.api.selected_account(self.a["token"])
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.api.selected_summary(self.a["token"])
        # Revoking A's token has no effect on B's authenticated phone.
        self.assertEqual(self.api.selected_account(self.b["token"]),self.a2)
        self.auth.revoke_all(self.owner)
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.api.selected_account(self.b["token"])
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute("""SELECT COUNT(*) FROM
                tenant_session_account_selection""").fetchone()[0],0)

    def test_raw_database_cannot_bind_a_session_to_different_owner(self):
        import hashlib
        h=hashlib.sha256(self.a["token"].encode()).hexdigest()
        with account_scope._db(self.path) as con:
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("""INSERT INTO tenant_session_account_selection
                    (token_hash,user_id,account_id,selected_at)
                    VALUES(?,?,?,1)""",(h,self.another,self.bb))
        self.api.select_account(self.a["token"],self.a["csrf"],self.aa)
        with account_scope._db(self.path) as con:
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("""UPDATE tenant_session_account_selection
                    SET user_id=?,account_id=? WHERE token_hash=?""",
                    (self.another,self.bb,h))
        self.assertEqual(self.api.selected_account(self.a["token"]),self.aa)

    def test_account_disable_and_provider_revocation_fail_closed(self):
        self.api.select_account(self.a["token"],self.a["csrf"],self.aa)
        self.api.select_account(self.b["token"],self.b["csrf"],self.a2)
        with account_scope._db(self.path) as con:
            con.execute("UPDATE tenant_accounts SET disabled_at='2026-11-09' WHERE account_id=?",
                        (self.aa,))
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.api.selected_account(self.a["token"])
        self.assertEqual(self.api.selected_account(self.b["token"]),self.a2)
        with account_scope._db(self.path) as con:
            con.execute("UPDATE tenant_connections SET revoked_at='2026-11-09' WHERE connection_id=?",
                        (self.ca,))
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.api.selected_account(self.b["token"])
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.api.list_accounts(self.c["token"] + "bogus")
        self.assertEqual(self._legacy(),"LEGACY-UNCHANGED")

    def test_selection_clearing_is_per_session(self):
        self.api.select_account(self.a["token"],self.a["csrf"],self.aa)
        self.api.select_account(self.b["token"],self.b["csrf"],self.a2)
        with self.assertRaises(tenant_api_gateway.AccountSelectionError):
            self.api.clear_selection(self.a["token"],self.c["csrf"])
        self.api.clear_selection(self.a["token"],self.a["csrf"])
        self.assertIsNone(self.api.selected_account(self.a["token"]))
        self.assertEqual(self.api.selected_account(self.b["token"]),self.a2)

    def test_never_exposes_execution_capability(self):
        for handler in (self.api.blocked_operation,):
            with self.assertRaises(tenant_foundation.TenantAccessError):
                handler("trade","BUY","SPY")
        self.assertEqual(self._legacy(),"LEGACY-UNCHANGED")

    def test_account_specific_monitor_plans_never_activate(self):
        self.store.account_setting(self.owner,self.aa,"watchlist_csv","SPY,QQQ")
        self.store.account_setting(self.owner,self.a2,"watchlist_csv","IWM")
        self.store.account_setting(self.another,self.bb,"watchlist_csv","MSFT")
        aa=self.planner.plan_for(self.owner,self.aa)
        a2=self.planner.plan_for(self.owner,self.a2)
        bb=self.planner.plan_for(self.another,self.bb)
        self.assertEqual(aa.symbols,("SPY","QQQ"))
        self.assertEqual(a2.symbols,("IWM",))
        self.assertEqual(bb.symbols,("MSFT",))
        for plan in self.planner.enumerate_disabled():
            self.assertFalse(plan.scheduled)
            self.assertFalse(plan.runtime_enabled)
            self.assertFalse(plan.broker_requests_allowed)
            self.assertFalse(plan.paper_trading_allowed)
            self.assertFalse(plan.live_trading_allowed)
            self.assertEqual(plan.mode,"observe")
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.planner.plan_for(self.owner,self.bb)
        for method in ("start_live_monitoring","execute_order"):
            with self.assertRaises(tenant_monitor_blueprint.MonitorPlanningError):
                getattr(self.planner,method)(aa)
        self.assertEqual(self._legacy(),"LEGACY-UNCHANGED")

    def test_offline_synthetic_cycle_stays_in_one_owner_and_account(self):
        self.store.account_setting(self.owner,self.aa,"watchlist_csv","SPY,QQQ")
        self.store.account_setting(self.owner,self.a2,"watchlist_csv","IWM")
        self.store.account_setting(self.another,self.bb,"watchlist_csv","MSFT")
        aa=self.planner.plan_for(self.owner,self.aa)
        a2=self.planner.plan_for(self.owner,self.a2)
        bb=self.planner.plan_for(self.another,self.bb)
        with self.assertRaises(tenant_monitor_blueprint.MonitorPlanningError):
            self.planner.offline_replay(aa,"worker-0000000001",approval="no")
        self.planner.offline_replay(aa,"worker-0000000001",
                                   approval="SYNTHETIC ACCOUNT OBSERVATION ONLY")
        self.planner.offline_replay(bb,"worker-0000000002",
                                   approval="SYNTHETIC ACCOUNT OBSERVATION ONLY")
        a_summary=self.api.account_summary(self.a["token"],self.aa)
        b_summary=self.api.account_summary(self.c["token"],self.bb)
        empty=self.api.account_summary(self.a["token"],self.a2)
        self.assertEqual(a_summary["observation"]["symbols"],["SPY","QQQ"])
        self.assertEqual(b_summary["observation"]["symbols"],["MSFT"])
        self.assertEqual(a_summary["observation"]["accepted"],0)
        self.assertEqual(a_summary["observation"]["state"],"NO_DATA")
        self.assertIsNone(empty["observation"])
        self.assertEqual(a_summary["last24h"]["cycles"],1)
        self.assertEqual(b_summary["last24h"]["cycles"],1)
        self.assertEqual(empty["last24h"]["cycles"],0)
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tenant_worker_leases").fetchone()[0],0)

    def test_offline_replay_fails_after_account_state_or_watchlist_changes(self):
        self.store.account_setting(self.owner,self.aa,"watchlist_csv","SPY")
        plan=self.planner.plan_for(self.owner,self.aa)
        self.store.account_setting(self.owner,self.aa,"watchlist_csv","AAPL")
        with self.assertRaises(tenant_monitor_blueprint.MonitorPlanningError):
            self.planner.offline_replay(plan,"worker-0000000003",
                                      approval="SYNTHETIC ACCOUNT OBSERVATION ONLY")
        plan=self.planner.plan_for(self.owner,self.aa)
        with account_scope._db(self.path) as con:
            con.execute("UPDATE tenant_connections SET revoked_at='2026-11-09' WHERE connection_id=?",
                        (self.ca,))
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.planner.offline_replay(plan,"worker-0000000003",
                                      approval="SYNTHETIC ACCOUNT OBSERVATION ONLY")

    def test_inactive_modules_not_connected_to_http_or_live_worker(self):
        app=(ROOT/"backend/app.py").read_text()
        worker=(ROOT/"backend/engine/automation_worker.py").read_text()
        self.assertNotIn("tenant_api_gateway",app)
        self.assertIn("tenant_monitor_blueprint",app)
        self.assertIn("EDGE_TENANT_MONITOR_PREVIEW_ENABLED','false'",app)
        for module in ("tenant_api_gateway","tenant_monitor_blueprint"):
            self.assertNotIn(module,worker)
        self.assertIn("'liveTradingAvailable':False",app)


if __name__=="__main__":
    unittest.main()
