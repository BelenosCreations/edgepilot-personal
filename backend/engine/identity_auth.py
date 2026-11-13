"""Dormant, independently authenticated EdgePilot identity sessions.

Not linked to the legacy owner's login or trading/account APIs. Identity
sessions NEVER authorize brokerage reads, account settings, worker operations,
bank actions, or trades. No user self-registration and no live activation.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
from datetime import datetime, timezone

from argon2 import PasswordHasher, exceptions

COOKIE_NAME = "__Host-edgepilot_identity"
SESSION_SECONDS = 4 * 3600
FAILURE_WINDOW_SECONDS = 10 * 60
MAX_FAILURES = 12
PASSWORD_MIN_LENGTH = 14
PASSWORD_MAX_LENGTH = 128

# Argon2id salt and format are handled by argon2-cffi; no passwords in logs.
_HASHER = PasswordHasher(time_cost=3, memory_cost=32768, parallelism=2,
                         hash_len=32, salt_len=16)


class TooManyAttempts(PermissionError):
    pass


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _db(path):
    con = sqlite3.connect(str(path), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=30000")
    return con


def _normalize_username(name):
    if not isinstance(name, str) or not 3 <= len(name) <= 64:
        raise ValueError("Invalid login identifier")
    normalized = name.casefold()
    if not normalized.isascii() or not normalized[0].isalnum() or any(
        not (c.isalnum() or c in "._-") for c in normalized
    ):
        raise ValueError("Invalid login identifier")
    return normalized


def _validate_password(password):
    if (not isinstance(password, str) or
        not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH or
        any(c in password for c in "\x00\r\n")):
        raise ValueError("Use a password of 14–128 characters with no line breaks")


def setup(path):
    """Prepare new identity-only tables; never alter legacy session tables."""
    with _db(path) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS tenant_identities (
            user_id TEXT PRIMARY KEY REFERENCES tenant_users(user_id),
            login_name TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            credential_version INTEGER NOT NULL DEFAULT 1 CHECK(credential_version>=1),
            created_at INTEGER NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS tenant_identity_sessions (
            token_hash TEXT PRIMARY KEY,
            csrf_hash TEXT NOT NULL,
            user_id TEXT NOT NULL REFERENCES tenant_identities(user_id),
            credential_version INTEGER NOT NULL,
            issued_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_tenant_identity_sessions_user ON tenant_identity_sessions(user_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_tenant_identity_sessions_expiry ON tenant_identity_sessions(expires_at)")
        con.execute("""CREATE TABLE IF NOT EXISTS tenant_auth_failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_hash TEXT NOT NULL,
            login_hash TEXT NOT NULL,
            attempted_at INTEGER NOT NULL
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_tenant_auth_failures_source ON tenant_auth_failures(source_hash,attempted_at)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_tenant_auth_failures_login ON tenant_auth_failures(login_hash,attempted_at)")


