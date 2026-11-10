"""v0.2.41: real, local WebAuthn ES256 cryptographic HTTP acceptance.

These software-authenticator responses are deliberately generated inside the
test process using ephemeral P-256 private keys. Unlike older unit tests, the
production py_webauthn verification functions are NOT mocked. No physical
biometrics, Android OS link validation, provider API, live users, or network
requests are involved. These are protocol fixtures, not deployable passkeys.
"""
import base64
import hashlib
import importlib
import json
import os
import struct
import tempfile
import unittest
import uuid
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from engine import tenant_foundation

RP = "edgepilot.example.test"
ORIGIN = "https://" + RP
HEADERS = {"Origin": ORIGIN}
PW_A = "Synthetic-Private-Alice-Password-Long-2026"
PW_B = "Synthetic-Private-Bob-Password-Long-2026"


def _url64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _from64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _head(major, count):
    """Minimal independent CBOR encoder for a test-only FIDO2 authenticator."""
    if count < 24:
        return bytes([(major << 5) | count])
    if count < 256:
        return bytes([(major << 5) | 24, count])
    if count < 65536:
        return bytes([(major << 5) | 25]) + struct.pack(">H", count)
    return bytes([(major << 5) | 26]) + struct.pack(">I", count)


def _cbor(value):
    if isinstance(value, int):
        return _head(0, value) if value >= 0 else _head(1, -1 - value)
    if isinstance(value, bytes):
        return _head(2, len(value)) + value
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        return _head(3, len(encoded)) + encoded
    if isinstance(value, dict):
        return _head(5, len(value)) + b"".join(
            _cbor(k) + _cbor(v) for k, v in value.items()
        )
    raise TypeError("Unsupported test-only CBOR element")


def _client_data(kind, challenge, origin=ORIGIN):
    return json.dumps({
        "type": kind,
        "challenge": challenge,
        "origin": origin,
        "crossOrigin": False,
    }, separators=(",", ":")).encode("utf-8")


class LocalAuthenticator:
    """Not a device authenticator: an isolated fixture with an ephemeral key."""

    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.counter = 0

    @staticmethod
    def _rp_hash():
        return hashlib.sha256(RP.encode("ascii")).digest()

    def _cose_key(self):
        p = self.key.public_key().public_numbers()
        return _cbor({
            1: 2,             # EC2
            3: -7,            # ES256
            -1: 1,            # P-256
            -2: p.x.to_bytes(32, "big"),
            -3: p.y.to_bytes(32, "big"),
        })

    def registration(self, options, *, origin=ORIGIN, user_verified=True):
        auth_flags = 0x41 | (0x04 if user_verified else 0)
        auth_data = (
            self._rp_hash() +
            bytes([auth_flags]) +
            struct.pack(">I", 0) +
            b"\x00" * 16 +
            struct.pack(">H", len(self.credential_id)) +
            self.credential_id +
            self._cose_key()
        )
        attestation = _cbor({
            "fmt": "none",
            "attStmt": {},
            "authData": auth_data,
        })
        return {
            "id": _url64(self.credential_id),
            "rawId": _url64(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": _url64(
                    _client_data("webauthn.create", options["challenge"], origin)),
                "attestationObject": _url64(attestation),
            },
        }

    def assertion(self, options, user_id, *, origin=ORIGIN,
                  user_verified=True, counter=None, tamper_signature=False,
                  override_user_handle=None):
        if counter is None:
            self.counter += 1
            counter = self.counter
        flags = 0x01 | (0x04 if user_verified else 0)
        auth_data = self._rp_hash() + bytes([flags]) + struct.pack(">I", counter)
        client_data = _client_data("webauthn.get", options["challenge"], origin)
        signature = self.key.sign(
            auth_data + hashlib.sha256(client_data).digest(),
            ec.ECDSA(hashes.SHA256()))
        if tamper_signature:
            signature = signature[:-1] + bytes([signature[-1] ^ 1])
        user_handle = (uuid.UUID(user_id).bytes if override_user_handle is None
                       else uuid.UUID(override_user_handle).bytes)
        return {
            "id": _url64(self.credential_id),
            "rawId": _url64(self.credential_id),
            "type": "public-key",
            "response": {
                "authenticatorData": _url64(auth_data),
                "clientDataJSON": _url64(client_data),
                "signature": _url64(signature),
                "userHandle": _url64(user_handle),
            },
        }


class TwoUserRealCryptoHttpAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="edgepilot-webauthn-realcrypto-")
        self.environment = patch.dict(os.environ, {
            "EDGE_DB_PATH": self.temp.name + "/isolated.db",
            "EDGE_TENANT_SCHEMA_PREPARE": "true",
            "EDGE_IDENTITY_AUTH_ENABLED": "true",
            "EDGE_TENANT_SIGNUP_ENABLED": "false",
            "EDGE_TENANT_PASSKEYS_ENABLED": "true",
            "EDGE_WEBAUTHN_RP_ID": RP,
            "EDGE_WEBAUTHN_ORIGIN": ORIGIN,
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED": "false",
            "EDGE_TENANT_PUBLIC_READONLY_ENABLED": "false",
            "EDGE_AUTOMATION_WORKER_ENABLED": "false",
            "EDGE_APP_TOKEN": "fake-legacy-owner-access-token-only-for-local-tests-2026",
            "PUBLIC_API_SECRET": "",
        })
        self.environment.start()
        # Trip on ANY unanticipated outbound request. The fixtures never connect
        # to Google, Public, Render, production services, or real identity sites.
        self.network = patch(
            "requests.sessions.Session.request",
            side_effect=AssertionError("Network forbidden in synthetic passkey acceptance"))
        self.network.start()
        import app
        self.module = importlib.reload(app)
        self.users = tenant_foundation.TenantStore(str(self.module.DB))
        self.aid = self.users.provision_user("Synthetic Alice")
        self.bid = self.users.provision_user("Synthetic Bob")
        self.module.identity_store.provision(self.aid, "crypto_alice", PW_A)
        self.module.identity_store.provision(self.bid, "crypto_bob", PW_B)
        self.a = self.module.app.test_client()
        self.b = self.module.app.test_client()
        self.alice_key = LocalAuthenticator()
        self.bob_key = LocalAuthenticator()
        self.alice_csrf = self.login(self.a, "crypto_alice", PW_A)
        self.bob_csrf = self.login(self.b, "crypto_bob", PW_B)

    def tearDown(self):
        self.network.stop()
        self.environment.stop()
        import app
        importlib.reload(app)
        self.temp.cleanup()

    def post(self, client, url, payload, csrf=None):
        headers = dict(HEADERS)
        if csrf is not None:
            headers["X-Edge-Identity-CSRF"] = csrf
        return client.post(url, base_url=ORIGIN, headers=headers, json=payload)

    def get(self, client, url):
        return client.get(url, base_url=ORIGIN)

    def login(self, client, username, password):
        result = self.post(client, "/api/identity/login",
                           {"username": username, "password": password})
        self.assertEqual(result.status_code, 200, result.get_data(as_text=True))
        return result.get_json()["csrf"]

    def begin_registration(self, client, csrf):
        response = self.post(client, "/api/identity/passkeys/register/options", {}, csrf)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        data = response.get_json()
        self.assertEqual(data["publicKey"]["rp"]["id"], RP)
        self.assertEqual(data["publicKey"]["authenticatorSelection"]["userVerification"],
                         "required")
        return data

    def register(self, client, csrf, authenticator):
        started = self.begin_registration(client, csrf)
        response = self.post(client, "/api/identity/passkeys/register/finish", {
            "requestId": started["requestId"],
            "credential": authenticator.registration(started["publicKey"]),
        }, csrf)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["tradingEnabled"], False)
        return started

    def begin_authentication(self, client):
        response = self.post(client, "/api/identity/passkeys/authenticate/options", {})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        data = response.get_json()
        self.assertEqual(data["publicKey"]["rpId"], RP)
        self.assertEqual(data["publicKey"]["userVerification"], "required")
        return data

    def finish_authentication(self, client, started, response):
        return self.post(client, "/api/identity/passkeys/authenticate/finish", {
            "requestId": started["requestId"],
            "credential": response,
        })

    def test_real_cryptography_registration_and_two_independent_sign_ins(self):
        self.register(self.a, self.alice_csrf, self.alice_key)
        self.register(self.b, self.bob_csrf, self.bob_key)
        fresh_a = self.module.app.test_client()
        fresh_b = self.module.app.test_client()
        login_a = self.begin_authentication(fresh_a)
        login_b = self.begin_authentication(fresh_b)
        done_a = self.finish_authentication(
            fresh_a, login_a, self.alice_key.assertion(login_a["publicKey"], self.aid))
        done_b = self.finish_authentication(
            fresh_b, login_b, self.bob_key.assertion(login_b["publicKey"], self.bid))
        for signed in (done_a, done_b):
            self.assertEqual(signed.status_code, 200, signed.get_data(as_text=True))
            self.assertIn("HttpOnly", signed.headers["Set-Cookie"])
            self.assertIn("Secure", signed.headers["Set-Cookie"])
            self.assertIn("SameSite=Strict", signed.headers["Set-Cookie"])
            self.assertEqual(signed.get_json()["scope"], "identity_only_no_legacy_access")
        a_session = self.get(fresh_a, "/api/identity/session")
        b_session = self.get(fresh_b, "/api/identity/session")
        self.assertEqual(a_session.get_json()["user"]["userId"], self.aid)
        self.assertEqual(b_session.get_json()["user"]["userId"], self.bid)
        self.assertNotEqual(a_session.get_json()["user"]["userId"],
                            b_session.get_json()["user"]["userId"])
        self.assertEqual(self.get(fresh_a, "/api/dashboard").status_code, 401)
        self.assertEqual(self.get(fresh_b, "/api/dashboard").status_code, 401)
        # Failed cross-owner revocation cannot make another owner's key disappear.
        path = "/api/identity/passkeys/" + _url64(self.alice_key.credential_id)
        denial = fresh_b.delete(path, base_url=ORIGIN, headers={
            **HEADERS, "X-Edge-Identity-CSRF": done_b.get_json()["csrf"]})
        self.assertEqual(denial.status_code, 404)
        self.assertEqual(self.get(fresh_a, "/api/identity/session").status_code, 200)

    def test_live_verifier_refuses_wrong_origin_uv_and_tampered_signature(self):
        self.register(self.a, self.alice_csrf, self.alice_key)
        for kwargs in (
            {"origin": "https://attacker.invalid"},
            {"user_verified": False},
            {"tamper_signature": True},
            {"override_user_handle": self.bid},
        ):
            client = self.module.app.test_client()
            started = self.begin_authentication(client)
            bad = self.finish_authentication(
                client, started, self.alice_key.assertion(
                    started["publicKey"], self.aid, **kwargs))
            self.assertEqual(bad.status_code, 400, bad.get_data(as_text=True))
            self.assertEqual(self.get(client, "/api/identity/session").status_code, 401)
            # Failed or malformed ceremonies consume their challenge exactly once.
            replay = self.finish_authentication(
                client, started, self.alice_key.assertion(
                    started["publicKey"], self.aid))
            self.assertEqual(replay.status_code, 400)
        good_client = self.module.app.test_client()
        started = self.begin_authentication(good_client)
        good = self.finish_authentication(
            good_client, started, self.alice_key.assertion(started["publicKey"], self.aid))
        self.assertEqual(good.status_code, 200, good.get_data(as_text=True))

    def test_live_verifier_refuses_counter_rollback_and_revoked_key(self):
        self.register(self.a, self.alice_csrf, self.alice_key)
        signed_client = self.module.app.test_client()
        started = self.begin_authentication(signed_client)
        signed = self.finish_authentication(
            signed_client, started,
            self.alice_key.assertion(started["publicKey"], self.aid, counter=8))
        self.assertEqual(signed.status_code, 200, signed.get_data(as_text=True))
        attack_client = self.module.app.test_client()
        attack = self.begin_authentication(attack_client)
        rollback = self.finish_authentication(
            attack_client, attack,
            self.alice_key.assertion(attack["publicKey"], self.aid, counter=7))
        self.assertEqual(rollback.status_code, 400)
        path = "/api/identity/passkeys/" + _url64(self.alice_key.credential_id)
        revoked = self.a.delete(path, base_url=ORIGIN, headers={
            **HEADERS, "X-Edge-Identity-CSRF": self.alice_csrf})
        self.assertEqual(revoked.status_code, 200, revoked.get_data(as_text=True))
        self.assertEqual(self.get(signed_client, "/api/identity/session").status_code, 401)
        self.assertEqual(self.get(self.b, "/api/identity/session").status_code, 200)
        another = self.module.app.test_client()
        retry = self.begin_authentication(another)
        denied = self.finish_authentication(
            another, retry,
            self.alice_key.assertion(retry["publicKey"], self.aid, counter=9))
        self.assertEqual(denied.status_code, 400)


if __name__ == "__main__":
    unittest.main()
