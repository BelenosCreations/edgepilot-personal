"""WebAuthn tenant repository regression tests, all local fake credentials.

Successful crypto verification is replaced with a test stub ONLY in the
unit test process; actual production module always calls py_webauthn.
No actual credentials, biometrics, Public calls, bank data or active routes.
"""
import base64
import json
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from engine import identity_auth, tenant_foundation, tenant_passkeys, tenant_route_audit

ROOT=Path(__file__).resolve().parents[2]
NOW=1_900_000_000
ORIGIN="https://edgepilot.example.test"
RP="edgepilot.example.test"


def b64url(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


class TenantPasskeyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="edgepilot-passkey-")
        self.db=self.tmp.name+"/tenants.db"
        tenant_foundation.setup(self.db)
        identity_auth.setup(self.db)
        tenant_passkeys.setup(self.db)
        self.tenants=tenant_foundation.TenantStore(self.db)
        self.users=[self.tenants.provision_user("Test A"),self.tenants.provision_user("Test B")]
        self.identities=identity_auth.IdentityStore(self.db)
        self.identities.provision(self.users[0],"owner_a","password-one-is-long-and-private")
        self.identities.provision(self.users[1],"owner_b","password-two-is-long-and-private")
        self.sessions=[
            self.identities.authenticate("owner_a","password-one-is-long-and-private","source1",now=NOW),
            self.identities.authenticate("owner_b","password-two-is-long-and-private","source2",now=NOW)
        ]
        self.store=tenant_passkeys.TenantPasskeyStore(
            self.db,self.identities,rp_id=RP,expected_origin=ORIGIN)
        self.cred_ids=[b"a"*32,b"b"*32]

    def tearDown(self):
        self.tmp.cleanup()

    def reg(self,index=0,credential=None):
        identity=self.sessions[index]
        started=self.store.begin_registration(identity["token"],identity["csrf"],now=NOW)
        if credential is None:credential=self.cred_ids[index]
        response={"id":b64url(credential),"rawId":b64url(credential),
                  "type":"public-key","response":{"attestationObject":"fake",
                                                     "clientDataJSON":"fake"}}
        verification=SimpleNamespace(
            credential_id=credential,credential_public_key=b"synthetic-test-public-key",
            sign_count=0,credential_device_type="single_device",
            credential_backed_up=False)
        with patch.object(tenant_passkeys,"verify_registration_response",
                          return_value=verification) as verified:
            result=self.store.finish_registration(identity["token"],identity["csrf"],
                                                  started["requestId"],response,now=NOW)
        self.assertFalse(result["biometricsStoredOnServer"])
        self.assertFalse(result["tradingEnabled"])
        self.assertEqual(verified.call_args.kwargs["expected_origin"],ORIGIN)
        self.assertEqual(verified.call_args.kwargs["expected_rp_id"],RP)
        self.assertTrue(verified.call_args.kwargs["require_user_verification"])
        return started

    def login(self,credential=b"a"*32,request_id=None,user_id=None,*,now=NOW):
        if request_id is None:
            request_id=self.store.begin_authentication(now=now)["requestId"]
        response={"id":b64url(credential),"rawId":b64url(credential),"type":"public-key",
                  "response":{"authenticatorData":"fake","clientDataJSON":"fake",
                              "signature":"fake",
                              "userHandle":b64url(uuid.UUID(user_id).bytes) if user_id else None}}
        with patch.object(tenant_passkeys,"verify_authentication_response",
                          return_value=SimpleNamespace(new_sign_count=1,
                                                       credential_backed_up=False)) as verified:
            issued=self.store.finish_authentication(request_id,response,now=now)
        self.assertEqual(verified.call_args.kwargs["expected_origin"],ORIGIN)
        self.assertTrue(verified.call_args.kwargs["require_user_verification"])
        return issued

    def test_password_authenticated_registration_only_and_scoped_login(self):
        with self.assertRaises(tenant_passkeys.PasskeyDenied):
            self.store.begin_registration("not-a-session","not-csrf",now=NOW)
        started=self.reg()
        self.assertIn("publicKey",started)
        self.assertNotIn("secret",json.dumps(started).lower())
        with sqlite3.connect(self.db) as conn:
            stored=conn.execute("""SELECT user_id,public_key,sign_count
                FROM tenant_passkey_credentials""").fetchone()
        self.assertEqual(stored[0],self.users[0])
        self.assertEqual(stored[1],b"synthetic-test-public-key")
        self.assertEqual(stored[2],0)
        issued=self.login(user_id=self.users[0])
        principal=self.identities.principal(issued["token"],issued["csrf"],now=NOW)
        self.assertEqual(principal["user_id"],self.users[0])
        self.assertIsNone(self.identities.principal(issued["token"],self.sessions[1]["csrf"],now=NOW))
        self.assertEqual(issued["scope"],"identity_only_no_broker_access")
        self.assertIsNone(self.identities.principal(self.sessions[1]["token"],issued["csrf"],now=NOW))

    def test_registration_challenge_needs_same_identity_and_single_use(self):
        started=self.store.begin_registration(
            self.sessions[0]["token"],self.sessions[0]["csrf"],now=NOW)
        with self.assertRaises(tenant_passkeys.PasskeyDenied):
            self.store.finish_registration(
                self.sessions[1]["token"],self.sessions[1]["csrf"],started["requestId"],{},
                now=NOW)
        with self.assertRaises(tenant_passkeys.PasskeyDenied):
            self.store.finish_registration(
                self.sessions[0]["token"],self.sessions[0]["csrf"],started["requestId"],{},
                now=NOW)
        self.assertEqual(self.store.redacted_own_status(
            self.sessions[0]["token"],self.sessions[0]["csrf"],now=NOW)["activePasskeys"],0)

    def test_passkey_login_wrong_user_handle_denied_before_verifier(self):
        self.reg(0)
        req=self.store.begin_authentication(now=NOW)["requestId"]
        with patch.object(tenant_passkeys,"verify_authentication_response") as verifier:
            with self.assertRaises(tenant_passkeys.PasskeyDenied):
                self.store.finish_authentication(req,{"id":b64url(self.cred_ids[0]),
                   "rawId":b64url(self.cred_ids[0]),"response":{
                   "userHandle":b64url(uuid.UUID(self.users[1]).bytes)}},now=NOW)
            verifier.assert_not_called()
        with self.assertRaises(tenant_passkeys.PasskeyDenied):
            self.store.finish_authentication(req,{},now=NOW)

    def test_cross_owner_revocation_and_isolation(self):
        self.reg(0)
        self.reg(1)
        with self.assertRaises(tenant_passkeys.PasskeyDenied):
            self.store.revoke_for_user(
                self.sessions[1]["token"],self.sessions[1]["csrf"],self.cred_ids[0],now=NOW)
        self.assertEqual(self.store.redacted_own_status(
            self.sessions[1]["token"],self.sessions[1]["csrf"],now=NOW)["activePasskeys"],1)
        revocation=self.store.revoke_for_user(
            self.sessions[0]["token"],self.sessions[0]["csrf"],self.cred_ids[0],
            now=NOW)
        self.assertTrue(revocation["revoked"])
        self.assertTrue(revocation["identitySessionsRevoked"])
        self.assertIsNone(self.identities.principal(self.sessions[0]["token"],now=NOW))
        self.assertIsNotNone(self.identities.principal(self.sessions[1]["token"],now=NOW))
        with self.assertRaises(tenant_passkeys.PasskeyDenied):
            self.login(self.cred_ids[0],user_id=self.users[0])
        b=self.login(self.cred_ids[1],user_id=self.users[1])
        self.assertEqual(self.identities.principal(b["token"],b["csrf"],now=NOW)["user_id"],self.users[1])

    def test_registered_passkey_is_unique_across_users(self):
        self.reg(0)
        with self.assertRaises(tenant_passkeys.PasskeyDenied):
            self.reg(1,credential=self.cred_ids[0])
        self.assertEqual(self.store.redacted_own_status(
            self.sessions[1]["token"],self.sessions[1]["csrf"],now=NOW)["activePasskeys"],0)

    def test_expired_request_and_challenge_quota(self):
        self.reg(0)
        old=self.store.begin_authentication(now=NOW)
        with self.assertRaises(tenant_passkeys.PasskeyDenied):
            self.login(self.cred_ids[0],request_id=old["requestId"],
                       now=NOW+tenant_passkeys.CHALLENGE_TTL_SECONDS)
        with patch.object(tenant_passkeys,"MAX_PENDING_CHALLENGES",2):
            self.store.begin_authentication(now=NOW)
            self.store.begin_authentication(now=NOW)
            with self.assertRaises(tenant_passkeys.PasskeyDenied):
                self.store.begin_authentication(now=NOW)
        with self.assertRaises(tenant_passkeys.PasskeyDenied):
            self.login(self.cred_ids[0],request_id=old["requestId"],now=NOW)

    def test_failed_verification_consumes_challenge_and_no_session(self):
        self.reg(0)
        req=self.store.begin_authentication(now=NOW)["requestId"]
        fake={"id":b64url(self.cred_ids[0]),"rawId":b64url(self.cred_ids[0]),
              "response":{"authenticatorData":"bad"}}
        with self.assertRaises(tenant_passkeys.PasskeyDenied):
            self.store.finish_authentication(req,fake,now=NOW)
        with self.assertRaises(tenant_passkeys.PasskeyDenied):
            self.login(self.cred_ids[0],request_id=req,now=NOW)
        self.assertIsNone(self.identities.principal("made-up-passkey-session",now=NOW))

    def test_disabled_user_cannot_login_or_register(self):
        self.reg(0)
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE tenant_users SET disabled_at='2026-11-10' WHERE user_id=?",
                         (self.users[0],))
        with self.assertRaises(tenant_passkeys.PasskeyDenied):
            self.login(self.cred_ids[0],user_id=self.users[0])
        with self.assertRaises(tenant_passkeys.PasskeyDenied):
            self.store.begin_registration(self.sessions[0]["token"],self.sessions[0]["csrf"],now=NOW)
        self.assertIsNotNone(self.identities.principal(self.sessions[1]["token"],now=NOW))

    def test_strict_origin_binding_and_id_configuration(self):
        for rp,origin in (
            ("evil.example.test",ORIGIN),
            (RP,"http://"+RP),
            (RP,ORIGIN+"/path"),
            (RP,ORIGIN+":443"),
            (RP,"https://user@"+RP),
            ("a..b","https://a..b"),
        ):
            with self.assertRaises(ValueError):
                tenant_passkeys.TenantPasskeyStore(
                    self.db,self.identities,rp_id=rp,expected_origin=origin)

    def test_oversized_response_denied_without_credential_leak(self):
        self.reg(0)
        req=self.store.begin_authentication(now=NOW)["requestId"]
        with self.assertRaises(tenant_passkeys.PasskeyDenied):
            self.store.finish_authentication(req,{"id":"x"*18000},now=NOW)

    def test_no_legacy_api_or_live_worker_import(self):
        app=(ROOT/"backend/app.py").read_text()
        worker=(ROOT/"backend/engine/automation_worker.py").read_text()
        module="tenant_passkeys"
        self.assertIn(module,app)
        self.assertIn("EDGE_TENANT_PASSKEYS_ENABLED\u0027,\u0027false\u0027",app)
        self.assertNotIn(module,worker)
        self.assertFalse(tenant_route_audit.inspect_sources(app,worker)["crossAccountProductionCutoverAllowed"])
        with self.assertRaises(tenant_route_audit.ApiBoundaryError):
            tenant_route_audit.inspect_sources(
                app,worker+"\nfrom engine import tenant_passkeys\n")


if __name__=="__main__":
    unittest.main()
