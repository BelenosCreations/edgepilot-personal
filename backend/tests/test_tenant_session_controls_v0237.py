"""v0.2.37 device-session visibility and selective other-session revocation.

Uses synthetic EdgePilot users and temporary SQLite only. No real Public
credentials, biometric templates, HTTP provider requests or trade activity.
"""
import importlib
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from engine import identity_auth, tenant_foundation, tenant_session_controls

ORIGIN="https://edgepilot.example.test"
HEADERS={"Origin":ORIGIN}
PW_A="alice-account-v037-strong-password-test"
PW_B="bob-account-v037-strong-password-test"


class SessionControlRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="edgepilot-v037-session-")
        self.path=self.temp.name+"/test.db"
        tenant_foundation.setup(self.path)
        identity_auth.setup(self.path)
        tenant_session_controls.setup(self.path)
        self.identity=identity_auth.IdentityStore(self.path)
        self.manager=tenant_session_controls.TenantSessionControls(self.path,self.identity)
        store=tenant_foundation.TenantStore(self.path)
        self.alice=store.provision_user("Alice","member")
        self.bob=store.provision_user("Bob","member")
        self.identity.provision(self.alice,"v037_alice",PW_A)
        self.identity.provision(self.bob,"v037_bob",PW_B)
        self.a1=self.identity.authenticate("v037_alice",PW_A,"android-a")
        self.a2=self.identity.authenticate("v037_alice",PW_A,"tablet-a")
        self.b1=self.identity.authenticate("v037_bob",PW_B,"android-b")

    def tearDown(self):
        self.temp.cleanup()

    def test_list_is_scoped_and_does_not_disclose_tokens_or_network_identifiers(self):
        aa=self.manager.list_sessions(self.a1["token"],self.a1["csrf"])
        ab=self.manager.list_sessions(self.a2["token"],self.a2["csrf"])
        bb=self.manager.list_sessions(self.b1["token"],self.b1["csrf"])
        self.assertEqual((aa["count"],ab["count"],bb["count"]),(2,2,1))
        self.assertEqual(sum(s["current"] for s in aa["sessions"]),1)
        self.assertEqual(sum(s["current"] for s in bb["sessions"]),1)
        self.assertEqual({s["sessionId"] for s in aa["sessions"]},
                         {s["sessionId"] for s in ab["sessions"]})
        self.assertTrue(aa["readOnly"])
        self.assertFalse(aa["deviceDetailsStored"])
        self.assertFalse(aa["publicKeysReturned"])
        for text in (self.a1["token"],self.a2["token"],self.b1["token"],
                     self.a1["csrf"],self.a2["csrf"],"android-a",
                     "tablet-a","android-b",self.alice,self.bob):
            self.assertNotIn(text,str(aa))
        for entry in aa["sessions"]:
            self.assertEqual(set(entry),{"sessionId","issuedAt","expiresAt","current"})
            self.assertRegex(entry["sessionId"],r"^[0-9a-f]{32}$")

    def test_revoke_other_session_preserves_owner_current_and_other_user(self):
        view=self.manager.list_sessions(self.a1["token"],self.a1["csrf"])
        target=next(s["sessionId"] for s in view["sessions"] if not s["current"])
        outcome=self.manager.revoke_other(self.a1["token"],self.a1["csrf"],target)
        self.assertTrue(outcome["otherSessionRevoked"])
        self.assertFalse(outcome["currentSessionRevoked"])
        self.assertFalse(outcome["otherUserAffected"])
        self.assertFalse(outcome["publicConnectionChanged"])
        self.assertFalse(outcome["liveTradingEnabled"])
        self.assertFalse(outcome["fundTransfersEnabled"])
        self.assertIsNotNone(self.identity.principal(self.a1["token"]))
        self.assertIsNone(self.identity.principal(self.a2["token"]))
        self.assertIsNotNone(self.identity.principal(self.b1["token"]))
        self.assertEqual(self.manager.list_sessions(self.a1["token"],self.a1["csrf"])["count"],1)
        with sqlite3.connect(self.path) as db:
            audit=db.execute("SELECT user_id,action FROM tenant_session_control_events").fetchall()
            self.assertEqual(audit,[(self.alice,"OTHER_SESSION_REVOKED")])
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM tenant_session_control_events")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE tenant_session_control_events SET action='X'")

    def test_cross_owner_current_session_and_invalid_csrf_denied(self):
        a=self.manager.list_sessions(self.a1["token"],self.a1["csrf"])
        b=self.manager.list_sessions(self.b1["token"],self.b1["csrf"])
        own=next(s["sessionId"] for s in a["sessions"] if s["current"])
        foreign=b["sessions"][0]["sessionId"]
        for handle in (own,foreign,"bogus","f"*32,"A"*32):
            with self.subTest(handle=handle):
                with self.assertRaises(tenant_session_controls.SessionControlDenied):
                    self.manager.revoke_other(self.a1["token"],self.a1["csrf"],handle)
        for token,csrf in ((self.a1["token"],self.b1["csrf"]),
                           (self.b1["token"],self.a1["csrf"]),
                           ("fake",self.a1["csrf"])):
            with self.assertRaises(tenant_session_controls.SessionControlDenied):
                self.manager.list_sessions(token,csrf)
        self.assertIsNotNone(self.identity.principal(self.a2["token"]))
        self.assertIsNotNone(self.identity.principal(self.b1["token"]))

    def test_concurrent_revocation_is_exactly_once_and_no_cross_user_effect(self):
        view=self.manager.list_sessions(self.a1["token"],self.a1["csrf"])
        target=next(s["sessionId"] for s in view["sessions"] if not s["current"])
        def call(_):
            try:
                self.manager.revoke_other(self.a1["token"],self.a1["csrf"],target)
                return "revoked"
            except tenant_session_controls.SessionControlDenied:
                return "denied"
        with ThreadPoolExecutor(max_workers=2) as pool:
            result=list(pool.map(call,range(2)))
        self.assertEqual(sorted(result),["denied","revoked"])
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM tenant_session_control_events").fetchone()[0],1)
        self.assertIsNotNone(self.identity.principal(self.b1["token"]))

    def test_expiry_disabled_account_and_password_all_session_logout(self):
        later=self.a1["expires_at"] + 2
        with self.assertRaises(tenant_session_controls.SessionControlDenied):
            self.manager.list_sessions(self.a1["token"],self.a1["csrf"],now=later)
        with self.assertRaises(tenant_session_controls.SessionControlDenied):
            self.manager.revoke_other(self.a1["token"],self.a1["csrf"],
                                      "0"*32,now=later)
        self.identity.revoke_all(self.alice)
        with self.assertRaises(tenant_session_controls.SessionControlDenied):
            self.manager.list_sessions(self.a1["token"],self.a1["csrf"])
        self.assertIsNotNone(self.identity.principal(self.b1["token"]))

    def test_schema_disabled_requires_tenant_identities(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                tenant_session_controls.setup(tmp+"/empty.db")


class SessionControlHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="edgepilot-v037-http-")
        self.patch=patch.dict(os.environ,{
            "EDGE_DB_PATH":self.tmp.name+"/edgepilot.db",
            "EDGE_TENANT_SCHEMA_PREPARE":"true",
            "EDGE_IDENTITY_AUTH_ENABLED":"true",
            "EDGE_TENANT_SESSION_CONTROLS_ENABLED":"true",
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED":"false",
            "EDGE_TENANT_PASSKEYS_ENABLED":"false",
            "EDGE_AUTOMATION_WORKER_ENABLED":"false",
            "EDGE_APP_TOKEN":"synthetic-personal-owner-token-v037-00000000000000000",
            "PUBLIC_API_SECRET":"",
        })
        self.patch.start()
        import app
        self.mod=importlib.reload(app)
        self.client_a=self.mod.app.test_client()
        self.client_a2=self.mod.app.test_client()
        self.client_b=self.mod.app.test_client()
        self.anonymous=self.mod.app.test_client()
        tenants=tenant_foundation.TenantStore(str(self.mod.DB))
        a=tenants.provision_user("Alice","member")
        b=tenants.provision_user("Bob","member")
        self.mod.identity_store.provision(a,"v037_alice",PW_A)
        self.mod.identity_store.provision(b,"v037_bob",PW_B)
        self.csrf_a=self.login(self.client_a,"v037_alice",PW_A)
        self.csrf_a2=self.login(self.client_a2,"v037_alice",PW_A)
        self.csrf_b=self.login(self.client_b,"v037_bob",PW_B)

    def tearDown(self):
        self.patch.stop()
        import app
        importlib.reload(app)
        self.tmp.cleanup()

    def login(self,client,user,pwd):
        response=client.post("/api/identity/login",base_url=ORIGIN,
                             headers=HEADERS,json={"username":user,"password":pwd})
        self.assertEqual(response.status_code,200,response.get_data(as_text=True))
        return response.get_json()["csrf"]

    def listing(self,client,csrf):
        return client.get("/api/identity/sessions",base_url=ORIGIN,
                          headers={"X-Edge-Identity-CSRF":csrf})

    def revoke(self,client,csrf,session_id,origin=ORIGIN):
        return client.delete("/api/identity/sessions/"+session_id,
                             base_url=ORIGIN,headers={
                                 "Origin":origin,"X-Edge-Identity-CSRF":csrf
                             })

    def test_two_device_session_list_and_revocation_are_user_scoped(self):
        list_a=self.listing(self.client_a,self.csrf_a)
        list_b=self.listing(self.client_b,self.csrf_b)
        self.assertEqual(list_a.status_code,200)
        self.assertEqual(list_b.status_code,200)
        self.assertEqual((list_a.get_json()["count"],list_b.get_json()["count"]),(2,1))
        target=next(x["sessionId"] for x in list_a.get_json()["sessions"]
                    if not x["current"])
        self.assertEqual(self.revoke(self.client_b,self.csrf_b,target).status_code,404)
        out=self.revoke(self.client_a,self.csrf_a,target)
        self.assertEqual(out.status_code,200,out.get_data(as_text=True))
        self.assertFalse(out.get_json()["otherUserAffected"])
        self.assertEqual(self.client_a2.get("/api/identity/session",
            base_url=ORIGIN).status_code,401)
        self.assertEqual(self.client_a.get("/api/identity/session",
            base_url=ORIGIN).status_code,200)
        self.assertEqual(self.client_b.get("/api/identity/session",
            base_url=ORIGIN).status_code,200)
        self.assertEqual(self.client_a.get("/api/dashboard",base_url=ORIGIN).status_code,401)

    def test_csrf_origin_anonymous_and_current_session_protection(self):
        self.assertEqual(self.listing(self.anonymous,self.csrf_a).status_code,401)
        self.assertEqual(self.listing(self.client_a,self.csrf_b).status_code,403)
        own=next(x["sessionId"] for x in self.listing(
            self.client_a,self.csrf_a).get_json()["sessions"] if x["current"])
        self.assertEqual(self.revoke(self.client_a,self.csrf_a,own).status_code,404)
        others=next(x["sessionId"] for x in self.listing(
            self.client_a,self.csrf_a).get_json()["sessions"] if not x["current"])
        self.assertEqual(self.revoke(self.client_a,self.csrf_a,others,
            origin="https://attacker.invalid").status_code,403)
        self.assertEqual(self.revoke(self.client_a,self.csrf_b,others).status_code,403)
        self.assertEqual(self.client_a2.get("/api/identity/session",base_url=ORIGIN).status_code,200)


class SessionsDisabledDefaultTests(unittest.TestCase):
    def test_no_schema_and_routes_when_feature_off(self):
        with tempfile.TemporaryDirectory(prefix="edgepilot-session-disabled-") as tmp:
            with patch.dict(os.environ,{
                "EDGE_DB_PATH":tmp+"/edgepilot.db",
                "EDGE_TENANT_SCHEMA_PREPARE":"true",
                "EDGE_IDENTITY_AUTH_ENABLED":"true",
                "EDGE_TENANT_SESSION_CONTROLS_ENABLED":"false",
                "EDGE_AUTOMATION_WORKER_ENABLED":"false"
            }):
                import app
                mod=importlib.reload(app)
                self.assertIsNone(mod.tenant_session_manager)
                self.assertEqual(mod.app.test_client().get(
                    "/api/identity/sessions",base_url=ORIGIN).status_code,404)
                with sqlite3.connect(tmp+"/edgepilot.db") as db:
                    self.assertFalse(db.execute("""SELECT 1 FROM sqlite_master
                        WHERE name='tenant_session_control_events'""").fetchone())
        import app
        importlib.reload(app)


if __name__=="__main__":
    unittest.main()
