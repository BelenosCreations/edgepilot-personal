"""Read-only console preflight for the already paid permanent EdgePilot backend.

Never copies, edits, decrypts, or logs legacy/tenant data. Does not assert
that an encrypted external backup or real account recovery exists. Run only
on the trusted operator console after the isolated tenant DB is prepared.
"""
from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path

from . import shared_storage_cutover as storage


class CutoverPreflightDenied(RuntimeError):
    """A deliberately generic diagnostic without credentials or record values."""


LEGACY_TABLES = frozenset(("settings", "broker_credentials", "orders", "activity"))
TENANT_TABLES = frozenset((
    "tenant_schema_meta", "tenant_users", "tenant_identities",
    "tenant_identity_sessions", "tenant_audit_events",
))


def _private_regular_file(path):
    """Refuse symlinks, linked files, non-regular files, and shared permissions."""
    info = path.lstat()
    return (stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            and stat.S_IMODE(info.st_mode) & 0o077 == 0)


def _verify_database(path, required, forbidden):
    # mode=ro + query_only; never run migrations or application setup.
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10) as db:
        db.execute("PRAGMA query_only=ON")
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not required.issubset(tables) or (forbidden & tables):
            raise CutoverPreflightDenied("Storage schema is not isolated")
        if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise CutoverPreflightDenied("Storage integrity inspection failed")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise CutoverPreflightDenied("Storage relational integrity inspection failed")
        return db.execute("SELECT COUNT(*) FROM tenant_users").fetchone()[0] if (
            "tenant_users" in required) else None


def inspect_cutover(env, legacy_path, tenant_path, *, persistent_root=None):
    """Inspect two prepared databases and return only nonsecret state flags.

    Passing this inspection is NOT authority to run the bootstrap, migrate
    historical rows, enable identity/passkey/Public access, or retire legacy
    endpoints. Independently verified encrypted backup/restore is mandatory.
    """
    try:
        if storage._flag(env, "EDGE_CUTOVER_PREFLIGHT_ALLOWED") is not True:
            raise CutoverPreflightDenied("Console inspection was not enabled")
        for key in ("EDGE_PERMANENT_TENANTS_ONLY",
                    "EDGE_PERMANENT_READONLY_PILOT_ENABLED",
                    "EDGE_PERMANENT_ANDROID_PASSKEY_ORIGIN_ENABLED",
                    "EDGE_AUTOMATION_WORKER_ENABLED", "ENABLE_LIVE_ORDERS",
                    "EDGE_ISOLATED_STAGING", "EDGE_TENANT_SIGNUP_ENABLED"):
            if storage._flag(env, key):
                raise CutoverPreflightDenied("Inspection requires dormant cutover settings")
        selected = storage.select_tenant_database(
            env, legacy_path, persistent_root=persistent_root)
        root = storage.PERSISTENT_ROOT if persistent_root is None else Path(persistent_root)
        legacy, tenant = Path(legacy_path), Path(tenant_path)
        if (not root.is_absolute() or root.is_symlink() or
                legacy != root / storage.LEGACY_FILENAME or
                tenant != root / storage.TENANT_FILENAME or
                selected != tenant or legacy == tenant or
                not _private_regular_file(legacy) or
                not _private_regular_file(tenant) or
                legacy.samefile(tenant)):
            raise CutoverPreflightDenied("Private isolated disk files are required")
        _verify_database(legacy, LEGACY_TABLES, frozenset(("tenant_users",)))
        members = _verify_database(tenant, TENANT_TABLES,
                                   frozenset(("broker_credentials", "orders")))
        return {
            "inspection": "passed",
            "existing_paid_disk": True,
            "separate_database_files": True,
            "legacy_schema_intact": True,
            "tenant_identity_schema_intact": True,
            "tenant_has_members": bool(members),
            "production_backup_and_restore_verified": False,
            "authorized_to_activate": False,
            "live_trading_enabled": False,
            "bank_transfers_enabled": False,
        }
    except CutoverPreflightDenied:
        raise
    except (ValueError, OSError, sqlite3.Error, storage.SharedStorageDenied):
        raise CutoverPreflightDenied("Cutover inspection failed safely") from None
