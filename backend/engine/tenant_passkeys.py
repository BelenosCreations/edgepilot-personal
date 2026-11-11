"""Tenant-scoped WebAuthn repository, optionally exposed behind a disabled-by-default gate.

Uses real WebAuthn cryptographic verification and the separate Argon2id
identity store's session format. No biometric templates, Public API keys,
broker data, bank details, callbacks, app routes, or production worker changes.
The caller must derive registration tokens from an authenticated identity
session. A login response NEVER selects a brokerage account or authorizes trading.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import sqlite3
import time
import uuid
from urllib.parse import urlsplit

from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from . import identity_auth

CHALLENGE_TTL_SECONDS = 5 * 60
MAX_PENDING_CHALLENGES = 500
MAX_PASSKEYS_PER_USER = 12
MAX_CREDENTIAL_JSON_BYTES = 16_384


class PasskeyDenied(PermissionError):
    """Intentionally generic: no credential, username or token details."""


def _android_native_origin_from_pinned_cert(fingerprint):
    """Android's fixed signed-app WebAuthn origin, never client supplied.

    This is a public certificate digest (NOT a key or secret), encoded as
    RFC 4648 base64url without '='. Fail closed for malformed digests.
    """
    if (not isinstance(fingerprint, str) or
        re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){31}[0-9A-Fa-f]{2}", fingerprint) is None):
        raise ValueError("A verified Android certificate fingerprint is required")
    certificate_digest = bytes.fromhex(fingerprint.replace(":", ""))
    return ("android:apk-key-hash:" +
            base64.urlsafe_b64encode(certificate_digest).decode("ascii").rstrip("="))


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now(now):
    moment = int(time.time() if now is None else now)
    if moment < 0:
        raise PasskeyDenied("Passkey request unavailable")
    return moment


def _credential_json(value):
    if not isinstance(value, dict):
        raise PasskeyDenied("Passkey verification failed")
    try:
        serialized = json.dumps(value, separators=(",", ":"), allow_nan=False)
        if len(serialized.encode("utf-8")) > MAX_CREDENTIAL_JSON_BYTES:
            raise PasskeyDenied("Passkey verification failed")
    except (ValueError, TypeError, UnicodeError):
        raise PasskeyDenied("Passkey verification failed") from None
    return value


def _database(path):
    db = sqlite3.connect(str(path), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=15000")
    return db


def setup(path):
    """Add only dormant tenant tables; never migrate legacy owner credentials."""
    with _database(path) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS tenant_passkey_credentials(
            credential_id BLOB PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES tenant_identities(user_id),
            public_key BLOB NOT NULL,
            sign_count INTEGER NOT NULL CHECK(sign_count>=0),
            device_type TEXT NOT NULL,
            backed_up INTEGER NOT NULL CHECK(backed_up IN(0,1)),
            created_at INTEGER NOT NULL,
            revoked_at INTEGER
        )""")
        db.execute("""CREATE INDEX IF NOT EXISTS idx_tenant_passkey_owners
            ON tenant_passkey_credentials(user_id,revoked_at)""")
        db.execute("""CREATE TABLE IF NOT EXISTS tenant_passkey_challenges(
            token_hash TEXT PRIMARY KEY,
            operation TEXT NOT NULL CHECK(operation IN('register','authenticate')),
            user_id TEXT REFERENCES tenant_identities(user_id),
            challenge BLOB NOT NULL,
            expires_at INTEGER NOT NULL,
            rp_id TEXT NOT NULL,
            origin TEXT NOT NULL
        )""")
        db.execute("""CREATE INDEX IF NOT EXISTS idx_tenant_passkey_expiry
            ON tenant_passkey_challenges(expires_at)""")


