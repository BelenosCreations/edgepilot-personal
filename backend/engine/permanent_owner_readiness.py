"""Private read-only owner enrollment readiness inspector.

This does not create an owner, authenticate a password, transfer brokerage
data, change routing, or prove physical-device acceptance. Unlike static
schema readiness, it checks whether an initial real owner identity is
present in the separate tenant database after deliberate manual bootstrap.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path

from . import permanent_cutover_preflight as preflight
from . import shared_storage_cutover as storage


class OwnerReadinessDenied(RuntimeError):
    """Sanitized, nonsecret refusal."""


REQUIRED_TENANT = preflight.TENANT_TABLES
FORBIDDEN_TENANT = frozenset(("settings", "broker_credentials", "orders", "activity"))
DORMANT_FLAGS = (
    "EDGE_PERMANENT_TENANTS_ONLY",
    "EDGE_PERMANENT_ANDROID_PASSKEY_ORIGIN_ENABLED",
    "EDGE_AUTOMATION_WORKER_ENABLED",
    "ENABLE_LIVE_ORDERS",
    "EDGE_ISOLATED_STAGING",
    "EDGE_TENANT_SIGNUP_ENABLED",
    "EDGE_PERMANENT_OWNER_INVITES_ENABLED",
    "EDGE_TENANT_PUBLIC_VAULT_ENABLED",
    "EDGE_TENANT_PUBLIC_READONLY_ENABLED",
    "EDGE_TENANT_ACCOUNT_READS_ENABLED",
    "EDGE_TENANT_MONITOR_PREVIEW_ENABLED",
    "EDGE_TENANT_WATCHLIST_EDIT_ENABLED",
)


def inspect_owner_readiness(env, legacy_path, tenant_path, *, persistent_root=None):
    """Read-only inspection suitable before or after manual owner bootstrap.

    Never returns an identity, username, password hash, private key, API key,
    balance, account identifier or ciphertext. A passing report is NOT an
    authorization to switch tenant-only routing or activate brokerage.
    """
    try:
        if not storage._flag(env, "EDGE_OWNER_READINESS_AUDIT_ALLOWED"):
            raise OwnerReadinessDenied("Operator readiness audit not enabled")
        if any(storage._flag(env, key) for key in DORMANT_FLAGS):
            raise OwnerReadinessDenied("Owner readiness inspection requires dormant operations")
        root = storage.PERSISTENT_ROOT if persistent_root is None else Path(persistent_root)
        legacy, tenant = Path(legacy_path), Path(tenant_path)
        if (not root.is_absolute() or root.is_symlink() or
                legacy != root / storage.LEGACY_FILENAME or
                tenant != root / storage.TENANT_FILENAME or
                not storage._flag(env, "EDGE_SHARED_TENANT_DB_PREPARE") or
                not storage._flag(env, "EDGE_TENANT_SCHEMA_PREPARE") or
                str(env.get("EDGE_TENANT_DB_PATH", "")) != str(tenant) or
                not preflight._private_regular_file(legacy) or
                not preflight._private_regular_file(tenant) or
                legacy.lstat().st_uid != os.geteuid() or
                tenant.lstat().st_uid != os.geteuid() or
                legacy.samefile(tenant)):
            raise OwnerReadinessDenied("Private separated databases required")
        preflight._verify_database(
            legacy, preflight.LEGACY_TABLES, frozenset(("tenant_users",)))
        preflight._verify_database(tenant, REQUIRED_TENANT, FORBIDDEN_TENANT)
        with closing(sqlite3.connect(tenant.as_uri() + "?mode=ro",
                                     uri=True, timeout=10)) as db:
            db.execute("PRAGMA query_only=ON")
            # Aggregate counts only. No user identifiers or password hashes
            # leave SQLite, including on denial.
            users, owners, owner_identities, identities, unbound = db.execute("""
                SELECT
                  (SELECT COUNT(*) FROM tenant_users),
                  (SELECT COUNT(*) FROM tenant_users WHERE role='owner' AND disabled_at IS NULL),
                  (SELECT COUNT(*) FROM tenant_users u JOIN tenant_identities i
                      ON i.user_id=u.user_id
                      WHERE u.role='owner' AND u.disabled_at IS NULL
                      AND LENGTH(i.password_hash)>0),
                  (SELECT COUNT(*) FROM tenant_identities),
                  (SELECT COUNT(*) FROM tenant_identities i LEFT JOIN tenant_users u
                    ON u.user_id=i.user_id WHERE u.user_id IS NULL)
                """).fetchone()
            suspicious_owner = db.execute("""
                SELECT COUNT(*) FROM tenant_users u WHERE u.role='owner' AND
                  (u.disabled_at IS NOT NULL OR
                   NOT EXISTS(SELECT 1 FROM tenant_identities i
                              WHERE i.user_id=u.user_id))
                """).fetchone()[0]
        if (owners > 1 or unbound or suspicious_owner or identities > users or
                (users == 0 and identities != 0) or
                (users > 0 and (owners != 1 or owner_identities != 1))):
            raise OwnerReadinessDenied("Independent owner identity not safely established")
        # A non-owner member without an identity is also a bad partial state
        # for activation. This tool must remain useful at exactly 0 members.
        if identities != users:
            raise OwnerReadinessDenied("Unpaired member records exist")

        return {
            "inspection": "passed",
            "separate_private_tenant_database": True,
            "tenant_owner_initialized": owners == 1,
            "tenant_owner_has_password_identity": owner_identities == 1,
            "tenant_member_count": users,
            "next_operator_stage": (
                "manual_owner_identity_login_test" if owners == 1
                else "manual_first_owner_bootstrap"
            ),
            "independent_owner_login_verified": False,
            "owner_public_connection_verified": False,
            "second_physical_device_verified": False,
            "legacy_data_migration_verified": False,
            "authorized_to_activate": False,
            "live_trading_enabled": False,
            "bank_transfers_enabled": False,
        }
    except OwnerReadinessDenied:
        raise
    except (ValueError, OSError, sqlite3.Error, storage.SharedStorageDenied,
            preflight.CutoverPreflightDenied):
        raise OwnerReadinessDenied("Private owner readiness inspection denied safely") from None
