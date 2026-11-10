"""v0.2.32 identity-scoped, strictly inactive monitoring plan HTTP preview.

No Public network requests, scheduling, market scans, paper orders or trades.
Tests operate on synthetic identities and isolated temporary tenant databases.
"""
import importlib
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from engine import tenant_foundation

ORIGIN="https://edgepilot.example.test"
HEADERS={"Origin":ORIGIN}
ALICE_PASS="synthetic-alice-password-long-enough-v032"
BOB_PASS="synthetic-bob-password-long-enough-v032"


class TenantMonitoringPreviewHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="edgepilot-monitor-preview-")
        self.env=patch.dict(os.environ,{
            "EDGE_DB_PATH":self.temp.name+"/edgepilot.db",
            "EDGE_TENANT_SCHEMA_PREPARE":"true",
            "EDGE_IDENTITY_AUTH_ENABLED":"true",
            "EDGE_TENANT_ACCOUNT_READS_ENABLED":"true",
            "EDGE_TENANT_MONITOR_PREVIEW_ENABLED":"true",
            "EDGE_TENANT_PUBLIC_READONLY_ENABLED":"false",
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED":"false",
            "EDGE_AUTOMATION_WORKER_ENABLED":"false",
            "EDGE_APP_TOKEN":"synthetic-owner-only-test-token-000000000000000000",
            "PUBLIC_API_SECRET":"",
        })
        self.env.start()
        import app
        self.mod=importlib.reload(app)
        self.a=self.mod.app.test_client()
        self.b=self.mod.app.test_client()
        self.anon=self.mod.app.test_client()
        self.tenants=tenant_foundation.TenantStore(
            str(self.mod.DB),credential_key=Fernet.generate_key().decode())
        self.alice=self.tenants.provision_user("Alice","member")
        self.bob=self.tenants.provision_user("Bob","member")
        self.mod.identity_store.provision(self.alice,"monitor_alice",ALICE_PASS)
        self.mod.identity_store.provision(self.bob,"monitor_bob",BOB_PASS)
        self.ca=self.tenants.add_connection(self.alice,"synthetic-api-key-alice-v032")
        self.cb=self.tenants.add_connection(self.bob,"synthetic-api-key-bob-v032")
        self.a1=self.tenants.link_account(self.alice,self.ca,"FAKE-A-1","Alice one")
        self.a2=self.tenants.link_account(self.alice,self.ca,"FAKE-A-2","Alice two")
        self.b1=self.tenants.link_account(self.bob,self.cb,"FAKE-B-1","Bob one")
        self.tenants.account_setting(self.alice,self.a1,"watchlist_csv","SPY,QQQ")
        self.tenants.account_setting(self.alice,self.a2,"watchlist_csv","IWM")
        self.tenants.account_setting(self.bob,self.b1,"watchlist_csv","MSFT")
        self._login(self.a,"monitor_alice",ALICE_PASS)
        self._login(self.b,"monitor_bob",BOB_PASS)

    def tearDown(self):
        self.env.stop()
        import app
        importlib.reload(app)
        self.temp.cleanup()

    def _login(self,client,name,password):
        response=client.post("/api/identity/login",base_url=ORIGIN,headers=HEADERS,
                             json={"username":name,"password":password})
        self.assertEqual(response.status_code,200,response.get_data(as_text=True))

    def _plan(self,client,account_id):
        return client.get("/api/identity/accounts/"+account_id+"/monitor/preview",
                          base_url=ORIGIN)

    def test_each_identity_has_separate_inactive_watchlists(self):
        one=self._plan(self.a,self.a1)
        two=self._plan(self.a,self.a2)
        other=self._plan(self.b,self.b1)
        self.assertEqual([one.status_code,two.status_code,other.status_code],
                         [200,200,200])
        self.assertEqual(one.get_json()["watchlist"],["SPY","QQQ"])
        self.assertEqual(two.get_json()["watchlist"],["IWM"])
        self.assertEqual(other.get_json()["watchlist"],["MSFT"])
        self.assertEqual(one.get_json()["accountId"],self.a1)
        for response in (one,two,other):
            data=response.get_json()
            self.assertTrue(data["readOnly"])
            self.assertTrue(data["simulatedPlanOnly"])
            self.assertEqual(data["mode"],"observe")
            self.assertFalse(data["scheduled"])
            self.assertFalse(data["workerActive"])
            self.assertFalse(data["brokerRequestsAllowed"])
            self.assertFalse(data["paperEnabled"])
            self.assertFalse(data["liveTradingEnabled"])
            self.assertNotIn("synthetic-api-key",response.get_data(as_text=True))
            self.assertNotIn("FAKE-A-",response.get_data(as_text=True))

    def test_swapped_account_ids_and_forged_owner_query_fail_closed(self):
        for client,wrong in ((self.a,self.b1),(self.b,self.a1),
                             (self.b,self.a2),(self.a,"forged-id")):
            response=self._plan(client,wrong)
            self.assertEqual(response.status_code,404)
            self.assertEqual(response.get_json()["error"],"Account unavailable")
        query=self.a.get("/api/identity/accounts/"+self.a1+
                         "/monitor/preview?user_id="+self.bob,base_url=ORIGIN)
        self.assertEqual(query.status_code,200)
        self.assertEqual(query.get_json()["watchlist"],["SPY","QQQ"])
        self.assertEqual(self._plan(self.anon,self.a1).status_code,401)

    def test_account_disable_or_connection_revocation_does_not_affect_other_owner(self):
        with sqlite3.connect(self.mod.DB) as con:
            con.execute("UPDATE tenant_accounts SET disabled_at='2026-11-10' WHERE account_id=?",
                        (self.a1,))
        self.assertEqual(self._plan(self.a,self.a1).status_code,404)
        self.assertEqual(self._plan(self.a,self.a2).status_code,200)
        with sqlite3.connect(self.mod.DB) as con:
            con.execute("UPDATE tenant_connections SET revoked_at='2026-11-10' WHERE connection_id=?",
                        (self.ca,))
        self.assertEqual(self._plan(self.a,self.a2).status_code,404)
        self.assertEqual(self._plan(self.b,self.b1).status_code,200)

    def test_invalid_watchlist_refuses_without_leaking_raw_settings(self):
        with sqlite3.connect(self.mod.DB) as con:
            con.execute("""UPDATE tenant_account_settings SET setting_value=?
                WHERE user_id=? AND account_id=? AND setting_key='watchlist_csv'""",
                ("<script>alert('x')</script>",self.alice,self.a2))
        resp=self._plan(self.a,self.a2)
        self.assertEqual(resp.status_code,404)
        self.assertEqual(resp.get_json()["error"],"Account unavailable")
        self.assertNotIn("script",resp.get_data(as_text=True))
        self.assertEqual(self._plan(self.b,self.b1).status_code,200)


