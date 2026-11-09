"""Inactive, additive tenant data foundation for future EdgePilot multi-account support.

This is NOT a login system and is NOT wired to any HTTP endpoint, existing
broker credential, account selector, trading model or worker. It only creates
new tables if explicitly enabled in the server configuration. The current
single-owner app continues using its existing database records untouched.

Future requests MUST derive the user identity from a verified session, NEVER
from client-supplied user_id or account_id alone. No live execution capability.
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone

from cryptography.fernet import Fernet

SCHEMA_VERSION = 1
_ALLOWED_ROLES = frozenset(("owner", "member"))
_ALLOWED_PREFERENCES = frozenset(("display_name", "theme", "locale"))
_ALLOWED_ACCOUNT_SETTINGS = frozenset((
    "profile_label", "research_mode", "watchlist_csv", "paper_risk_profile"
))


class TenantAccessError(PermissionError):
    """Tenant object is missing or belongs to a different authenticated user."""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _uuid():
    return str(uuid.uuid4())


def _open(path):
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def setup(path):
    """Add *new* v1 tenant tables. Never alter or copy legacy user data."""
    with _open(path) as conn:
        conn.executescript("""BEGIN IMMEDIATE;
        CREATE TABLE IF NOT EXISTS tenant_schema_meta (
            id INTEGER PRIMARY KEY CHECK (id=1),
            schema_version INTEGER NOT NULL CHECK(schema_version>0)
        );
        CREATE TABLE IF NOT EXISTS tenant_users (
            user_id TEXT PRIMARY KEY,
            label TEXT NOT NULL CHECK(length(label) BETWEEN 1 AND 64),
            role TEXT NOT NULL CHECK(role IN ('owner','member')),
            created_at TEXT NOT NULL,
            disabled_at TEXT
        );
        CREATE TABLE IF NOT EXISTS tenant_connections (
            connection_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES tenant_users(user_id),
            provider TEXT NOT NULL CHECK(provider='public'),
            credential_ciphertext BLOB NOT NULL,
            created_at TEXT NOT NULL,
            revoked_at TEXT,
            UNIQUE(connection_id,user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_tenant_connections_user
            ON tenant_connections(user_id);
        CREATE TABLE IF NOT EXISTS tenant_accounts (
            account_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES tenant_users(user_id),
            connection_id TEXT NOT NULL,
            provider TEXT NOT NULL CHECK(provider='public'),
            provider_account_ref TEXT NOT NULL,
            label TEXT NOT NULL CHECK(length(label) BETWEEN 1 AND 64),
            created_at TEXT NOT NULL,
            disabled_at TEXT,
            UNIQUE(account_id,user_id),
            UNIQUE(provider,provider_account_ref),
            FOREIGN KEY(connection_id,user_id)
                REFERENCES tenant_connections(connection_id,user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_tenant_accounts_user
            ON tenant_accounts(user_id);
        CREATE TABLE IF NOT EXISTS tenant_user_preferences (
            user_id TEXT NOT NULL REFERENCES tenant_users(user_id),
            preference_key TEXT NOT NULL,
            preference_value TEXT NOT NULL,
            PRIMARY KEY(user_id,preference_key)
        );
        CREATE TABLE IF NOT EXISTS tenant_account_settings (
            account_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            setting_key TEXT NOT NULL,
            setting_value TEXT NOT NULL,
            PRIMARY KEY(account_id,user_id,setting_key),
            FOREIGN KEY(account_id,user_id)
                REFERENCES tenant_accounts(account_id,user_id)
        );
        CREATE TABLE IF NOT EXISTS tenant_audit_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            user_id TEXT NOT NULL REFERENCES tenant_users(user_id),
            account_id TEXT,
            action TEXT NOT NULL CHECK(action IN (
                'USER_PROVISIONED','CONNECTION_ADDED','ACCOUNT_LINKED',
                'PREFERENCE_CHANGED','ACCOUNT_SETTING_CHANGED')),
            FOREIGN KEY(account_id,user_id)
                REFERENCES tenant_accounts(account_id,user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_tenant_audit_user_time
            ON tenant_audit_events(user_id,created_at);
        """)
        row=conn.execute("SELECT schema_version FROM tenant_schema_meta WHERE id=1").fetchone()
        if row and row["schema_version"] != SCHEMA_VERSION:
            raise RuntimeError("Unsupported tenant schema version; stop and migrate offline")
        conn.execute("INSERT OR IGNORE INTO tenant_schema_meta (id,schema_version) VALUES (1,?)",
                     (SCHEMA_VERSION,))


class TenantStore:
    """Internal-only repository. Caller must supply a trusted session principal.

    Absolutely no route uses this class yet. Provisioning and credential
    linking require future authentication/authorization flow before exposure.
    """

    def __init__(self, path, credential_key=None):
        self.path = str(path)
        self.credential_key = credential_key

    def _fernet(self):
        key = self.credential_key or os.getenv("EDGE_CREDENTIAL_KEY", "")
        if not key:
            raise RuntimeError("Server credential encryption is unavailable")
        try:
            return Fernet(key.encode("ascii") if isinstance(key,str) else key)
        except (ValueError,TypeError,UnicodeError) as exc:
            raise RuntimeError("Invalid server encryption key") from None

    def _active_user(self, conn, user_id):
        row=conn.execute("SELECT user_id FROM tenant_users WHERE user_id=? AND disabled_at IS NULL",
                         (user_id,)).fetchone()
        if row is None:
            raise TenantAccessError("User is not enabled")

    def _active_account(self, conn, user_id, account_id):
        row=conn.execute("""SELECT account_id FROM tenant_accounts
            WHERE account_id=? AND user_id=? AND disabled_at IS NULL""",
            (account_id,user_id)).fetchone()
        if row is None:
            raise TenantAccessError("Account unavailable to this user")

    def provision_user(self, label, role="member"):
        """Internal provisioning only; not accessible to API clients."""
        if not isinstance(label,str) or not 1<=len(label.strip())<=64 or role not in _ALLOWED_ROLES:
            raise ValueError("Invalid user profile")
        user_id = _uuid()
        with _open(self.path) as conn:
            conn.execute("INSERT INTO tenant_users(user_id,label,role,created_at) VALUES(?,?,?,?)",
                         (user_id,label.strip(),role,_now()))
            conn.execute("""INSERT INTO tenant_audit_events(created_at,user_id,action)
                VALUES(?,?,'USER_PROVISIONED')""",(_now(),user_id))
        return user_id

    def add_connection(self, user_id, secret):
        """Encrypt one verified Public credential. No plaintext persisted."""
        if not isinstance(secret,str) or not 20<=len(secret.strip())<=2048 or any(
                ch in secret for ch in "\r\n\0"):
            raise ValueError("Invalid Public credential")
        cipher=self._fernet().encrypt(secret.strip().encode("utf-8"))
        connection_id=_uuid()
        with _open(self.path) as conn:
            self._active_user(conn,user_id)
            conn.execute("""INSERT INTO tenant_connections
                (connection_id,user_id,provider,credential_ciphertext,created_at)
                VALUES(?,?,'public',?,?)""",(connection_id,user_id,cipher,_now()))
            conn.execute("""INSERT INTO tenant_audit_events(created_at,user_id,action)
                VALUES(?,?,'CONNECTION_ADDED')""",(_now(),user_id))
        return connection_id

    def link_account(self, user_id, connection_id, provider_account_ref, label):
        """Future caller must first verify broker account ownership with Public."""
        if (not isinstance(provider_account_ref,str) or
            not 1<=len(provider_account_ref.strip())<=128 or
            not isinstance(label,str) or not 1<=len(label.strip())<=64):
            raise ValueError("Invalid broker account reference")
        account_id=_uuid()
        with _open(self.path) as conn:
            self._active_user(conn,user_id)
            row=conn.execute("""SELECT connection_id FROM tenant_connections
                WHERE connection_id=? AND user_id=? AND revoked_at IS NULL""",
                (connection_id,user_id)).fetchone()
            if row is None:
                raise TenantAccessError("Public connection unavailable to this user")
            conn.execute("""INSERT INTO tenant_accounts
                (account_id,user_id,connection_id,provider,provider_account_ref,label,created_at)
                VALUES(?,?,?,'public',?,?,?)""",
                (account_id,user_id,connection_id,provider_account_ref.strip(),label.strip(),_now()))
            conn.execute("""INSERT INTO tenant_audit_events(created_at,user_id,account_id,action)
                VALUES(?,?,?,'ACCOUNT_LINKED')""",(_now(),user_id,account_id))
        return account_id

    def list_accounts(self, user_id):
        with _open(self.path) as conn:
            self._active_user(conn,user_id)
            return [dict(row) for row in conn.execute("""SELECT account_id,label,provider
                FROM tenant_accounts WHERE user_id=? AND disabled_at IS NULL
                ORDER BY created_at,account_id""",(user_id,))]

    def account_setting(self, user_id, account_id, key, value=None):
        """Scoped nonsecret config. None reads; strings write."""
        if key not in _ALLOWED_ACCOUNT_SETTINGS:
            raise ValueError("Unsupported tenant account setting")
        with _open(self.path) as conn:
            self._active_user(conn,user_id)
            self._active_account(conn,user_id,account_id)
            if value is None:
                row=conn.execute("""SELECT setting_value FROM tenant_account_settings
                    WHERE user_id=? AND account_id=? AND setting_key=?""",
                    (user_id,account_id,key)).fetchone()
                return row["setting_value"] if row else None
            if not isinstance(value,str) or len(value)>1024:
                raise ValueError("Invalid setting value")
            conn.execute("""INSERT INTO tenant_account_settings
                (user_id,account_id,setting_key,setting_value) VALUES(?,?,?,?)
                ON CONFLICT(account_id,user_id,setting_key)
                DO UPDATE SET setting_value=excluded.setting_value""",
                (user_id,account_id,key,value))
            conn.execute("""INSERT INTO tenant_audit_events(created_at,user_id,account_id,action)
                VALUES(?,?,?,'ACCOUNT_SETTING_CHANGED')""",(_now(),user_id,account_id))
