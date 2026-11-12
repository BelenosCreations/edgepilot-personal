"""Operator-only read-only readiness audit for future independent family users.

This module deliberately has no web route, cron job, startup hook, migration,
archive writer, or brokerage-network access. Even a successful inspection is
not authorization to invite a user or enable a worker, trade, or transfer.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from . import permanent_cutover_preflight as preflight
from . import shared_storage_cutover as storage

APPROVAL_FLAG = "EDGE_FAMILY_RECOVERY_INSPECT_ALLOWED"
REQUIRED_TRUE = (
    "EDGE_SHARED_TENANT_DB_PREPARE",
    "EDGE_TENANT_SCHEMA_PREPARE",
    "EDGE_IDENTITY_AUTH_ENABLED",
    "EDGE_PERMANENT_READONLY_PILOT_ENABLED",
    "EDGE_TENANT_ACCOUNT_READS_ENABLED",
    "EDGE_TENANT_PUBLIC_VAULT_ENABLED",
    "EDGE_TENANT_PUBLIC_READONLY_ENABLED",
    "EDGE_TENANT_PUBLIC_DISCOVERY_ONLY",
)
REQUIRED_FALSE = (
    "EDGE_PERMANENT_TENANTS_ONLY",
    "EDGE_AUTOMATION_WORKER_ENABLED",
    "ENABLE_LIVE_ORDERS",
    "EDGE_ISOLATED_STAGING",
    "EDGE_TENANT_SIGNUP_ENABLED",
    "EDGE_PERMANENT_OWNER_INVITES_ENABLED",
    "EDGE_TENANT_PASSKEYS_ENABLED",
    "EDGE_PERMANENT_ANDROID_PASSKEY_ORIGIN_ENABLED",
    "EDGE_TENANT_MONITOR_PREVIEW_ENABLED",
    "EDGE_TENANT_WATCHLIST_EDIT_ENABLED",
)
MAX_PRIVATE_USERS = 10


class FamilyRecoveryReadinessDenied(RuntimeError):
    """Refusal text is always constant; never expose owner data or secrets."""


def inspect_family_recovery(env, legacy_path, tenant_path, *,
                            persistent_root=None):
    """Inspect two private existing SQLite files without changing either.

    Return aggregate counts only. Verify every independent identity is
    paired, encrypted broker secrets remain decryptable with the CURRENT
    Fernet key, and a Public secret is not silently shared by two users.
    Does not write an archive, prove cloud backup, or call Public.
    """
    try:
        if (not isinstance(env, dict) or
                env.get(APPROVAL_FLAG) != "true" or
                any(env.get(flag) != "true" for flag in REQUIRED_TRUE) or
                any(storage._flag(env, flag) for flag in REQUIRED_FALSE)):
            raise FamilyRecoveryReadinessDenied(
                "Family recovery inspection requires safe operator-only flags")
        root = (storage.PERSISTENT_ROOT if persistent_root is None
                else Path(persistent_root))
        legacy, tenant = Path(legacy_path), Path(tenant_path)
        if (not root.is_absolute() or root.is_symlink() or
                legacy != root / storage.LEGACY_FILENAME or
                tenant != root / storage.TENANT_FILENAME or
                env.get("EDGE_DB_PATH") != str(legacy) or
                env.get("EDGE_TENANT_DB_PATH") != str(tenant) or
                not preflight._private_regular_file(legacy) or
                not preflight._private_regular_file(tenant) or
                legacy.lstat().st_uid != os.geteuid() or
                tenant.lstat().st_uid != os.geteuid() or
                legacy.samefile(tenant)):
            raise FamilyRecoveryReadinessDenied(
                "Separate private owner and tenant storage is required")
        preflight._verify_database(
            legacy, preflight.LEGACY_TABLES, frozenset(("tenant_users",)))
        count = preflight._verify_database(
            tenant, preflight.TENANT_TABLES,
            frozenset(("settings", "broker_credentials", "orders", "activity")))
        if not 1 <= count <= MAX_PRIVATE_USERS:
            raise FamilyRecoveryReadinessDenied(
                "Independent tenant capacity or owner is not safe")
        raw_key = env.get("EDGE_CREDENTIAL_KEY", "")
        if not isinstance(raw_key, str) or not raw_key:
            raise FamilyRecoveryReadinessDenied(
                "Existing encrypted credential key is required")
        try:
            vault = Fernet(raw_key.encode("ascii"))
        except (ValueError, TypeError, UnicodeError):
            raise FamilyRecoveryReadinessDenied(
                "Existing encrypted credential key is invalid") from None

        with closing(sqlite3.connect(tenant.as_uri() + "?mode=ro",
                                     uri=True, timeout=15)) as db:
            db.execute("PRAGMA query_only=ON")
            users = db.execute(
                "SELECT user_id, role, disabled_at FROM tenant_users").fetchall()
            identities = db.execute(
                "SELECT user_id, password_hash FROM tenant_identities").fetchall()
            valid_owner = sum(role == "owner" and disabled is None
                              for _, role, disabled in users)
            if (valid_owner != 1 or
                    sum(role == "owner" for _, role, _ in users) != 1 or
                    len(identities) != len(users) or
                    len({u for u, _, _ in users}) != len(users) or
                    {u for u, _ in identities} != {u for u, _, _ in users} or
                    any(not isinstance(h, str) or
                        not h.startswith("$argon2id$")
                        for _, h in identities)):
                raise FamilyRecoveryReadinessDenied(
                    "Owner and member identities are not fully paired")
            enabled_users = {user for user, _, disabled in users if disabled is None}
            if not enabled_users:
                raise FamilyRecoveryReadinessDenied(
                    "No active private tenant owner")

            seen_secrets = {}
            active_connection_users = set()
            connections = db.execute(
                "SELECT user_id, credential_ciphertext, revoked_at "
                "FROM tenant_connections WHERE provider='public'").fetchall()
            for user, ciphertext, revoked in connections:
                if (user not in {u for u, _, _ in users} or
                        not isinstance(ciphertext, bytes) or len(ciphertext) < 80):
                    raise FamilyRecoveryReadinessDenied(
                        "Independent encrypted connection is invalid")
                try:
                    secret = vault.decrypt(ciphertext)
                    if (not 20 <= len(secret) <= 2048 or
                            any(c in secret for c in (b"\x00", b"\r", b"\n"))):
                        raise ValueError()
                except (InvalidToken, TypeError, ValueError):
                    raise FamilyRecoveryReadinessDenied(
                        "Encrypted Public connection cannot be recovered") from None
                # Never print the value or a digest. The equality check is
                # internal only; distinct users must not reuse one API key.
                digest = hashlib.sha256(secret).digest()
                secret = None
                prior = seen_secrets.get(digest)
                if prior is not None and prior != user:
                    raise FamilyRecoveryReadinessDenied(
                        "Independent members must not share a Public credential")
                seen_secrets[digest] = user
                if revoked is None and user in enabled_users:
                    active_connection_users.add(user)

            links = db.execute("""SELECT a.user_id, a.disabled_at, c.revoked_at
                FROM tenant_accounts a JOIN tenant_connections c
                  ON c.connection_id=a.connection_id AND c.user_id=a.user_id
                WHERE a.provider='public' AND c.provider='public'""").fetchall()
            linked_users = {user for user, disabled, revoked in links
                            if user in enabled_users and
                            disabled is None and revoked is None}
            if (len(links) != db.execute(
                    "SELECT COUNT(*) FROM tenant_accounts").fetchone()[0] or
                    any(disabled is None and revoked is not None
                        for _, disabled, revoked in links) or
                    any(user not in active_connection_users for user in linked_users)):
                raise FamilyRecoveryReadinessDenied(
                    "Verified account binding is not correctly isolated")
            active_sessions = db.execute(
                "SELECT COUNT(*) FROM tenant_identity_sessions").fetchone()[0]
        return {
            "inspection": "passed",
            "private_isolated_database_files": True,
            "independent_identities": len(users),
            "active_identities": len(enabled_users),
            "encrypted_public_connections": len(connections),
            "active_linked_accounts": sum(
                disabled is None and revoked is None and user in enabled_users
                for user, disabled, revoked in links),
            "active_identity_sessions": active_sessions,
            "two_independent_linked_users_in_storage": len(linked_users) >= 2,
            "encrypted_multiuser_archive_verified": False,
            "second_physical_device_verified": False,
            "real_second_broker_verified": False,
            "authorized_to_activate": False,
            "live_trading_enabled": False,
            "bank_transfers_enabled": False,
        }
    except FamilyRecoveryReadinessDenied:
        raise
    except (ValueError, OSError, TypeError, sqlite3.Error,
            preflight.CutoverPreflightDenied, storage.SharedStorageDenied):
        raise FamilyRecoveryReadinessDenied(
            "Family recovery inspection denied safely") from None
