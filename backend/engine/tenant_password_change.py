"""Self-service tenant password change, never a public password reset.

The signed-in member must supply the current password, valid server session,
and identity CSRF. A single SQLite write transaction rechecks authentication,
enforces a per-user attempt budget, changes the Argon2id hash and revokes ALL
of that user's identity sessions. No brokerage, recovery-code issuance or
legacy owner access is enabled by this module.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hmac
import sqlite3
import time

from argon2 import exceptions

from . import identity_auth

WINDOW_SECONDS = 15 * 60
MAX_FAILURES = 5


class PasswordChangeDenied(PermissionError):
    """Never reveal whether a cookie, password or account exists."""


class PasswordChangeRateLimited(PasswordChangeDenied):
    """Too many attempts; still cannot reset without the current password."""


def setup(path):
    """Explicit, opt-in schema preparation after identity_auth.setup()."""
    with closing(identity_auth._db(path)) as con:
        with con:
            for table in ("tenant_users", "tenant_identities", "tenant_identity_sessions"):
                if con.execute("""SELECT 1 FROM sqlite_master
                    WHERE type='table' AND name=?""", (table,)).fetchone() is None:
                    raise RuntimeError("Tenant identity schema required before password management")
            con.execute("""CREATE TABLE IF NOT EXISTS tenant_password_change_failures(
                id INTEGER PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES tenant_users(user_id),
                attempted_at INTEGER NOT NULL
            )""")
            con.execute("""CREATE INDEX IF NOT EXISTS idx_tenant_password_failure_user_time
                ON tenant_password_change_failures(user_id,attempted_at)""")
            con.execute("""CREATE TABLE IF NOT EXISTS tenant_password_change_events(
                id INTEGER PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES tenant_users(user_id),
                occurred_at TEXT NOT NULL,
                event TEXT NOT NULL CHECK(event='PASSWORD_CHANGED')
            )""")
            con.execute("""CREATE TRIGGER IF NOT EXISTS no_password_change_event_delete
                BEFORE DELETE ON tenant_password_change_events
                BEGIN SELECT RAISE(ABORT,'account security audit immutable'); END""")
            con.execute("""CREATE TRIGGER IF NOT EXISTS no_password_change_event_update
                BEFORE UPDATE ON tenant_password_change_events
                BEGIN SELECT RAISE(ABORT,'account security audit immutable'); END""")


class TenantPasswordChange:
    def __init__(self, path, identity_store):
        if type(identity_store) is not identity_auth.IdentityStore:
            raise TypeError("Independent tenant identity store required")
        if str(path) != identity_store.path:
            raise ValueError("Password change must use the identity database")
        self.path = str(path)

    def change(self, token, csrf, current_password, new_password, *, now=None):
        if (not isinstance(token,str) or not 25 < len(token) < 256 or
            not isinstance(csrf,str) or not 20 < len(csrf) < 256):
            raise PasswordChangeDenied("Password change unavailable")
        try:
            identity_auth._validate_password(new_password)
        except ValueError:
            raise PasswordChangeDenied("Password change unavailable") from None
        if (not isinstance(current_password,str) or
            not 0 < len(current_password) <= identity_auth.PASSWORD_MAX_LENGTH or
            current_password == new_password):
            raise PasswordChangeDenied("Password change unavailable")

        moment = int(time.time()) if now is None else now
        if type(moment) is not int or not 0 <= moment <= 253402300799:
            raise PasswordChangeDenied("Password change unavailable")

        with closing(identity_auth._db(self.path)) as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                row=con.execute("""SELECT s.user_id,s.csrf_hash,i.password_hash
                    FROM tenant_identity_sessions s
                    JOIN tenant_identities i ON i.user_id=s.user_id
                    JOIN tenant_users u ON u.user_id=s.user_id
                    WHERE s.token_hash=? AND s.expires_at>?
                      AND s.credential_version=i.credential_version
                      AND u.disabled_at IS NULL""",
                    (identity_auth._digest(token),moment)).fetchone()
                if (row is None or not hmac.compare_digest(
                    row["csrf_hash"],identity_auth._digest(csrf))):
                    raise PasswordChangeDenied("Password change unavailable")
                user_id = row["user_id"]
                con.execute("""DELETE FROM tenant_password_change_failures
                    WHERE attempted_at<?""", (moment-WINDOW_SECONDS,))
                count=con.execute("""SELECT COUNT(*) AS n
                    FROM tenant_password_change_failures
                    WHERE user_id=? AND attempted_at>=?""",
                    (user_id,moment-WINDOW_SECONDS)).fetchone()["n"]
                if count >= MAX_FAILURES:
                    raise PasswordChangeRateLimited("Password change temporarily unavailable")

                try:
                    accepted=identity_auth._HASHER.verify(
                        row["password_hash"],current_password)
                except (exceptions.VerifyMismatchError,
                        exceptions.VerificationError,
                        exceptions.InvalidHashError,TypeError,ValueError):
                    accepted=False
                if not accepted:
                    # Persist the failure without modifying identity sessions.
                    con.execute("""INSERT INTO tenant_password_change_failures
                        (user_id,attempted_at) VALUES(?,?)""",
                        (user_id,moment))
                    con.commit()
                    raise PasswordChangeDenied("Password change unavailable")
                # Current session was verified under the same lock as both
                # the credential version bump and deletion of all sessions.
                new_hash=identity_auth._HASHER.hash(new_password)
                updated=con.execute("""UPDATE tenant_identities
                    SET password_hash=?,credential_version=credential_version+1
                    WHERE user_id=? AND password_hash=?""",
                    (new_hash,user_id,row["password_hash"])).rowcount
                if updated!=1:
                    raise PasswordChangeDenied("Password change unavailable")
                con.execute("DELETE FROM tenant_identity_sessions WHERE user_id=?",(user_id,))
                con.execute("""INSERT INTO tenant_password_change_events
                    (user_id,occurred_at,event) VALUES(?,?,'PASSWORD_CHANGED')""",
                    (user_id,datetime.fromtimestamp(moment,timezone.utc).isoformat()))
                con.execute("DELETE FROM tenant_password_change_failures WHERE user_id=?",
                            (user_id,))
                con.commit()
            except (PasswordChangeDenied,PasswordChangeRateLimited):
                if con.in_transaction:
                    con.rollback()
                raise
            except (sqlite3.Error,RuntimeError):
                if con.in_transaction:
                    con.rollback()
                raise PasswordChangeDenied("Password change unavailable") from None
        return {
            "passwordChanged":True,
            "allIdentitySessionsRevoked":True,
            "mustSignInAgain":True,
            "publicCredentialChanged":False,
            "liveTradingEnabled":False,
            "fundTransfersEnabled":False,
        }
