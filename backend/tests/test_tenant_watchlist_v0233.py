"""v0.2.33 authenticated account-specific watchlist editing tests.

All credentials/accounts are synthetic. No Public HTTP, scanning, paper
trading, funds transfers or order execution occurs.
"""
import importlib
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from engine import tenant_foundation, tenant_watchlist, tenant_route_audit

BASE="https://edgepilot.example.test"
ORIGIN={"Origin":BASE}
A_PASS="synthetic-user-A-password-v033-long-enough"
B_PASS="synthetic-user-B-password-v033-long-enough"


class TenantWatchlistHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="edgepilot-v033-watchlists-")
        self.env=patch.dict(os.environ,{
            "EDGE_DB_PATH":self.temp.name+"/edgepilot.db",
            "EDGE_TENANT_SCHEMA_PREPARE":"true",
            "EDGE_IDENTITY_AUTH_ENABLED":"true",
            "EDGE_TENANT_ACCOUNT_READS_ENABLED":"true",
            "EDGE_TENANT_MONITOR_PREVIEW_ENABLED":"true",
            "EDGE_TENANT_WATCHLIST_EDIT_ENABLED":"true",
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED":"false",
            "EDGE_TENANT_PUBLIC_READONLY_ENABLED":"false",
            "EDGE_AUTOMATION_WORKER_ENABLED":"false",
            "EDGE_APP_TOKEN":"synthetic-legacy-owner-login-token-v033-00000000000",
            "PUBLIC_API_SECRET":"",
        })
        self.env.start()
        import app
        self.mod=importlib.reload(app)
        self.alice=self.mod.app.test_client()
        self.bob=self.mod.app.test_client()
        self.anon=self.mod.app.test_client()
        tenant=tenant_foundation.TenantStore(
            str(self.mod.DB),credential_key=Fernet.generate_key().decode())
        self.owner_a=tenant.provision_user("Alice","member")
        self.owner_b=tenant.provision_user("Bob","member")
        self.mod.identity_store.provision(self.owner_a,"v033_alice",A_PASS)
        self.mod.identity_store.provision(self.owner_b,"v033_bob",B_PASS)
        self.conn_a=tenant.add_connection(self.owner_a,"fake-key-alice-v033-keep-private")
        self.conn_b=tenant.add_connection(self.owner_b,"fake-key-bob-v033-keep-private")
        self.acct_a=tenant.link_account(self.owner_a,self.conn_a,"A-ACCOUNT","Alice")
        self.acct_b=tenant.link_account(self.owner_b,self.conn_b,"B-ACCOUNT","Bob")
        self.csrf_a=self.login(self.alice,"v033_alice",A_PASS)
        self.csrf_b=self.login(self.bob,"v033_bob",B_PASS)

    def tearDown(self):
        self.env.stop()
        import app
        importlib.reload(app)
        self.temp.cleanup()

    def login(self,client,name,password):
        r=client.post("/api/identity/login",base_url=BASE,headers=ORIGIN,
                      json={"username":name,"password":password})
        self.assertEqual(r.status_code,200,r.get_data(as_text=True))
        return r.get_json()["csrf"]

    def put(self,client,account,symbols,csrf=None):
        headers={**ORIGIN}
        if csrf is not None:
            headers["X-Edge-Identity-CSRF"]=csrf
        return client.put("/api/identity/accounts/"+account+"/monitor/watchlist",
                          base_url=BASE,headers=headers,json={"symbols":symbols})

    def preview(self,client,account):
        return client.get("/api/identity/accounts/"+account+"/monitor/preview",
                          base_url=BASE)

    def test_two_users_and_two_watchlists_are_independent_and_never_execute(self):
        a=self.put(self.alice,self.acct_a,["SPY","QQQ"],self.csrf_a)
        b=self.put(self.bob,self.acct_b,["MSFT"],self.csrf_b)
        self.assertEqual([a.status_code,b.status_code],[200,200])
        for response in (a,b):
            data=response.get_json()
            self.assertTrue(data["saved"])
            self.assertTrue(data["readOnlyMonitoring"])
            self.assertFalse(data["workerActive"])
            self.assertFalse(data["brokerRequestsAllowed"])
            self.assertFalse(data["paperEnabled"])
            self.assertFalse(data["liveTradingEnabled"])
            self.assertFalse(data["fundTransfersEnabled"])
            self.assertNotIn("fake-key-",response.get_data(as_text=True))
        self.assertEqual(self.preview(self.alice,self.acct_a).get_json()["watchlist"],["SPY","QQQ"])
        self.assertEqual(self.preview(self.bob,self.acct_b).get_json()["watchlist"],["MSFT"])
        self.assertEqual(self.put(self.alice,self.acct_a,[],self.csrf_a).get_json()["watchlist"],[])
        self.assertEqual(self.preview(self.alice,self.acct_a).get_json()["watchlist"],[])
        self.assertEqual(self.preview(self.bob,self.acct_b).get_json()["watchlist"],["MSFT"])
        with sqlite3.connect(self.mod.DB) as con:
            rows=con.execute("""SELECT user_id,account_id,setting_value
                FROM tenant_account_settings WHERE setting_key='watchlist_csv'
                ORDER BY user_id""").fetchall()
            self.assertEqual(len(rows),2)
            self.assertEqual({(r[0],r[1]):r[2] for r in rows},
                {(self.owner_a,self.acct_a):"",(self.owner_b,self.acct_b):"MSFT"})
            events=con.execute("""SELECT user_id,account_id,action FROM tenant_audit_events
                WHERE action='ACCOUNT_SETTING_CHANGED'""").fetchall()
            self.assertEqual(len(events),3)
            self.assertTrue(all(r[2]=="ACCOUNT_SETTING_CHANGED" for r in events))
            worker=con.execute("SELECT COUNT(*) FROM tenant_worker_leases").fetchone()[0]
            cycles=con.execute("SELECT COUNT(*) FROM tenant_observation_cycles").fetchone()[0]
            self.assertEqual([worker,cycles],[0,0])

    def test_foreign_owner_csrf_and_spoofed_user_denied(self):
        self.assertEqual(self.put(self.alice,self.acct_b,["AAPL"],self.csrf_a).status_code,404)
        self.assertEqual(self.put(self.bob,self.acct_a,["AAPL"],self.csrf_b).status_code,404)
        self.assertEqual(self.put(self.anon,self.acct_a,["AAPL"]).status_code,401)
        self.assertEqual(self.put(self.alice,self.acct_a,["AAPL"],self.csrf_b).status_code,403)
        self.assertEqual(self.put(self.alice,self.acct_a,["AAPL"]).status_code,403)
        spoof=self.alice.put("/api/identity/accounts/"+self.acct_a+"/monitor/watchlist",
            base_url=BASE,headers={**ORIGIN,"X-Edge-Identity-CSRF":self.csrf_a},
            json={"symbols":["SPY"],"user_id":self.owner_b})
        self.assertEqual(spoof.status_code,400)
        cross=self.alice.put("/api/identity/accounts/"+self.acct_a+"/monitor/watchlist",
            base_url=BASE,headers={"Origin":"https://evil.invalid","X-Edge-Identity-CSRF":self.csrf_a},
            json={"symbols":["SPY"]})
        self.assertEqual(cross.status_code,403)
        with sqlite3.connect(self.mod.DB) as con:
            self.assertEqual(con.execute("""SELECT COUNT(*) FROM tenant_account_settings""").fetchone()[0],0)

    def test_validation_atomic_denial_does_not_rewrite_existing_symbols(self):
        self.assertEqual(self.put(self.alice,self.acct_a,["SPY"],self.csrf_a).status_code,200)
        invalid=(["spy"],["SPY","SPY"],["<script>"],["A"*16],
                 ["AAPL"]*26,["AAPL",None],None,{"symbols":"SPY"},"SPY,QQQ",
                 [123],[False],["ABC DEF"],["SPY\nQQQ"])
        for candidate in invalid:
            with self.subTest(value=str(candidate)[:30]):
                response=self.put(self.alice,self.acct_a,candidate,self.csrf_a)
                self.assertEqual(response.status_code,400,response.get_data(as_text=True))
                self.assertNotIn("script",response.get_data(as_text=True))
                self.assertEqual(self.preview(self.alice,self.acct_a).get_json()["watchlist"],["SPY"])
        with sqlite3.connect(self.mod.DB) as con:
            self.assertEqual(con.execute("""SELECT COUNT(*) FROM tenant_audit_events
                WHERE action='ACCOUNT_SETTING_CHANGED'""").fetchone()[0],1)

    def test_revoked_or_disabled_account_and_session_cannot_update(self):
        self.assertEqual(self.put(self.alice,self.acct_a,["SPY"],self.csrf_a).status_code,200)
        with sqlite3.connect(self.mod.DB) as con:
            con.execute("UPDATE tenant_accounts SET disabled_at='2026-11-10' WHERE account_id=?",
                        (self.acct_a,))
        self.assertEqual(self.put(self.alice,self.acct_a,["QQQ"],self.csrf_a).status_code,404)
        self.assertEqual(self.put(self.bob,self.acct_b,["MSFT"],self.csrf_b).status_code,200)
        with sqlite3.connect(self.mod.DB) as con:
            con.execute("UPDATE tenant_connections SET revoked_at='2026-11-10' WHERE connection_id=?",
                        (self.conn_b,))
        self.assertEqual(self.put(self.bob,self.acct_b,["NVDA"],self.csrf_b).status_code,404)
        logout=self.alice.post("/api/identity/logout",base_url=BASE,
                               headers={**ORIGIN,"X-Edge-Identity-CSRF":self.csrf_a},json={})
        self.assertEqual(logout.status_code,200)
        self.assertEqual(self.put(self.alice,self.acct_a,["SPY"],self.csrf_a).status_code,401)
        with sqlite3.connect(self.mod.DB) as con:
            self.assertEqual(con.execute("""SELECT setting_value FROM tenant_account_settings
                WHERE account_id=?""",(self.acct_a,)).fetchone()[0],"SPY")

    def test_unexpected_active_runtime_blocks_settings_edits(self):
        with sqlite3.connect(self.mod.DB) as con:
            con.execute("""INSERT INTO tenant_runtime_status
                (user_id,account_id,requested_mode,worker_enabled,paper_enabled,live_enabled)
                VALUES(?,?,'observe',0,0,0)""",(self.owner_a,self.acct_a))
            # CHECK constraints forbid active flags. To exercise fail-closed
            # path, corrupt the runtime mode with ignore_check_constraints.
            con.execute("PRAGMA ignore_check_constraints=ON")
            con.execute("UPDATE tenant_runtime_status SET worker_enabled=1 WHERE account_id=?",
                        (self.acct_a,))
            con.execute("PRAGMA ignore_check_constraints=OFF")
        self.assertEqual(self.put(self.alice,self.acct_a,["SPY"],self.csrf_a).status_code,404)
        self.assertEqual(self.put(self.bob,self.acct_b,["MSFT"],self.csrf_b).status_code,200)


