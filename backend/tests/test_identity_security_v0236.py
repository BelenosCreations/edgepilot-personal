"""v0.2.36 signed-in EdgePilot security actions, synthetic identities only.

Old-password step-up prevents a stolen identity cookie/CSRF alone from
changing the password or invalidating other devices. No Public requests.
"""
import importlib
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from engine import tenant_foundation, identity_auth

HOST="https://edgepilot.example.test"
HEADERS={"Origin":HOST}
A_OLD="long-valid-alice-password-for-v036"
A_NEW="fresh-unique-alice-password-for-v036"
B_OLD="long-valid-bob-password-for-v036"


class IdentitySecurityRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="edgepilot-v036-id-security-")
        self.db=self.temp.name+"/tenant.db"
        tenant_foundation.setup(self.db)
        identity_auth.setup(self.db)
        self.tenant=tenant_foundation.TenantStore(self.db)
        self.a=self.tenant.provision_user("Alice","member")
        self.b=self.tenant.provision_user("Bob","member")
        self.store=identity_auth.IdentityStore(self.db)
        self.store.provision(self.a,"security_alice",A_OLD)
        self.store.provision(self.b,"security_bob",B_OLD)
        self.a1=self.store.authenticate("security_alice",A_OLD,"phone-a")
        self.a2=self.store.authenticate("security_alice",A_OLD,"phone-a2")
        self.b1=self.store.authenticate("security_bob",B_OLD,"phone-b")

    def tearDown(self):
        self.temp.cleanup()

    def test_change_password_revokes_both_alice_sessions_not_bob(self):
        changed=self.store.change_password_from_session(
            self.a1["token"],self.a1["csrf"],A_OLD,A_NEW)
        self.assertTrue(changed["ok"])
        self.assertTrue(changed["allSessionsSignedOut"])
        self.assertFalse(changed["passkeysRevoked"])
        self.assertFalse(changed["publicConnectionsChanged"])
        self.assertFalse(changed["tradingEnabled"])
        self.assertIsNone(self.store.principal(self.a1["token"]))
        self.assertIsNone(self.store.principal(self.a2["token"]))
        self.assertIsNotNone(self.store.principal(self.b1["token"]))
        self.assertIsNone(self.store.authenticate("security_alice",A_OLD,"phone-a"))
        self.assertIsNotNone(self.store.authenticate("security_alice",A_NEW,"phone-a"))
        with sqlite3.connect(self.db) as db:
            record=db.execute("SELECT action,user_id FROM tenant_identity_security_events").fetchall()
            self.assertEqual(record,[("PASSWORD_CHANGED",self.a)])
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM tenant_identity_security_events")

    def test_signout_all_requires_current_password_and_spares_other_user(self):
        with self.assertRaises(PermissionError):
            self.store.sign_out_everywhere_from_session(
                self.a1["token"],self.a1["csrf"],B_OLD)
        self.assertIsNotNone(self.store.principal(self.a2["token"]))
        result=self.store.sign_out_everywhere_from_session(
            self.a1["token"],self.a1["csrf"],A_OLD)
        self.assertTrue(result["allSessionsSignedOut"])
        self.assertIsNone(self.store.principal(self.a1["token"]))
        self.assertIsNone(self.store.principal(self.a2["token"]))
        self.assertIsNotNone(self.store.principal(self.b1["token"]))
        # A passkey is retained; a new password login also works.
        self.assertIsNotNone(self.store.authenticate("security_alice",A_OLD,"phone-c"))
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("""SELECT action FROM tenant_identity_security_events
                WHERE user_id=?""",(self.a,)).fetchall(),[("SESSIONS_REVOKED",)])

    def test_security_actions_recheck_revoked_session_at_write_time(self):
        old=self.store._verify_password_for_security_action
        def revoke_after_preflight(token,csrf,password):
            result=old(token,csrf,password)
            self.store.revoke(token)
            return result
        with patch.object(self.store,"_verify_password_for_security_action",
                          side_effect=revoke_after_preflight):
            with self.assertRaises(PermissionError):
                self.store.change_password_from_session(
                    self.a1["token"],self.a1["csrf"],A_OLD,A_NEW)
        self.assertIsNotNone(self.store.authenticate("security_alice",A_OLD,"phone-c"))
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM tenant_identity_security_events").fetchone()[0],0)

    def test_wrong_passwords_budgeted_without_cross_owner_lockout(self):
        for _ in range(identity_auth.MAX_SECURITY_ATTEMPTS):
            with self.assertRaises(PermissionError):
                self.store.sign_out_everywhere_from_session(
                    self.a1["token"],self.a1["csrf"],"incorrect-password-value")
        with self.assertRaises(PermissionError):
            self.store.sign_out_everywhere_from_session(
                self.a1["token"],self.a1["csrf"],A_OLD)
        self.assertIsNotNone(self.store.principal(self.a1["token"]))
        self.assertTrue(self.store.sign_out_everywhere_from_session(
            self.b1["token"],self.b1["csrf"],B_OLD)["allSessionsSignedOut"])

    def test_rejects_invalid_new_password_and_wrong_csrf(self):
        with self.assertRaises(ValueError):
            self.store.change_password_from_session(
                self.a1["token"],self.a1["csrf"],A_OLD,"short")
        with self.assertRaises(ValueError):
            self.store.change_password_from_session(
                self.a1["token"],self.a1["csrf"],A_OLD,A_OLD)
        with self.assertRaises(PermissionError):
            self.store.change_password_from_session(
                self.a1["token"],self.b1["csrf"],A_OLD,A_NEW)
        self.assertIsNotNone(self.store.principal(self.a1["token"]))


class IdentitySecurityHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="edgepilot-v036-http-")
        self.env=patch.dict(os.environ,{
            "EDGE_DB_PATH":self.temp.name+"/site.db",
            "EDGE_TENANT_SCHEMA_PREPARE":"true",
            "EDGE_IDENTITY_AUTH_ENABLED":"true",
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED":"false",
            "EDGE_AUTOMATION_WORKER_ENABLED":"false",
            "PUBLIC_API_SECRET":"",
            "EDGE_APP_TOKEN":"synthetic-legacy-owner-key-v036-not-for-tenants-00000000"
        })
        self.env.start()
        import app
        self.mod=importlib.reload(app)
        self.a1=self.mod.app.test_client()
        self.a2=self.mod.app.test_client()
        self.b=self.mod.app.test_client()
        store=tenant_foundation.TenantStore(str(self.mod.DB))
        owner_a=store.provision_user("Alice","member")
        owner_b=store.provision_user("Bob","member")
        self.mod.identity_store.provision(owner_a,"http_alice",A_OLD)
        self.mod.identity_store.provision(owner_b,"http_bob",B_OLD)
        self.csrf_a=self._login(self.a1,"http_alice",A_OLD)
        self.csrf_a2=self._login(self.a2,"http_alice",A_OLD)
        self.csrf_b=self._login(self.b,"http_bob",B_OLD)

    def tearDown(self):
        self.env.stop()
        import app
        importlib.reload(app)
        self.temp.cleanup()

    def _login(self,client,username,password):
        res=client.post("/api/identity/login",base_url=HOST,headers=HEADERS,
                        json={"username":username,"password":password})
        self.assertEqual(res.status_code,200,res.get_data(as_text=True))
        return res.get_json()["csrf"]

    def _security(self,client,path,data,csrf=None):
        headers={**HEADERS}
        if csrf is not None: headers["X-Edge-Identity-CSRF"]=csrf
        return client.post("/api/identity/security/"+path,
                           base_url=HOST,headers=headers,json=data)

    def test_change_password_ends_only_alice_sessions_and_requires_relogin(self):
        data={"currentPassword":A_OLD,"newPassword":A_NEW}
        self.assertEqual(self._security(self.a1,"change-password",data).status_code,403)
        wrong=self._security(self.a1,"change-password",data,self.csrf_b)
        self.assertEqual(wrong.status_code,403)
        result=self._security(self.a1,"change-password",data,self.csrf_a)
        self.assertEqual(result.status_code,200,result.get_data(as_text=True))
        self.assertIn("HttpOnly",result.headers["Set-Cookie"])
        self.assertNotIn(A_OLD,result.get_data(as_text=True))
        self.assertNotIn(A_NEW,result.get_data(as_text=True))
        self.assertEqual(self.a1.get("/api/identity/session",base_url=HOST).status_code,401)
        self.assertEqual(self.a2.get("/api/identity/session",base_url=HOST).status_code,401)
        self.assertEqual(self.b.get("/api/identity/session",base_url=HOST).status_code,200)
        self._login(self.a1,"http_alice",A_NEW)

    def test_sign_out_everywhere_step_up_and_no_user_spoof(self):
        path="sign-out-everywhere"
        self.assertEqual(self._security(self.a1,path,{"currentPassword":B_OLD},
                                        self.csrf_a).status_code,403)
        self.assertEqual(self._security(self.a1,path,
                                        {"currentPassword":A_OLD,"userId":"other"},
                                        self.csrf_a).status_code,400)
        self.assertEqual(self.a2.get("/api/identity/session",base_url=HOST).status_code,200)
        res=self._security(self.a1,path,{"currentPassword":A_OLD},self.csrf_a)
        self.assertEqual(res.status_code,200)
        self.assertTrue(res.get_json()["allSessionsSignedOut"])
        self.assertFalse(res.get_json()["passkeysRevoked"])
        self.assertFalse(res.get_json()["publicConnectionsChanged"])
        self.assertEqual(self.a2.get("/api/identity/session",base_url=HOST).status_code,401)
        self.assertEqual(self.b.get("/api/identity/session",base_url=HOST).status_code,200)

    def test_origin_csrf_and_bad_password_format_denied(self):
        evil=self.a1.post("/api/identity/security/sign-out-everywhere",
            base_url=HOST,headers={"Origin":"https://evil.invalid",
                                   "X-Edge-Identity-CSRF":self.csrf_a},
            json={"currentPassword":A_OLD})
        self.assertEqual(evil.status_code,403)
        self.assertEqual(self._security(self.a1,"change-password",
            {"currentPassword":A_OLD,"newPassword":"too-short"},self.csrf_a).status_code,400)
        self.assertEqual(self.a1.get("/api/identity/session",base_url=HOST).status_code,200)


