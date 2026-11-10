"""v0.2.36 HTTP password rotation, two-user session isolation, default-off tests.

No real brokerage keys, account requests, orders, transfers or biometrics.
"""
import importlib
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from engine import tenant_foundation

HOST="https://edgepilot.example.test"
ORIGIN={"Origin":HOST}
PW_A="first-member-password-strong-example-2026"
PW_B="second-member-password-strong-example-2026"
PW_NEW="first-member-replacement-strong-example-2026"


class TenantPasswordChangeHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="edgepilot-v036-pw-http-")
        self.env=patch.dict(os.environ,{
            "EDGE_DB_PATH":self.temp.name+"/edgepilot.db",
            "EDGE_TENANT_SCHEMA_PREPARE":"true",
            "EDGE_IDENTITY_AUTH_ENABLED":"true",
            "EDGE_TENANT_PASSWORD_CHANGE_ENABLED":"true",
            "EDGE_TENANT_SIGNUP_ENABLED":"false",
            "EDGE_TENANT_PASSKEYS_ENABLED":"false",
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED":"false",
            "EDGE_TENANT_PUBLIC_READONLY_ENABLED":"false",
            "EDGE_AUTOMATION_WORKER_ENABLED":"false",
            "EDGE_APP_TOKEN":"legacy-only-synthetic-test-secret-0000000000000000",
            "PUBLIC_API_SECRET":"",
        })
        self.env.start()
        import app
        self.mod=importlib.reload(app)
        self.device_a=self.mod.app.test_client()
        self.device_a2=self.mod.app.test_client()
        self.device_b=self.mod.app.test_client()
        self.anon=self.mod.app.test_client()
        self.tenants=tenant_foundation.TenantStore(str(self.mod.DB))
        self.a=self.tenants.provision_user("Alice","member")
        self.b=self.tenants.provision_user("Bob","member")
        self.mod.identity_store.provision(self.a,"v036_alice",PW_A)
        self.mod.identity_store.provision(self.b,"v036_bob",PW_B)
        self.a_csrf=self.login(self.device_a,"v036_alice",PW_A)
        self.a2_csrf=self.login(self.device_a2,"v036_alice",PW_A)
        self.b_csrf=self.login(self.device_b,"v036_bob",PW_B)

    def tearDown(self):
        self.env.stop()
        import app
        importlib.reload(app)
        self.temp.cleanup()

    def login(self,client,name,password):
        response=client.post("/api/identity/login",base_url=HOST,
                             headers=ORIGIN,json={"username":name,"password":password})
        self.assertEqual(response.status_code,200,response.get_data(as_text=True))
        return response.get_json()["csrf"]

    def change(self,client,csrf,current,new,*,origin=HOST):
        return client.post("/api/identity/password/change",base_url=HOST,
            headers={"Origin":origin,"X-Edge-Identity-CSRF":csrf},
            json={"currentPassword":current,"newPassword":new})

    def test_password_change_revokes_both_phones_not_other_member(self):
        result=self.change(self.device_a,self.a_csrf,PW_A,PW_NEW)
        self.assertEqual(result.status_code,200,result.get_data(as_text=True))
        body=result.get_json()
        self.assertTrue(body["passwordChanged"])
        self.assertTrue(body["allIdentitySessionsRevoked"])
        self.assertTrue(body["mustSignInAgain"])
        self.assertFalse(body["liveTradingEnabled"])
        self.assertFalse(body["fundTransfersEnabled"])
        self.assertIn("Secure",result.headers["Set-Cookie"])
        self.assertIn("__Host-edgepilot_identity=",result.headers["Set-Cookie"])
        self.assertEqual(self.device_a.get("/api/identity/session",base_url=HOST).status_code,401)
        self.assertEqual(self.device_a2.get("/api/identity/session",base_url=HOST).status_code,401)
        self.assertEqual(self.device_b.get("/api/identity/session",base_url=HOST).status_code,200)
        rejected=self.device_a.post("/api/identity/login",base_url=HOST,
                    headers=ORIGIN,json={"username":"v036_alice","password":PW_A})
        self.assertEqual(rejected.status_code,401)
        newly=self.login(self.device_a,"v036_alice",PW_NEW)
        self.assertGreater(len(newly),24)
        self.assertEqual(self.device_a.get("/api/dashboard",base_url=HOST).status_code,401)
        with sqlite3.connect(self.mod.DB) as con:
            self.assertEqual(con.execute("""SELECT COUNT(*) FROM tenant_password_change_events
                WHERE user_id=?""",(self.a,)).fetchone()[0],1)
            self.assertEqual(con.execute("""SELECT COUNT(*) FROM tenant_password_change_events
                WHERE user_id=?""",(self.b,)).fetchone()[0],0)

    def test_origin_csrf_and_overposting_are_rejected(self):
        origin=self.change(self.device_a,self.a_csrf,PW_A,PW_NEW,
                           origin="https://evil.invalid")
        self.assertEqual(origin.status_code,403)
        mismatched=self.change(self.device_a,self.b_csrf,PW_A,PW_NEW)
        self.assertEqual(mismatched.status_code,403)
        no_session=self.change(self.anon,self.a_csrf,PW_A,PW_NEW)
        self.assertEqual(no_session.status_code,401)
        extra=self.device_a.post("/api/identity/password/change",base_url=HOST,
            headers={**ORIGIN,"X-Edge-Identity-CSRF":self.a_csrf},
            json={"currentPassword":PW_A,"newPassword":PW_NEW,"userId":self.b})
        self.assertEqual(extra.status_code,400)
        wrong=self.change(self.device_a,self.a_csrf,"wrong-current-password",PW_NEW)
        self.assertEqual(wrong.status_code,400)
        self.assertEqual(self.device_a.get("/api/identity/session",base_url=HOST).status_code,200)
        self.assertEqual(self.device_b.get("/api/identity/session",base_url=HOST).status_code,200)
        self.assertEqual(self.device_a.get("/api/health",base_url=HOST).status_code,401)
        self.assertNotIn(PW_A,wrong.get_data(as_text=True))
        self.assertNotIn(PW_NEW,wrong.get_data(as_text=True))

    def test_wrong_password_rate_limit_is_per_owner(self):
        for i in range(5):
            self.assertEqual(self.change(self.device_a,self.a_csrf,
                "wrong-old-password",PW_NEW).status_code,400)
        blocked=self.change(self.device_a,self.a_csrf,PW_A,PW_NEW)
        self.assertEqual(blocked.status_code,429)
        self.assertEqual(self.change(self.device_b,self.b_csrf,PW_B,
             "bob-new-password-strong-example-2026").status_code,200)