class TenantPasskeyStore:
    """User-scoped passkey ceremonies; never accepts a client-provided owner ID."""

    def __init__(self, path, identity_store, *, rp_id, expected_origin,
                 staging_android_cert_sha256=None):
        if not isinstance(identity_store, identity_auth.IdentityStore):
            raise TypeError("Verified identity store required")
        if identity_store.path != str(path):
            raise ValueError("Identity and passkeys must share the tenant database")
        if (not isinstance(rp_id, str) or
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{1,251})[a-z0-9]", rp_id) or
            ".." in rp_id or not isinstance(expected_origin, str)):
            raise ValueError("Invalid fixed WebAuthn relying party")
        parsed = urlsplit(expected_origin)
        if (parsed.scheme != "https" or parsed.hostname != rp_id or
            parsed.netloc != rp_id or parsed.path or parsed.query or
            parsed.fragment or parsed.username or parsed.password):
            raise ValueError("WebAuthn origin must exactly match HTTPS relying party")
        self.path = str(path)
        self.identity_store = identity_store
        self.rp_id = rp_id
        self.origin = expected_origin
        # Production remains HTTPS-only. In separately gated staging only,
        # app.py may pass the verified public signer digest to accept the
        # Android Credential Manager native origin in addition to HTTPS.
        # Neither request headers nor credential clientData can extend this.
        self.allowed_origins = (
            [expected_origin, _android_native_origin_from_pinned_cert(
                staging_android_cert_sha256)]
            if staging_android_cert_sha256 is not None else expected_origin
        )

    def _new_challenge(self, operation, user_id, challenge, now):
        token = secrets.token_urlsafe(36)
        with _database(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM tenant_passkey_challenges WHERE expires_at<=?", (now,))
            pending = db.execute("SELECT COUNT(*) FROM tenant_passkey_challenges").fetchone()[0]
            if pending >= MAX_PENDING_CHALLENGES:
                raise PasskeyDenied("Passkey request unavailable")
            db.execute("""INSERT INTO tenant_passkey_challenges
                (token_hash,operation,user_id,challenge,expires_at,rp_id,origin)
                VALUES(?,?,?,?,?,?,?)""",
                (_digest(token),operation,user_id,challenge,
                 now + CHALLENGE_TTL_SECONDS,self.rp_id,self.origin))
        return token

    def _consume_challenge(self, operation, request_id, now, user_id=None):
        if not isinstance(request_id,str) or not 30 <= len(request_id) <= 128:
            raise PasskeyDenied("Passkey verification failed")
        with _database(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT challenge,user_id,expires_at,rp_id,origin
                FROM tenant_passkey_challenges
                WHERE token_hash=? AND operation=?""",
                (_digest(request_id),operation)).fetchone()
            if row is None:
                raise PasskeyDenied("Passkey verification failed")
            db.execute("DELETE FROM tenant_passkey_challenges WHERE token_hash=?",
                       (_digest(request_id),))
            # The request ID is single-use even when cryptographic verification fails.
        if (row["expires_at"] <= now or row["rp_id"] != self.rp_id or
            row["origin"] != self.origin or
            (operation == "register" and
             (user_id is None or row["user_id"] != user_id)) or
            (operation == "authenticate" and row["user_id"] is not None)):
            raise PasskeyDenied("Passkey verification failed")
        return bytes(row["challenge"])

    def begin_registration(self, identity_token, identity_csrf, *, now=None):
        """Requires existing user identity session and CSRF, never self-enrolls."""
        now = _now(now)
        principal = self.identity_store.principal(identity_token,identity_csrf,now=now)
        if principal is None:
            raise PasskeyDenied("Passkey registration unavailable")
        user_id = principal["user_id"]
        with _database(self.path) as db:
            row = db.execute("""SELECT i.login_name,u.label FROM tenant_identities i
                JOIN tenant_users u ON u.user_id=i.user_id
                WHERE i.user_id=? AND u.disabled_at IS NULL""",
                (user_id,)).fetchone()
            existing = db.execute("""SELECT credential_id FROM tenant_passkey_credentials
                WHERE user_id=? AND revoked_at IS NULL""",(user_id,)).fetchall()
        if row is None or len(existing) >= MAX_PASSKEYS_PER_USER:
            raise PasskeyDenied("Passkey registration unavailable")
        options = generate_registration_options(
            rp_id=self.rp_id,
            rp_name="EdgePilot",
            user_id=uuid.UUID(user_id).bytes,
            user_name=row["login_name"],
            user_display_name=row["label"],
            attestation=AttestationConveyancePreference.NONE,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED),
            exclude_credentials=[PublicKeyCredentialDescriptor(id=bytes(r["credential_id"]))
                                 for r in existing],
        )
        request_id = self._new_challenge("register", user_id, options.challenge, now)
        return {"requestId":request_id,"publicKey":json.loads(options_to_json(options))}

    def finish_registration(self, identity_token, identity_csrf, request_id, credential, *,
                            now=None):
        now = _now(now)
        principal = self.identity_store.principal(identity_token,identity_csrf,now=now)
        if principal is None:
            raise PasskeyDenied("Passkey registration unavailable")
        challenge = self._consume_challenge("register",request_id,now,principal["user_id"])
        data = _credential_json(credential)
        try:
            verified = verify_registration_response(
                credential=data,expected_challenge=challenge,
                expected_rp_id=self.rp_id,expected_origin=self.allowed_origins,
                require_user_verification=True)
            credential_id = bytes(verified.credential_id)
            public_key = bytes(verified.credential_public_key)
            counter = int(verified.sign_count)
            device_type = str(getattr(verified.credential_device_type, "value",
                                      verified.credential_device_type))
            backed_up = int(bool(verified.credential_backed_up))
            if not 16 <= len(credential_id) <= 2048 or not public_key or counter < 0:
                raise ValueError("Invalid credential shape")
        except Exception:
            raise PasskeyDenied("Passkey verification failed") from None
        with _database(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute("""SELECT u.user_id FROM tenant_users u
                JOIN tenant_identities i ON i.user_id=u.user_id
                WHERE u.user_id=? AND u.disabled_at IS NULL""",
                (principal["user_id"],)).fetchone()
            count = db.execute("""SELECT COUNT(*) FROM tenant_passkey_credentials
                WHERE user_id=? AND revoked_at IS NULL""",
                (principal["user_id"],)).fetchone()[0]
            if active is None or count >= MAX_PASSKEYS_PER_USER:
                raise PasskeyDenied("Passkey registration unavailable")
            try:
                db.execute("""INSERT INTO tenant_passkey_credentials
                    (credential_id,user_id,public_key,sign_count,device_type,
                     backed_up,created_at)
                    VALUES(?,?,?,?,?,?,?)""",
                    (credential_id,principal["user_id"],public_key,counter,
                     device_type,backed_up,now))
            except sqlite3.IntegrityError:
                raise PasskeyDenied("Passkey registration unavailable") from None
        return {"registered":True,"biometricsStoredOnServer":False,
                "brokerAccessAuthorized":False,"tradingEnabled":False}

    def begin_authentication(self, *, now=None):
        """Discoverable passkey request; no email/username enumeration."""
        now = _now(now)
        options = generate_authentication_options(
            rp_id=self.rp_id,
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        request_id = self._new_challenge("authenticate",None,options.challenge,now)
        return {"requestId":request_id,"publicKey":json.loads(options_to_json(options))}

    def finish_authentication(self, request_id, credential, *, now=None):
        """Verify a real WebAuthn assertion, then create a scoped identity session."""
        now = _now(now)
        challenge = self._consume_challenge("authenticate",request_id,now)
        data = _credential_json(credential)
        try:
            identifier = base64url_to_bytes(data["id"])
            if (not isinstance(data.get("rawId"),str) or
                base64url_to_bytes(data["rawId"]) != identifier or
                not 16 <= len(identifier) <= 2048):
                raise ValueError("Credential mismatch")
        except (KeyError,ValueError,TypeError,OverflowError):
            raise PasskeyDenied("Passkey verification failed") from None
        with _database(self.path) as db:
            row = db.execute("""SELECT c.user_id,c.public_key,c.sign_count,
                c.revoked_at,u.disabled_at
                FROM tenant_passkey_credentials c
                JOIN tenant_identities i ON i.user_id=c.user_id
                JOIN tenant_users u ON u.user_id=i.user_id
                WHERE c.credential_id=?""",(identifier,)).fetchone()
        if row is None or row["revoked_at"] is not None or row["disabled_at"] is not None:
            raise PasskeyDenied("Passkey verification failed")
        response = data.get("response",{})
        try:
            if isinstance(response,dict) and response.get("userHandle") is not None:
                user_handle = base64url_to_bytes(response["userHandle"])
                if user_handle != uuid.UUID(row["user_id"]).bytes:
                    raise ValueError("User handle mismatch")
            verified = verify_authentication_response(
                credential=data,expected_challenge=challenge,
                expected_rp_id=self.rp_id,expected_origin=self.allowed_origins,
                credential_public_key=bytes(row["public_key"]),
                credential_current_sign_count=row["sign_count"],
                require_user_verification=True)
            counter = int(verified.new_sign_count)
            if counter < row["sign_count"]:
                raise ValueError("Authenticator counter rolled back")
        except Exception:
            raise PasskeyDenied("Passkey verification failed") from None
        token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        expires = now + identity_auth.SESSION_SECONDS
        with _database(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("""UPDATE tenant_passkey_credentials
                SET sign_count=?,backed_up=?
                WHERE credential_id=? AND user_id=? AND sign_count=?
                  AND revoked_at IS NULL""",
                (counter,int(bool(verified.credential_backed_up)),identifier,
                 row["user_id"],row["sign_count"])).rowcount
            if changed != 1:
                raise PasskeyDenied("Passkey verification failed")
            active = db.execute("""SELECT i.credential_version
                FROM tenant_identities i JOIN tenant_users u ON u.user_id=i.user_id
                WHERE i.user_id=? AND u.disabled_at IS NULL""",
                (row["user_id"],)).fetchone()
            if active is None:
                raise PasskeyDenied("Passkey verification failed")
            db.execute("""INSERT INTO tenant_identity_sessions
                (token_hash,csrf_hash,user_id,credential_version,issued_at,expires_at)
                VALUES(?,?,?,?,?,?)""",
                (_digest(token),_digest(csrf),row["user_id"],
                 active["credential_version"],now,expires))
        return {"token":token,"csrf":csrf,"expires_at":expires,
                "scope":"identity_only_no_broker_access"}

    def revoke_for_user(self, identity_token, identity_csrf, credential_id, *, now=None):
        """Revoke only an authenticated user's own passkey; never remove last login."""
        now = _now(now)
        principal = self.identity_store.principal(identity_token,identity_csrf,now=now)
        if principal is None or not isinstance(credential_id,(bytes,bytearray)):
            raise PasskeyDenied("Passkey revocation unavailable")
        with _database(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("""UPDATE tenant_passkey_credentials SET revoked_at=?
                WHERE credential_id=? AND user_id=? AND revoked_at IS NULL""",
                (now,bytes(credential_id),principal["user_id"])).rowcount
            if changed != 1:
                raise PasskeyDenied("Passkey revocation unavailable")
            # Any session previously obtained with a compromised passkey
            # must not outlive the explicit revocation. This also logs out
            # this user on their other devices, without touching any tenant
            # other than the verified session principal.
            db.execute("""UPDATE tenant_identities
                SET credential_version=credential_version+1 WHERE user_id=?""",
                (principal["user_id"],))
            db.execute("DELETE FROM tenant_identity_sessions WHERE user_id=?",
                       (principal["user_id"],))
        return {"revoked":True,"otherUsersUnaffected":True,
                "identitySessionsRevoked":True}

    def redacted_own_status(self, identity_token, identity_csrf, *, now=None):
        """List only this signed-in member's active passkeys for UI management.

        Credential IDs are public identifiers used by the existing revoke
        endpoint, NOT private keys. Never expose stored public-key material,
        another tenant's rows, device identifiers or biometric templates.
        """
        now = _now(now)
        principal = self.identity_store.principal(identity_token,identity_csrf,now=now)
        if principal is None:
            raise PasskeyDenied("Passkey status unavailable")
        with _database(self.path) as db:
            rows=db.execute("""SELECT credential_id,created_at,device_type,backed_up
                FROM tenant_passkey_credentials
                WHERE user_id=? AND revoked_at IS NULL
                ORDER BY created_at,credential_id""",
                (principal["user_id"],)).fetchall()
        registered=[{
            "credentialId":base64.urlsafe_b64encode(bytes(row["credential_id"]))
                .decode("ascii").rstrip("="),
            "createdAt":int(row["created_at"]),
            "deviceType":str(row["device_type"]),
            "backedUp":bool(row["backed_up"]),
        } for row in rows]
        return {"activePasskeys":len(registered),"passkeys":registered,
                "brokerAccessAuthorized":False,"tradingEnabled":False,
                "deviceIdentifiersStored":False,"biometricsStoredOnServer":False}
