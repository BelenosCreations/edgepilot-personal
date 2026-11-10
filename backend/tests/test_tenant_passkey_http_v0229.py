"""v0.2.29 gated WebAuthn HTTP ceremonies; all credentials synthetic.

The real py_webauthn verifiers are stubbed ONLY in unit tests to exercise
HTTP routing and tenant boundary behavior. This does not prove device biometrics.
"""
import base64
import importlib
import os
import tempfile
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from engine import tenant_passkeys, tenant_foundation

HOST="https://edgepilot.example.test"
ORIGIN={"Origin":HOST}
PW_A="strong-example-private-password-for-user-a"
PW_B="strong-example-private-password-for-user-b"


def b64url(data):
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


class PasskeyHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="edgepilot-v029-http-")
        self.env=patch.dict(os.environ,{
            "EDGE_DB_PATH":self.temp.name+"/edgepilot.db",
            "EDGE_TENANT_SCHEMA_PREPARE":"true",
            "EDGE_IDENTITY_AUTH_ENABLED":"true",
            "EDGE_TENANT_SIGNUP_ENABLED":"false",
            "EDGE_TENANT_PASSKEYS_ENABLED":"true",
            "EDGE_WEBAUTHN_RP_ID":"edgepilot.example.test",
            "EDGE_WEBAUTHN_ORIGIN":HOST,
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED":"false",
            "EDGE_TENANT_PUBLIC_READONLY_ENABLED":"false",
            "EDGE_AUTOMATION_WORKER_ENABLED":"false",
            "EDGE_APP_TOKEN":"legacy-identity-test-token-00000000000000000",
            "PUBLIC_API_SECRET":""
        })
        self.env.start()
        import app
        self.mod=importlib.reload(app)
        self.a=self.mod.app.test_client()
        self.b=self.mod.app.test_client()
        self.anon=self.mod.app.test_client()
        tenant=self.mod.tenant_foundation.TenantStore(str(self.mod.DB))
        self.aid=tenant.provision_user("Alice","member")
        self.bid=tenant.provision_user("Bob","member")
        self.mod.identity_store.provision(self.aid,"user_a",PW_A)
        self.mod.identity_store.provision(self.bid,"user_b",PW_B)
        self.cred_a=b"a"*32
        self.cred_b=b"b"*32

    def tearDown(self):
        self.env.stop()
        import app
        importlib.reload(app)
        self.temp.cleanup()

    def post(self,client,path,data,csrf=None):
        headers=dict(ORIGIN)
        if csrf is not None:
            headers["X-Edge-Identity-CSRF"]=csrf
        return client.post(path,base_url=HOST,headers=headers,json=data)

    def login(self,client,user,password):
        response=self.post(client,"/api/identity/login",
                           {"username":user,"password":password})
        self.assertEqual(response.status_code,200,response.get_data(as_text=True))
        return response.get_json()["csrf"]

    def enroll(self,client,csrf,raw):
        begin=self.post(client,"/api/identity/passkeys/register/options",{},csrf)
        self.assertEqual(begin.status_code,200,begin.get_data(as_text=True))
        self.assertEqual(begin.get_json()["publicKey"]["rp"]["id"],
                         "edgepilot.example.test")
        request_id=begin.get_json()["requestId"]
        data={"id":b64url(raw),"rawId":b64url(raw),"type":"public-key",
              "response":{"attestationObject":"fake","clientDataJSON":"fake"}}
        verified=SimpleNamespace(credential_id=raw,
              credential_public_key=b"synthetic-verifier-public-key",
              sign_count=0,credential_device_type="single_device",
              credential_backed_up=False)
        with patch.object(tenant_passkeys,"verify_registration_response",
                          return_value=verified) as verify:
            done=self.post(client,"/api/identity/passkeys/register/finish",
                {"requestId":request_id,"credential":data},csrf)
        self.assertEqual(done.status_code,200,done.get_data(as_text=True))
        self.assertTrue(verify.call_args.kwargs["require_user_verification"])
        self.assertEqual(verify.call_args.kwargs["expected_origin"],HOST)
        self.assertFalse(done.get_json()["tradingEnabled"])
        return request_id

    def sign_in_passkey(self,client,raw,user_id):
        started=self.post(client,"/api/identity/passkeys/authenticate/options",{})
        self.assertEqual(started.status_code,200)
        data={"id":b64url(raw),"rawId":b64url(raw),"type":"public-key",
              "response":{"authenticatorData":"fake","clientDataJSON":"fake",
                          "signature":"fake",
                          "userHandle":b64url(uuid.UUID(user_id).bytes)}}
        with patch.object(tenant_passkeys,"verify_authentication_response",
                          return_value=SimpleNamespace(new_sign_count=1,
                                                       credential_backed_up=False)) as verifier:
            done=self.post(client,"/api/identity/passkeys/authenticate/finish",
                {"requestId":started.get_json()["requestId"],"credential":data})
        self.assertTrue(verifier.call_args.kwargs["require_user_verification"])
        return done

    def test_two_identity_passkeys_issue_independent_cookies_and_no_legacy_access(self):
        acsrf=self.login(self.a,"user_a",PW_A)
        bcsrf=self.login(self.b,"user_b",PW_B)
        self.enroll(self.a,acsrf,self.cred_a)
        self.enroll(self.b,bcsrf,self.cred_b)
        self.assertEqual(self.a.get("/api/identity/passkeys",base_url=HOST,
            headers={"X-Edge-Identity-CSRF":acsrf}).get_json()["activePasskeys"],1)
        self.assertEqual(self.b.get("/api/identity/passkeys",base_url=HOST,
            headers={"X-Edge-Identity-CSRF":bcsrf}).get_json()["activePasskeys"],1)
        fresh_a=self.mod.app.test_client()
        fresh_b=self.mod.app.test_client()
        signed_a=self.sign_in_passkey(fresh_a,self.cred_a,self.aid)
        signed_b=self.sign_in_passkey(fresh_b,self.cred_b,self.bid)
        self.assertEqual(signed_a.status_code,200,signed_a.get_data(as_text=True))
        self.assertEqual(signed_b.status_code,200,signed_b.get_data(as_text=True))
        self.assertIn("HttpOnly",signed_a.headers["Set-Cookie"])
        self.assertIn("SameSite=Strict",signed_a.headers["Set-Cookie"])
        self.assertIn("Secure",signed_a.headers["Set-Cookie"])
        self.assertNotEqual(signed_a.headers["Set-Cookie"],signed_b.headers["Set-Cookie"])
        principal_a=fresh_a.get("/api/identity/session",base_url=HOST).get_json()
        principal_b=fresh_b.get("/api/identity/session",base_url=HOST).get_json()
        self.assertEqual(principal_a["user"]["userId"],self.aid)
        self.assertEqual(principal_b["user"]["userId"],self.bid)
        self.assertEqual(fresh_a.get("/api/dashboard",base_url=HOST).status_code,401)
        self.assertEqual(fresh_b.get("/api/health",base_url=HOST).status_code,401)

    def test_owner_specific_revocation_invalidates_only_its_sessions(self):
        acsrf=self.login(self.a,"user_a",PW_A)
        bcsrf=self.login(self.b,"user_b",PW_B)
        self.enroll(self.a,acsrf,self.cred_a)
        self.enroll(self.b,bcsrf,self.cred_b)
        path="/api/identity/passkeys/"+b64url(self.cred_a)
        denied=self.b.delete(path,base_url=HOST,
            headers={**ORIGIN,"X-Edge-Identity-CSRF":bcsrf})
        self.assertEqual(denied.status_code,404)
        self.assertEqual(self.b.get("/api/identity/session",base_url=HOST).status_code,200)
        revoked=self.a.delete(path,base_url=HOST,
            headers={**ORIGIN,"X-Edge-Identity-CSRF":acsrf})
        self.assertEqual(revoked.status_code,200)
        self.assertTrue(revoked.get_json()["identitySessionsRevoked"])
        self.assertEqual(self.a.get("/api/identity/session",base_url=HOST).status_code,401)
        self.assertEqual(self.b.get("/api/identity/session",base_url=HOST).status_code,200)
        failed=self.sign_in_passkey(self.mod.app.test_client(),self.cred_a,self.aid)
        self.assertEqual(failed.status_code,400)

    def test_ceremony_guards_anonymous_and_cross_origin(self):
        anonymous=self.post(self.anon,"/api/identity/passkeys/register/options",{})
        self.assertEqual(anonymous.status_code,401)
        bad=self.anon.post("/api/identity/passkeys/authenticate/options",
            base_url=HOST,headers={"Origin":"https://attacker.invalid"},json={})
        self.assertEqual(bad.status_code,403)
        self.assertEqual(self.post(self.anon,
            "/api/identity/passkeys/authenticate/finish",
            {"requestId":"fake","credential":{}}).status_code,400)
        acsrf=self.login(self.a,"user_a",PW_A)
        self.assertEqual(self.post(self.a,
            "/api/identity/passkeys/register/options",{}).status_code,403)
        self.assertEqual(self.post(self.a,
            "/api/identity/passkeys/register/options",{"role":"owner"},acsrf).status_code,400)


class PasskeyDisabledDefaultTests(unittest.TestCase):
    def test_passkeys_do_not_enable_without_explicit_configuration(self):
        with tempfile.TemporaryDirectory(prefix="edgepilot-passkey-off-") as temp:
            with patch.dict(os.environ,{
                "EDGE_DB_PATH":temp+"/edgepilot.db",
                "EDGE_TENANT_SCHEMA_PREPARE":"true",
                "EDGE_IDENTITY_AUTH_ENABLED":"true",
                "EDGE_TENANT_PASSKEYS_ENABLED":"false",
                "EDGE_AUTOMATION_WORKER_ENABLED":"false"
            }):
                import app
                mod=importlib.reload(app)
                client=mod.app.test_client()
                self.assertEqual(client.post(
                    "/api/identity/passkeys/authenticate/options",
                    base_url=HOST,headers=ORIGIN,json={}).status_code,404)
                self.assertIsNone(mod.tenant_passkey_store)
        import app
        importlib.reload(app)


if __name__=="__main__":
    unittest.main()