class PasswordChangeDefaultOffHttpTests(unittest.TestCase):
    def test_route_and_schema_are_disabled_by_default(self):
        with tempfile.TemporaryDirectory(prefix="edgepilot-v036-pw-disabled-") as tmp:
            with patch.dict(os.environ,{
                "EDGE_DB_PATH":tmp+"/edgepilot.db",
                "EDGE_TENANT_SCHEMA_PREPARE":"true",
                "EDGE_IDENTITY_AUTH_ENABLED":"true",
                "EDGE_TENANT_PASSWORD_CHANGE_ENABLED":"false",
                "EDGE_AUTOMATION_WORKER_ENABLED":"false",
            }):
                import app
                mod=importlib.reload(app)
                self.assertIsNone(mod.tenant_password_manager)
                response=mod.app.test_client().post("/api/identity/password/change",
                   base_url=HOST,headers=ORIGIN,
                   json={"currentPassword":PW_A,"newPassword":PW_NEW})
                self.assertEqual(response.status_code,404)
                with sqlite3.connect(tmp+"/edgepilot.db") as con:
                    self.assertFalse(con.execute("""SELECT 1 FROM sqlite_master
                        WHERE name='tenant_password_change_events'""").fetchone())
        import app
        importlib.reload(app)

    def test_password_manager_cannot_be_enabled_without_identity(self):
        with tempfile.TemporaryDirectory(prefix="edgepilot-v036-pw-noid-") as tmp:
            with patch.dict(os.environ,{
                "EDGE_DB_PATH":tmp+"/edgepilot.db",
                "EDGE_TENANT_SCHEMA_PREPARE":"true",
                "EDGE_IDENTITY_AUTH_ENABLED":"false",
                "EDGE_TENANT_PASSWORD_CHANGE_ENABLED":"true",
                "EDGE_AUTOMATION_WORKER_ENABLED":"false",
            }):
                import app
                with self.assertRaisesRegex(RuntimeError,"requires identity"):
                    importlib.reload(app)
        import app
        importlib.reload(app)


if __name__=="__main__":
    unittest.main()
