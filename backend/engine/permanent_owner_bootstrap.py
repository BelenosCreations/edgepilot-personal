"""One-time, local-console-only first-owner creation on the permanent tenant DB.

NOT imported by Flask or exposed as HTTP. No copy of legacy Public keys,
balances, orders, sessions or history. Requires an existing separate,
restricted tenant database on the paid persistent disk, explicit gated
operator intent, and zero prior tenant user rows. No automatic migrations.
"""
from __future__ import annotations

import os
import sqlite3
import stat
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import identity_auth, shared_storage_cutover


class OwnerBootstrapDenied(RuntimeError):
    """Never include passwords, API keys, user identities or SQL contents."""


APPROVAL = "INITIALIZE FIRST EDGEPILOT OWNER"


def create_first_owner(env, legacy_path, tenant_path, *,
                       label, login_name, password, approval,
                       persistent_root=None):
    """Atomically create exactly one identity with the existing owner role.

    Caller must already have trusted local console access, and the app schema
    must already be prepared. On any failure the DB transaction rolls back.
    This is *not* a password reset, recovery tool, or an invitation issuer.
    """
    if approval != APPROVAL or str(env.get("EDGE_OWNER_BOOTSTRAP_ALLOWED", "")) != "true":
        raise OwnerBootstrapDenied("Offline owner bootstrap is disabled")
    if (str(env.get("EDGE_IDENTITY_AUTH_ENABLED", "false")).lower() != "true" or
            str(env.get("EDGE_PERMANENT_TENANTS_ONLY", "false")).lower() != "false" or
            str(env.get("EDGE_ISOLATED_STAGING", "false")).lower() != "false" or
            str(env.get("EDGE_TENANT_SIGNUP_ENABLED", "false")).lower() != "false"):
        raise OwnerBootstrapDenied("Offline owner initialization requires isolated identity preparation")
    try:
        selected = shared_storage_cutover.select_tenant_database(
            env, legacy_path, persistent_root=persistent_root)
        if Path(tenant_path) != selected or selected == Path(legacy_path):
            raise OwnerBootstrapDenied("A separate tenant database is required")
        root = shared_storage_cutover.PERSISTENT_ROOT if persistent_root is None else Path(persistent_root)
        target = root / shared_storage_cutover.TENANT_FILENAME
        if selected != target or selected.is_symlink() or not selected.is_file():
            raise OwnerBootstrapDenied("Existing private tenant database required")
        info = selected.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                stat.S_IMODE(info.st_mode) & 0o077):
            raise OwnerBootstrapDenied("Tenant database file permissions are unsafe")
        if (not isinstance(label, str) or not 1 <= len(label.strip()) <= 64
                or len(label) > 128 or any(c in label for c in "\x00\r\n")):
            raise OwnerBootstrapDenied("Owner identity configuration invalid")
        normalized = identity_auth._normalize_username(login_name)
        identity_auth._validate_password(password)
        # Hash outside the write lock; another concurrent bootstrap is still
        # rejected inside the serialized BEGIN IMMEDIATE transaction.
        encoded = identity_auth._HASHER.hash(password)
        created_at = int(time.time())
        new_user_id = str(uuid.uuid4())
        with sqlite3.connect(selected.as_uri() + "?mode=rw", uri=True, timeout=20) as db:
            db.execute("PRAGMA busy_timeout=20000")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            required = ("tenant_schema_meta", "tenant_users",
                        "tenant_identities", "tenant_identity_sessions",
                        "tenant_audit_events")
            if any(not db.execute("""SELECT 1 FROM sqlite_master
                    WHERE name=? AND type='table'""", (table,)).fetchone()
                    for table in required):
                raise OwnerBootstrapDenied("Prepared tenant identity schema required")
            if (db.execute("PRAGMA integrity_check").fetchone() != ("ok",)
                    or db.execute("PRAGMA foreign_key_check").fetchone() is not None):
                raise OwnerBootstrapDenied("Tenant database integrity unavailable")
            if (db.execute("SELECT COUNT(*) FROM tenant_users").fetchone()[0] != 0 or
                    db.execute("SELECT COUNT(*) FROM tenant_identities").fetchone()[0] != 0 or
                    db.execute("SELECT COUNT(*) FROM tenant_identity_sessions").fetchone()[0] != 0):
                raise OwnerBootstrapDenied("Existing tenant identities require a separate recovery procedure")
            iso = datetime.fromtimestamp(created_at, timezone.utc).isoformat()
            db.execute("""INSERT INTO tenant_users
                    (user_id,label,role,created_at) VALUES(?,?,'owner',?)""",
                    (new_user_id, label.strip(), iso))
            db.execute("""INSERT INTO tenant_identities
                    (user_id,login_name,password_hash,created_at)
                    VALUES(?,?,?,?)""", (new_user_id, normalized, encoded, created_at))
            db.execute("""INSERT INTO tenant_audit_events(created_at,user_id,action)
                    VALUES(?,?,'USER_PROVISIONED')""", (iso, new_user_id))
    except OwnerBootstrapDenied:
        raise
    except (ValueError, TypeError, OSError, sqlite3.Error,
            shared_storage_cutover.SharedStorageDenied):
        raise OwnerBootstrapDenied("Offline owner bootstrap failed safely") from None
    return {"created": True, "role": "owner",
            "legacyDataMigrated": False, "brokerConnected": False,
            "tradingEnabled": False, "fundTransfersEnabled": False}