class TenantMonitorPreviewDisabledTests(unittest.TestCase):
    def test_off_by_default_and_never_starts_worker(self):
        with tempfile.TemporaryDirectory(prefix="edgepilot-monitor-off-") as temp:
            with patch.dict(os.environ,{
                "EDGE_DB_PATH":temp+"/edgepilot.db",
                "EDGE_TENANT_SCHEMA_PREPARE":"true",
                "EDGE_IDENTITY_AUTH_ENABLED":"true",
                "EDGE_TENANT_ACCOUNT_READS_ENABLED":"true",
                "EDGE_TENANT_MONITOR_PREVIEW_ENABLED":"false",
                "EDGE_AUTOMATION_WORKER_ENABLED":"false"
            }):
                import app
                m=importlib.reload(app)
                self.assertIsNone(m.tenant_monitor_planner)
                client=m.app.test_client()
                self.assertEqual(client.get(
                    "/api/identity/accounts/random-id/monitor/preview",
                    base_url=ORIGIN).status_code,401)
                # A valid identity session would still get a 404 from the
                # route because the feature flag is off.
                self.assertFalse(m.tenant_monitor_preview_enabled)
        import app
        importlib.reload(app)

    def test_cannot_enable_monitor_preview_without_identity_account_reads(self):
        with tempfile.TemporaryDirectory(prefix="edgepilot-monitor-invalid-") as temp:
            with patch.dict(os.environ,{
                "EDGE_DB_PATH":temp+"/edgepilot.db",
                "EDGE_TENANT_SCHEMA_PREPARE":"true",
                "EDGE_IDENTITY_AUTH_ENABLED":"true",
                "EDGE_TENANT_ACCOUNT_READS_ENABLED":"false",
                "EDGE_TENANT_MONITOR_PREVIEW_ENABLED":"true",
                "EDGE_AUTOMATION_WORKER_ENABLED":"false"
            }):
                import app
                with self.assertRaisesRegex(RuntimeError,"requires account-scoped"):
                    importlib.reload(app)
        import app
        importlib.reload(app)


if __name__=="__main__":
    unittest.main()
