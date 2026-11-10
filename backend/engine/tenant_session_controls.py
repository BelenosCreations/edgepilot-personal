"""Identity-only active-session visibility and selective other-device logout.

This module never authenticates legacy owner routes, touches Public keys, starts
workers, or handles orders/transfers. Session handles are deterministic SHA-256
labels of *hashed* random bearer tokens, domain-separated and truncated. They
are not the bearer token itself and cannot authenticate a request.

No device fingerprint, network address, user agent or location is stored or
returned. "Other session" is intentionally not claimed to identify a phone.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import hmac
import re
import sqlite3
import time

from . import identity_auth

_ID = re.compile(r"^[0-9a-f]{32}$")
_MAX_RETURNED_SESSIONS = 1000


class SessionControlDenied(PermissionError):
    """Uniform fail-closed identity/account/session denial."""


class SessionTargetDenied(SessionControlDenied):
    """The requested other session does not belong to this identity."""


def _label(token_hash):
    if not isinstance(token_hash, str) or len(token_hash) != 64:
        raise SessionControlDenied("Session management unavailable")
    return hashlib.sha256(
        b"EdgePilot:identity-session-label:v1:" + bytes.fromhex(token_hash)
    ).hexdigest()[:32]


def setup(path):
    """Audit-only additive schema; existing sessions need no migration."""
    with closing(identity_auth._db(path)) as con:
        with con:
            for name in ("tenant_users", "tenant_identities", "tenant_identity_sessions"):
                if not con.execute("""SELECT 1 FROM sqlite_master
                    WHERE type='table' AND name=?""", (name,)).fetchone():
                    raise RuntimeError("Tenant identity tables required for session controls")
            con.execute("""CREATE TABLE IF NOT EXISTS tenant_session_control_events(
                id INTEGER PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES tenant_users(user_id),
                occurred_at TEXT NOT NULL,
                action TEXT NOT NULL CHECK(action='OTHER_SESSION_REVOKED')
            )""")
            con.execute("""CREATE TRIGGER IF NOT EXISTS no_session_control_event_delete
                BEFORE DELETE ON tenant_session_control_events
                BEGIN SELECT RAISE(ABORT,'session audit immutable'); END""")
            con.execute("""CREATE TRIGGER IF NOT EXISTS no_session_control_event_update
                BEFORE UPDATE ON tenant_session_control_events
                BEGIN SELECT RAISE(ABORT,'session audit immutable'); END""")


class TenantSessionControls:
    def __init__(self, path, identity_store):
        if type(identity_store) is not identity_auth.IdentityStore:
            raise TypeError("Tenant identity store required")
        if str(path) != identity_store.path:
            raise ValueError("Session control and identity database must match")
        self.path = str(path)

    @staticmethod
    def _verify(con, token, csrf, moment):
        if (not isinstance(token, str) or not 25 < len(token) < 256 or
                not isinstance(csrf, str) or not 20 < len(csrf) < 256):
            raise SessionControlDenied("Session management unavailable")
        token_hash = identity_auth._digest(token)
        row = con.execute("""SELECT s.user_id, s.csrf_hash FROM tenant_identity_sessions s
            JOIN tenant_identities i ON i.user_id=s.user_id
            JOIN tenant_users u ON u.user_id=s.user_id
            WHERE s.token_hash=? AND s.expires_at>?
              AND s.credential_version=i.credential_version
              AND u.disabled_at IS NULL""", (token_hash, moment)).fetchone()
        if row is None or not hmac.compare_digest(
                row["csrf_hash"], identity_auth._digest(csrf)):
            raise SessionControlDenied("Session management unavailable")
        return row["user_id"], token_hash

    @staticmethod
    def _now(now):
        value = int(time.time()) if now is None else now
        if type(value) is not int or value < 0 or value > 253402300799:
            raise SessionControlDenied("Session management unavailable")
        return value

    def list_sessions(self, token, csrf, *, now=None):
        moment = self._now(now)
        try:
            with closing(identity_auth._db(self.path)) as con:
                user_id, token_hash = self._verify(con, token, csrf, moment)
                rows = con.execute("""SELECT token_hash,issued_at,expires_at
                    FROM tenant_identity_sessions
                    WHERE user_id=? AND expires_at>?
                      AND credential_version=(
                        SELECT credential_version FROM tenant_identities
                        WHERE user_id=?
                      ) ORDER BY issued_at DESC,token_hash""",
                    (user_id, moment, user_id)).fetchmany(_MAX_RETURNED_SESSIONS+1)
                if len(rows) > _MAX_RETURNED_SESSIONS:
                    raise SessionControlDenied("Session management unavailable")
                sessions = [{
                    "sessionId": _label(row["token_hash"]),
                    "issuedAt": row["issued_at"],
                    "expiresAt": row["expires_at"],
                    "current": hmac.compare_digest(row["token_hash"],token_hash),
                } for row in rows]
        except sqlite3.Error:
            raise SessionControlDenied("Session management unavailable") from None
        return {
            "sessions": sessions, "count": len(sessions),
            "readOnly": True, "publicKeysReturned": False,
            "deviceDetailsStored": False, "legacyOwnerAccess": False,
        }

    def revoke_other(self, token, csrf, session_id, *, now=None):
        moment = self._now(now)
        if not isinstance(session_id, str) or not _ID.fullmatch(session_id):
            raise SessionTargetDenied("Other session unavailable")
        try:
            with closing(identity_auth._db(self.path)) as con:
                con.execute("BEGIN IMMEDIATE")
                user_id, current_hash = self._verify(con, token, csrf, moment)
                rows = con.execute("""SELECT token_hash FROM tenant_identity_sessions
                    WHERE user_id=? AND expires_at>?
                      AND credential_version=(
                        SELECT credential_version FROM tenant_identities
                        WHERE user_id=?
                      )""", (user_id,moment,user_id)).fetchmany(_MAX_RETURNED_SESSIONS+1)
                if len(rows) > _MAX_RETURNED_SESSIONS:
                    raise SessionControlDenied("Session management unavailable")
                target_hash = None
                for row in rows:
                    if hmac.compare_digest(_label(row["token_hash"]),session_id):
                        target_hash = row["token_hash"]
                if target_hash is None or hmac.compare_digest(target_hash,current_hash):
                    raise SessionTargetDenied("Other session unavailable")
                removed = con.execute("""DELETE FROM tenant_identity_sessions
                    WHERE user_id=? AND token_hash=?""",
                    (user_id,target_hash)).rowcount
                if removed != 1:
                    raise SessionTargetDenied("Other session unavailable")
                con.execute("""INSERT INTO tenant_session_control_events
                    (user_id,occurred_at,action)
                    VALUES(?,?,'OTHER_SESSION_REVOKED')""",
                    (user_id,datetime.fromtimestamp(moment,timezone.utc).isoformat()))
                con.commit()
        except sqlite3.Error:
            raise SessionControlDenied("Session management unavailable") from None
        return {
            "otherSessionRevoked": True,
            "currentSessionRevoked": False,
            "otherUserAffected": False,
            "publicConnectionChanged": False,
            "liveTradingEnabled": False,
            "fundTransfersEnabled": False,
        }
