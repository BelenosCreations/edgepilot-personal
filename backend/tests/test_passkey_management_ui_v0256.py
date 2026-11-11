"""v0.2.56: real authenticated HTTP tests for passkey management and UI state.

Fixtures use synthetic credentials with mocked cryptographic registration, not
physical biometric data. No Public calls, real secrets, fund transfers, or
production service changes are permitted.
"""
import base64
import importlib
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from engine import tenant_foundation, tenant_passkeys

HOST = "https://edgepilot.example.test"
PW_A = "Synthetic-A-Long-Password-For-Testing-2026"
PW_B = "Synthetic-B-Long-Password-For-Testing-2026"
ROOT = Path(__file__).resolve().parents[2]


def token(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class PasskeyManagementHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="edge-passkey-manage-")
        self.env = patch.dict(os.environ, {
            "EDGE_DB_PATH": self.temp.name + "/edgepilot.db",
            "EDGE_ISOLATED_STAGING": "false",
            "EDGE_TENANT_SCHEMA_PREPARE": "true",
            "EDGE_IDENTITY_AUTH_ENABLED": "true",
            "EDGE_TENANT_PASSKEYS_ENABLED": "true",
            "EDGE_TENANT_SIGNUP_ENABLED": "false",
            "EDGE_WEBAUTHN_RP_ID": "edgepilot.example.test",
            "EDGE_WEBAUTHN_ORIGIN": HOST,
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED": "false",
            "EDGE_TENANT_PUBLIC_READONLY_ENABLED": "false",
            "EDGE_TENANT_ACCOUNT_READS_ENABLED": "false",
            "EDGE_AUTOMATION_WORKER_ENABLED": "false",
            "ENABLE_LIVE_ORDERS": "false",
            "EDGE_APP_TOKEN": "offline-legacy-token-only-for-unit-tests-not-live",
            "PUBLIC_API_SECRET": "",
        })
        self.env.start()
        import app
        self.mod = importlib.reload(app)
        self.a = self.mod.app.test_client()
        self.b = self.mod.app.test_client()
        self.anon = self.mod.app.test_client()
        tenant = tenant_foundation.TenantStore(str(self.mod.DB))
        aid = tenant.provision_user("Synthetic A", "member")
        bid = tenant.provision_user("Synthetic B", "member")
        self.mod.identity_store.provision(aid, "passkey_test_a", PW_A)
        self.mod.identity_store.provision(bid, "passkey_test_b", PW_B)
        self.acsrf = self.login(self.a, "passkey_test_a", PW_A)
        self.bcsrf = self.login(self.b, "passkey_test_b", PW_B)

    def tearDown(self):
        self.env.stop()
        import app
        importlib.reload(app)
        self.temp.cleanup()

    def post(self, client, path, data, csrf=None):
        h = {"Origin": HOST}
        if csrf is not None:
            h["X-Edge-Identity-CSRF"] = csrf
        return client.post(path, base_url=HOST, headers=h, json=data)

    def login(self, client, name, password):
        response = self.post(client, "/api/identity/login",
                             {"username": name, "password": password})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()["csrf"]

    def listing(self, client, csrf):
        return client.get("/api/identity/passkeys", base_url=HOST,
                          headers={"X-Edge-Identity-CSRF": csrf})

    def enroll(self, client, csrf, raw, *, device="single_device", backed=False):
        begin = self.post(client, "/api/identity/passkeys/register/options",
                          {}, csrf)
        self.assertEqual(begin.status_code, 200, begin.get_data(as_text=True))
        credential = {
            "id": token(raw), "rawId": token(raw), "type": "public-key",
            "response": {"clientDataJSON": "offline-fixture",
                         "attestationObject": "offline-fixture"},
        }
        verified = SimpleNamespace(
            credential_id=raw,
            credential_public_key=b"synthetic-not-exportable-secret",
            sign_count=0, credential_device_type=device,
            credential_backed_up=backed)
        with patch.object(tenant_passkeys, "verify_registration_response",
                          return_value=verified):
            done = self.post(
                client, "/api/identity/passkeys/register/finish",
                {"requestId": begin.get_json()["requestId"],
                 "credential": credential},
                csrf)
        self.assertEqual(done.status_code, 200, done.get_data(as_text=True))
        return token(raw)

    def test_status_empty_then_multiple_and_only_current_user(self):
        initial = self.listing(self.a, self.acsrf)
        self.assertEqual(initial.status_code, 200)
        initial_data = initial.get_json()
        self.assertEqual(initial_data["activePasskeys"], 0)
        self.assertEqual(initial_data["passkeys"], [])
        self.assertFalse(initial_data["brokerAccessAuthorized"])
        self.assertFalse(initial_data["tradingEnabled"])
        self.assertFalse(initial_data["biometricsStoredOnServer"])
        self.assertFalse(initial_data["deviceIdentifiersStored"])

        key_a1 = self.enroll(self.a, self.acsrf, b"a" * 32)
        key_a2 = self.enroll(self.a, self.acsrf, b"c" * 32,
                             device="multi_device", backed=True)
        key_b = self.enroll(self.b, self.bcsrf, b"b" * 32)
        data_a = self.listing(self.a, self.acsrf).get_json()
        data_b = self.listing(self.b, self.bcsrf).get_json()
        self.assertEqual(data_a["activePasskeys"], 2)
        self.assertEqual(data_b["activePasskeys"], 1)
        self.assertEqual([x["credentialId"] for x in data_a["passkeys"]],
                         [key_a1, key_a2])
        self.assertEqual([x["credentialId"] for x in data_b["passkeys"]],
                         [key_b])
        self.assertTrue(data_a["passkeys"][1]["backedUp"])
        self.assertEqual(data_a["passkeys"][1]["deviceType"], "multi_device")
        self.assertTrue(all(isinstance(x["createdAt"], int)
                            for x in data_a["passkeys"]))
        self.assertEqual(set(data_a["passkeys"][0]),
                         {"credentialId", "createdAt", "deviceType", "backedUp"})
        # User-controlled query strings cannot change the signed-in principal.
        guessed = self.b.get("/api/identity/passkeys?userId=alice",
                             base_url=HOST,
                             headers={"X-Edge-Identity-CSRF": self.bcsrf})
        self.assertEqual(guessed.get_json()["passkeys"],
                         data_b["passkeys"])
        self.assertNotIn(key_b, str(data_a))
        self.assertNotIn(key_a1, str(data_b))
        self.assertNotIn("synthetic-not-exportable-secret", str(data_a))

    def test_remove_only_owned_passkey_revokes_own_sessions(self):
        key_a = self.enroll(self.a, self.acsrf, b"a" * 32)
        self.enroll(self.b, self.bcsrf, b"b" * 32)
        path = "/api/identity/passkeys/" + key_a
        forbidden = self.b.delete(path, base_url=HOST,
                                   headers={"Origin": HOST,
                                            "X-Edge-Identity-CSRF": self.bcsrf})
        self.assertEqual(forbidden.status_code, 404)
        self.assertEqual(self.listing(self.a, self.acsrf).get_json()
                         ["activePasskeys"], 1)
        self.assertEqual(self.listing(self.b, self.bcsrf).get_json()
                         ["activePasskeys"], 1)
        revoked = self.a.delete(path, base_url=HOST,
                                headers={"Origin": HOST,
                                         "X-Edge-Identity-CSRF": self.acsrf})
        self.assertEqual(revoked.status_code, 200)
        self.assertTrue(revoked.get_json()["revoked"])
        self.assertTrue(revoked.get_json()["identitySessionsRevoked"])
        self.assertTrue(revoked.get_json()["otherUsersUnaffected"])
        self.assertEqual(self.listing(self.a, self.acsrf).status_code, 401)
        self.assertEqual(self.listing(self.b, self.bcsrf).status_code, 200)
        second = self.login(self.a, "passkey_test_a", PW_A)
        self.assertEqual(self.listing(self.a, second).get_json()["passkeys"], [])
        self.assertEqual(self.listing(self.b, self.bcsrf).get_json()
                         ["activePasskeys"], 1)

    def test_incorrect_csrf_cross_origin_and_anonymous_listing_denied(self):
        self.enroll(self.a, self.acsrf, b"a" * 32)
        self.assertEqual(self.listing(self.anon, self.acsrf).status_code, 401)
        self.assertEqual(self.listing(self.a, "wrong-csrf").status_code, 404)
        target = "/api/identity/passkeys/" + token(b"a" * 32)
        missing = self.a.delete(target, base_url=HOST,
                                headers={"Origin": HOST})
        self.assertEqual(missing.status_code, 403)
        other = self.a.delete(target, base_url=HOST,
                              headers={"Origin": "https://evil.example",
                                       "X-Edge-Identity-CSRF": self.acsrf})
        self.assertEqual(other.status_code, 403)
        self.assertEqual(self.listing(self.a, self.acsrf).get_json()
                         ["activePasskeys"], 1)

    def test_account_ui_is_status_aware_and_no_client_storage(self):
        page = (ROOT / "backend/static/identity.html").read_text()
        js = (ROOT / "backend/static/assets/identity.js").read_text()
        for marker in ('id="passkeyState"', 'id="passkeyList"',
                       'id="passkeyListStatus"', 'id="addAnotherPasskey"',
                       "Set up biometric login", "Biometric login and passkeys"):
            self.assertIn(marker, page)
        for marker in ("async function loadPasskeys()", "knownPasskeyCount",
                       'el("addPasskey").hidden = count !== 0',
                       'el("addAnotherPasskey").hidden = count === 0',
                       "Passkey login enabled", "addAnotherPasskey",
                       'api("/passkeys/"', 'showLoggedOut();',
                       'await loadPasskeys();'):
            self.assertIn(marker, js)
        self.assertIn("textContent", js)
        for forbidden in ("localStorage", "sessionStorage",
                          "document.cookie", "innerHTML"):
            self.assertNotIn(forbidden, js)


if __name__ == "__main__":
    unittest.main()