class IdentitySecurityUiTests(unittest.TestCase):
    def test_ui_password_inputs_never_persist_credentials_and_clear_sessions(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[2]
        html=(root/"backend/static/identity.html").read_text(encoding="utf-8")
        js=(root/"backend/static/assets/identity.js").read_text(encoding="utf-8")
        for marker in ("changeIdentityPasswordForm","signOutEverywhereForm",
                       "securityCurrentPassword","securityNewPassword",
                       "securitySignOutPassword"):
            self.assertIn('id="'+marker+'"',html)
        self.assertIn('"/security/change-password"',js)
        self.assertIn('"/security/sign-out-everywhere"',js)
        self.assertIn("verifiedSecurityResponse(result)",js)
        self.assertIn('result.allSessionsSignedOut !== true',js)
        self.assertIn('result.passkeysRevoked !== false',js)
        self.assertIn("showLoggedOut();",js)
        self.assertIn('el("securityCurrentPassword").value = "";',js)
        self.assertIn('el("securityNewPassword").value = "";',js)
        self.assertIn('el("securitySignOutPassword").value = "";',js)
        self.assertNotIn("localStorage",js)
        self.assertNotIn("sessionStorage",js)
        self.assertNotIn("innerHTML",js)


if __name__=="__main__":
    unittest.main()