class TenantWatchlistUiChecks(unittest.TestCase):
    def test_private_watchlist_controls_require_readonly_and_current_identity(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[2]
        js=(root/"backend/static/assets/identity.js").read_text(encoding="utf-8")
        for pattern in (
            '"PUT", {symbols}, true',
            'requestGeneration !== identityViewGeneration',
            'saved.accountId !== id',
            'saved.workerActive !== false',
            'saved.liveTradingEnabled !== false',
            'saved.fundTransfersEnabled !== false',
            'new Set(symbols).size !== symbols.length',
            '"Save account watchlist"',
            'listInput.maxLength = 512',
        ):
            self.assertIn(pattern,js)
        self.assertNotIn("innerHTML",js)


class TenantWatchlistOffTests(unittest.TestCase):
    def test_default_off_and_activation_dependency(self):
        with tempfile.TemporaryDirectory(prefix="edgepilot-v033-disabled-") as tmp:
            with patch.dict(os.environ,{
                "EDGE_DB_PATH":tmp+"/edgepilot.db",
                "EDGE_TENANT_SCHEMA_PREPARE":"true",
                "EDGE_IDENTITY_AUTH_ENABLED":"true",
                "EDGE_TENANT_ACCOUNT_READS_ENABLED":"true",
                "EDGE_TENANT_MONITOR_PREVIEW_ENABLED":"true",
                "EDGE_TENANT_WATCHLIST_EDIT_ENABLED":"false",
                "EDGE_AUTOMATION_WORKER_ENABLED":"false",
            }):
                import app
                mod=importlib.reload(app)
                self.assertIsNone(mod.tenant_watchlist_editor)
                self.assertFalse(mod.tenant_watchlist_edit_enabled)
        import app
        importlib.reload(app)

    def test_edit_never_enables_preview_implicitly(self):
        with tempfile.TemporaryDirectory(prefix="edgepilot-v033-invalid-") as tmp:
            with patch.dict(os.environ,{
                "EDGE_DB_PATH":tmp+"/edgepilot.db",
                "EDGE_TENANT_SCHEMA_PREPARE":"true",
                "EDGE_IDENTITY_AUTH_ENABLED":"true",
                "EDGE_TENANT_ACCOUNT_READS_ENABLED":"true",
                "EDGE_TENANT_MONITOR_PREVIEW_ENABLED":"false",
                "EDGE_TENANT_WATCHLIST_EDIT_ENABLED":"true",
                "EDGE_AUTOMATION_WORKER_ENABLED":"false",
            }):
                import app
                with self.assertRaisesRegex(RuntimeError,"requires inactive monitoring preview"):
                    importlib.reload(app)
        import app
        importlib.reload(app)


if __name__=="__main__":
    unittest.main()
