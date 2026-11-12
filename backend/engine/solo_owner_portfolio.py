"""Temporary single-owner read-only portfolio pilot (strictly opt-in).

This is a narrow transition step. The separate multi-user tenant schema,
owner invitations and future account isolation remain unchanged. When another
member exists, the pilot refuses *all* portfolio requests until a separately
reviewed multi-member read-only policy is enabled. No orders or transfers.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from . import shared_storage_cutover as storage

FLAG = "EDGE_SOLO_OWNER_PORTFOLIO_ENABLED"
REQUIRED = (
    "EDGE_SHARED_TENANT_DB_PREPARE",
    "EDGE_TENANT_SCHEMA_PREPARE",
    "EDGE_IDENTITY_AUTH_ENABLED",
    "EDGE_PERMANENT_READONLY_PILOT_ENABLED",
    "EDGE_TENANT_ACCOUNT_READS_ENABLED",
    "EDGE_TENANT_PUBLIC_VAULT_ENABLED",
    "EDGE_TENANT_PUBLIC_READONLY_ENABLED",
    "EDGE_TENANT_PUBLIC_DISCOVERY_ONLY",
)
FORBIDDEN = (
    "EDGE_PERMANENT_TENANTS_ONLY",
    "EDGE_ISOLATED_STAGING",
    "EDGE_AUTOMATION_WORKER_ENABLED",
    "ENABLE_LIVE_ORDERS",
    "EDGE_TENANT_PASSKEYS_ENABLED",
    "EDGE_PERMANENT_ANDROID_PASSKEY_ORIGIN_ENABLED",
    "EDGE_TENANT_MONITOR_PREVIEW_ENABLED",
    "EDGE_TENANT_WATCHLIST_EDIT_ENABLED",
)


class SoloOwnerPortfolioDenied(RuntimeError):
    """Fails closed without leaking identity, file or account information."""


def validate_pilot(env, legacy_path, tenant_path):
    """A separate default-off switch; no env or database writes."""
    try:
        enabled = storage._flag(env, FLAG)
        if not enabled:
            return False
        if (any(not storage._flag(env, key) for key in REQUIRED)
                or any(storage._flag(env, key) for key in FORBIDDEN)
                or Path(tenant_path) == Path(legacy_path)):
            raise SoloOwnerPortfolioDenied(
                "Single-owner read-only portfolio prerequisites are missing")
        # Invitation switches may remain enabled: do not silently reverse
        # approved multi-user work. The database-level check below prevents
        # access immediately after a second member registers.
        if storage._flag(env, "EDGE_FAMILY_INVITE_COEXISTENCE_ENABLED"):
            storage.family_invite_coexistence_policy(env)
        return True
    except (storage.SharedStorageDenied, TypeError, ValueError):
        raise SoloOwnerPortfolioDenied(
            "Single-owner read-only portfolio policy denied") from None


def active_for_owner(path, principal):
    """Only one currently enrolled owner; no global selected-account fallback.

    Recheck on EVERY read, so a newly registered member automatically closes
    the temporary single-user pilot, while preserving all identities/accounts.
    No credentials, user IDs or counts are returned to the caller.
    """
    if (not isinstance(principal, dict)
            or principal.get("role") != "owner"
            or not isinstance(principal.get("user_id"), str)
            or not principal["user_id"]):
        return False
    try:
        with closing(sqlite3.connect(
                Path(path).as_uri() + "?mode=ro",
                uri=True, timeout=10)) as db:
            db.execute("PRAGMA query_only=ON")
            users = db.execute("""SELECT user_id,role,disabled_at
                FROM tenant_users""").fetchall()
            if (len(users) != 1 or users[0][0] != principal["user_id"]
                    or users[0][1] != "owner" or users[0][2] is not None):
                return False
            identity = db.execute("""SELECT COUNT(*) FROM tenant_identities
                WHERE user_id=? AND password_hash LIKE '$argon2id$%'""",
                (principal["user_id"],)).fetchone()[0]
            if identity != 1:
                return False
            return db.execute(
                "SELECT COUNT(*) FROM tenant_identities").fetchone()[0] == 1
    except (sqlite3.Error, OSError, ValueError, TypeError):
        return False