class IdentityStore:
    """Only backend-internal provisioning; route accepts login/logout only."""

    def __init__(self, path):
        self.path = str(path)
        # A dummy Argon2id verification mitigates username existence timing.
        self._dummy_hash = _HASHER.hash("not-a-real-user-password-for-timing-only")

    def provision(self, user_id, login_name, password):
        """Operator-only operation; never exposed as an HTTP endpoint."""
        normalized = _normalize_username(login_name)
        _validate_password(password)
        password_hash = _HASHER.hash(password)
        with _db(self.path) as con:
            user = con.execute("""SELECT user_id FROM tenant_users
                WHERE user_id=? AND disabled_at IS NULL""", (user_id,)).fetchone()
            if not user:
                raise PermissionError("User not active")
            con.execute("""INSERT INTO tenant_identities
                (user_id,login_name,password_hash,created_at) VALUES(?,?,?,?)""",
                (user_id, normalized, password_hash, int(time.time())))
        return user_id

    def authenticate(self, login_name, password, source, now=None):
        """Return a scoped identity session or None. Do not reveal which field failed."""
        now = int(time.time() if now is None else now)
        try:
            normalized = _normalize_username(login_name)
        except ValueError:
            normalized = "<invalid-login>"
        valid_input = isinstance(password,str) and 0 < len(password) <= 512
        candidate = password if valid_input else "invalid-login-password"
        source_hash = _digest(str(source)[:120] or "unknown")
        login_hash = _digest(normalized)
        with _db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("DELETE FROM tenant_auth_failures WHERE attempted_at<?",
                        (now-FAILURE_WINDOW_SECONDS,))
            recent = con.execute("""SELECT COUNT(*) AS n FROM tenant_auth_failures
                WHERE (source_hash=? OR login_hash=?) AND attempted_at>=?""",
                (source_hash, login_hash, now-FAILURE_WINDOW_SECONDS)).fetchone()["n"]
            if recent >= MAX_FAILURES:
                raise TooManyAttempts("Login temporarily unavailable")
            row = con.execute("""SELECT i.user_id, i.password_hash, i.credential_version
                FROM tenant_identities i JOIN tenant_users u ON u.user_id=i.user_id
                WHERE i.login_name=? AND u.disabled_at IS NULL""",
                (normalized,)).fetchone()
            reference = row["password_hash"] if row else self._dummy_hash
            try:
                valid = _HASHER.verify(reference, candidate)
            except (exceptions.VerifyMismatchError, exceptions.VerificationError,
                    exceptions.InvalidHashError):
                valid = False
            if not (row and valid and valid_input):
                con.execute("""INSERT INTO tenant_auth_failures
                    (source_hash,login_hash,attempted_at) VALUES(?,?,?)""",
                    (source_hash, login_hash, now))
                return None
            con.execute("DELETE FROM tenant_auth_failures WHERE source_hash=? AND login_hash=?",
                        (source_hash, login_hash))
            token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
            expires = now + SESSION_SECONDS
            con.execute("""INSERT INTO tenant_identity_sessions
                (token_hash,csrf_hash,user_id,credential_version,issued_at,expires_at)
                VALUES(?,?,?,?,?,?)""",
                (_digest(token), _digest(csrf), row["user_id"],
                 row["credential_version"], now, expires))
            return {"token":token, "csrf":csrf, "expires_at":expires}

    def principal(self, token, csrf=None, now=None):
        now = int(time.time() if now is None else now)
        if not isinstance(token, str) or not 25 < len(token) < 256:
            return None
        with _db(self.path) as con:
            return self._principal_in(con, token, csrf=csrf, now=now)

    @staticmethod
    def _principal_in(con, token, *, csrf, now):
        """Resolve a verified session using the caller's SQLite transaction."""
        if not isinstance(token, str) or not 25 < len(token) < 256:
            return None
        row = con.execute("""SELECT s.user_id,s.csrf_hash,u.label,u.role
            FROM tenant_identity_sessions s
            JOIN tenant_identities i ON i.user_id=s.user_id
            JOIN tenant_users u ON u.user_id=s.user_id
            WHERE s.token_hash=? AND s.expires_at>?
              AND s.credential_version=i.credential_version
              AND u.disabled_at IS NULL""", (_digest(token), now)).fetchone()
        if not row:
            return None
        if csrf is not None:
            if not isinstance(csrf, str) or not 20 < len(csrf) < 256 or not hmac.compare_digest(
                row["csrf_hash"], _digest(csrf)
            ):
                return None
        return {"user_id": row["user_id"], "label": row["label"], "role": row["role"]}

    def rotate_csrf(self, token, now=None):
        now=int(time.time() if now is None else now)
        principal=self.principal(token,now=now)
        if principal is None:
            return None
        csrf=secrets.token_urlsafe(32)
        with _db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            changed=con.execute("""UPDATE tenant_identity_sessions
                SET csrf_hash=? WHERE token_hash=? AND expires_at>?
                AND credential_version=(
                    SELECT credential_version FROM tenant_identities
                    WHERE user_id=tenant_identity_sessions.user_id)""",
                (_digest(csrf),_digest(token),now)).rowcount
        return (principal,csrf) if changed==1 else None

    def revoke(self, token):
        if isinstance(token,str) and token:
            with _db(self.path) as con:
                con.execute("DELETE FROM tenant_identity_sessions WHERE token_hash=?",
                            (_digest(token),))

    def revoke_all(self, user_id):
        """Administrative lockout: invalidates active sessions for one user only."""
        with _db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            updated=con.execute("""UPDATE tenant_identities
                SET credential_version=credential_version+1 WHERE user_id=?""",
                (user_id,)).rowcount
            con.execute("DELETE FROM tenant_identity_sessions WHERE user_id=?",(user_id,))
        return bool(updated)

    def change_password(self,user_id,old_password,new_password):
        """Internal-only change; requires old secret and revokes all sessions."""
        _validate_password(new_password)
        with _db(self.path) as con:
            row=con.execute("""SELECT password_hash FROM tenant_identities
                WHERE user_id=?""",(user_id,)).fetchone()
        if not row:
            raise PermissionError("Account unavailable")
        try:
            valid=_HASHER.verify(row["password_hash"],old_password)
        except (exceptions.VerifyMismatchError,exceptions.VerificationError,
                exceptions.InvalidHashError,TypeError):
            valid=False
        if not valid:
            raise PermissionError("Account unavailable")
        new_hash=_HASHER.hash(new_password)
        with _db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            updated=con.execute("""UPDATE tenant_identities SET password_hash=?,
                credential_version=credential_version+1
                WHERE user_id=? AND password_hash=?""",
                (new_hash,user_id,row["password_hash"])).rowcount
            if updated!=1:
                raise PermissionError("Credentials changed; retry securely")
            con.execute("DELETE FROM tenant_identity_sessions WHERE user_id=?",(user_id,))
