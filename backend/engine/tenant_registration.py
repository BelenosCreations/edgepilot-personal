"""Optional, invitation-only EdgePilot tenant self-registration.

Only identity/profile records are created. This does NOT enable broker access,
trading, tenant worker jobs, passkeys, or legacy owner account inheritance.
Invites are issued only by a trusted server-side operator (no HTTP issuance).
All invites are random 256-bit one-use values; only SHA-256 digests are stored.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import sqlite3
import time
import uuid
from datetime import datetime, timezone

from argon2 import PasswordHasher

from . import identity_auth

INVITE_TTL_MIN = 60
INVITE_TTL_MAX = 7 * 24 * 3600
ATTEMPT_WINDOW_SECONDS = 15 * 60
MAX_ATTEMPTS_PER_SOURCE = 8
MAX_UNREDEEMED_INVITES = 500
_INVITE_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_HASHER = PasswordHasher(time_cost=3, memory_cost=32768, parallelism=2,
                         hash_len=32, salt_len=16)


class RegistrationDenied(PermissionError):
    """Deliberately generic to avoid revealing invite/user existence."""


class RegistrationRateLimited(RegistrationDenied):
    """Too many signup submissions from the same client source."""


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _timestamp(value):
    if value is None:
        return int(time.time())
    if type(value) is not int or value < 0 or value > 253402300799:
        raise RegistrationDenied("Registration unavailable")
    return value


def _db(path):
    db = sqlite3.connect(str(path), timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=20000")
    return db


def setup(path):
    """Add only signup tables; tenant_foundation and identity_auth must exist."""
    with _db(path) as db:
        for table in ("tenant_users", "tenant_identities", "tenant_audit_events"):
            if not db.execute("""SELECT 1 FROM sqlite_master
                WHERE name=? AND type='table'""", (table,)).fetchone():
                raise RuntimeError("Tenant identity schema required before signup")
        db.execute("""CREATE TABLE IF NOT EXISTS tenant_signup_invites(
            token_hash TEXT PRIMARY KEY CHECK(length(token_hash)=64),
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            consumed_at INTEGER,
            redeemed_user_id TEXT UNIQUE REFERENCES tenant_users(user_id),
            CHECK(expires_at>created_at),
            CHECK((consumed_at IS NULL AND redeemed_user_id IS NULL) OR
                  (consumed_at IS NOT NULL AND redeemed_user_id IS NOT NULL))
        )""")
        db.execute("""CREATE INDEX IF NOT EXISTS idx_tenant_invites_expiry
            ON tenant_signup_invites(expires_at,consumed_at)""")
        db.execute("""CREATE TABLE IF NOT EXISTS tenant_signup_attempts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_hash TEXT NOT NULL,
            at_seconds INTEGER NOT NULL
        )""")
        db.execute("""CREATE INDEX IF NOT EXISTS idx_tenant_signup_attempts
            ON tenant_signup_attempts(source_hash,at_seconds)""")


class TenantRegistration:
    """No role selection, no provider connection, no auto-login."""

    def __init__(self, path):
        self.path = str(path)

    def issue_invitation(self, *, ttl_seconds=3600, now=None):
        """Trusted operator-only invocation. The raw token is returned ONCE."""
        moment = _timestamp(now)
        if type(ttl_seconds) is not int or not INVITE_TTL_MIN <= ttl_seconds <= INVITE_TTL_MAX:
            raise ValueError("Invalid invitation duration")
        token = secrets.token_urlsafe(32)
        with _db(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""DELETE FROM tenant_signup_invites
                WHERE consumed_at IS NULL AND expires_at<=?""", (moment,))
            pending = db.execute("""SELECT COUNT(*) FROM tenant_signup_invites
                WHERE consumed_at IS NULL AND expires_at>?""", (moment,)).fetchone()[0]
            if pending >= MAX_UNREDEEMED_INVITES:
                raise RegistrationDenied("Invitation issuance unavailable")
            db.execute("""INSERT INTO tenant_signup_invites
                (token_hash,created_at,expires_at) VALUES(?,?,?)""",
                (_digest(token), moment, moment+ttl_seconds))
        return {"invitation":token, "expiresAt":moment+ttl_seconds,
                "singleUse":True, "publicApiAccessEnabled":False}

    def _count_attempt(self, source, moment):
        # Source must come from trusted HTTP request.remote_addr, not a header
        # submitted by the user. Store only a digest, not network addresses.
        source_hash = _digest(str(source)[:120] or "unknown")
        with _db(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM tenant_signup_attempts WHERE at_seconds<?",
                       (moment-ATTEMPT_WINDOW_SECONDS,))
            total = db.execute("""SELECT COUNT(*) FROM tenant_signup_attempts
                WHERE source_hash=? AND at_seconds>=?""",
                (source_hash,moment-ATTEMPT_WINDOW_SECONDS)).fetchone()[0]
            if total >= MAX_ATTEMPTS_PER_SOURCE:
                raise RegistrationRateLimited("Registration temporarily unavailable")
            db.execute("""INSERT INTO tenant_signup_attempts(source_hash,at_seconds)
                VALUES(?,?)""", (source_hash,moment))

    def register(self, invitation, login_name, password, label, *, source, now=None):
        moment = _timestamp(now)
        self._count_attempt(source,moment)
        if (not isinstance(invitation,str) or not _INVITE_RE.fullmatch(invitation) or
            not isinstance(label,str) or not 1<=len(label.strip())<=64 or
            len(label)>128 or "\x00" in label):
            raise RegistrationDenied("Registration unavailable")
        try:
            name=identity_auth._normalize_username(login_name)
            identity_auth._validate_password(password)
        except ValueError:
            raise RegistrationDenied("Registration unavailable") from None
        hashed_invite = _digest(invitation)
        # Check before running Argon2 to avoid expensive unauthenticated
        # hashing when the invite does not exist. Recheck under the write lock.
        with _db(self.path) as db:
            exists = db.execute("""SELECT 1 FROM tenant_signup_invites
                WHERE token_hash=? AND expires_at>? AND consumed_at IS NULL""",
                (hashed_invite,moment)).fetchone()
        if not exists:
            raise RegistrationDenied("Registration unavailable")
        password_hash=_HASHER.hash(password)
        user_id=str(uuid.uuid4())
        created=datetime.fromtimestamp(moment,timezone.utc).isoformat()
        try:
            with _db(self.path) as db:
                db.execute("BEGIN IMMEDIATE")
                still_valid = db.execute("""SELECT 1 FROM tenant_signup_invites
                    WHERE token_hash=? AND expires_at>? AND consumed_at IS NULL""",
                    (hashed_invite,moment)).fetchone()
                if not still_valid:
                    raise RegistrationDenied("Registration unavailable")
                db.execute("""INSERT INTO tenant_users
                    (user_id,label,role,created_at) VALUES(?,?,'member',?)""",
                    (user_id,label.strip(),created))
                db.execute("""INSERT INTO tenant_identities
                    (user_id,login_name,password_hash,created_at) VALUES(?,?,?,?)""",
                    (user_id,name,password_hash,moment))
                changed=db.execute("""UPDATE tenant_signup_invites
                    SET consumed_at=?,redeemed_user_id=? WHERE token_hash=?
                    AND consumed_at IS NULL AND expires_at>?""",
                    (moment,user_id,hashed_invite,moment)).rowcount
                if changed!=1:
                    raise RegistrationDenied("Registration unavailable")
                db.execute("""INSERT INTO tenant_audit_events
                    (created_at,user_id,action) VALUES(?,?,'USER_PROVISIONED')""",
                    (created,user_id))
        except sqlite3.IntegrityError:
            raise RegistrationDenied("Registration unavailable") from None
        return {"registered":True,"loginRequired":True,
                "role":"member","publicConnected":False,
                "tradingEnabled":False,"fundTransfersEnabled":False}
