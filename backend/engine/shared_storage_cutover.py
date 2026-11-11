"""Safely split tenant identities from the existing owner's persistent SQLite.

No legacy rows, credentials, history or broker ownership are migrated here.
Opt-in configuration is mandatory and validation occurs before the application
opens any database. All file paths are fixed beneath the same paid /data mount.
This is for a single Render instance; it is not a distributed database.
"""
from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path

PERSISTENT_ROOT = Path("/data")
LEGACY_FILENAME = "edgepilot.db"
TENANT_FILENAME = "edgepilot-tenants.db"


class SharedStorageDenied(RuntimeError):
    """Fail closed without including credentials or sensitive file contents."""


def _flag(env, key):
    value = str(env.get(key, "false")).lower()
    if value not in ("true", "false", ""):
        raise SharedStorageDenied("Invalid shared-storage setting")
    return value == "true"


def select_tenant_database(env, legacy_path, *, persistent_root=None):
    """Return the separate tenant DB only with all required safety gates.

    Never silently fall back to the owner's DB after a split was requested.
    This selector does not touch files and is safe before legacy app startup.
    """
    legacy = Path(legacy_path)
    configured = str(env.get("EDGE_TENANT_DB_PATH", ""))
    enabled = _flag(env, "EDGE_SHARED_TENANT_DB_PREPARE")
    if not configured:
        if enabled:
            raise SharedStorageDenied("Separate tenant database path required")
        return legacy
    if (not enabled or not _flag(env, "EDGE_TENANT_SCHEMA_PREPARE")
            or _flag(env, "EDGE_ISOLATED_STAGING")
            or _flag(env, "EDGE_AUTOMATION_WORKER_ENABLED")
            or _flag(env, "ENABLE_LIVE_ORDERS")):
        raise SharedStorageDenied("Shared storage requires isolated, inactive preparation")
    # No real tenant brokerage or background operations during this milestone.
    for flag in ("EDGE_TENANT_PUBLIC_VAULT_ENABLED",
                 "EDGE_TENANT_PUBLIC_READONLY_ENABLED",
                 "EDGE_TENANT_ACCOUNT_READS_ENABLED",
                 "EDGE_TENANT_MONITOR_PREVIEW_ENABLED",
                 "EDGE_TENANT_WATCHLIST_EDIT_ENABLED"):
        if _flag(env, flag):
            raise SharedStorageDenied("Brokerage and tenant workers must stay disabled")
    root = PERSISTENT_ROOT if persistent_root is None else Path(persistent_root)
    target = root / TENANT_FILENAME
    try:
        if (not root.is_absolute() or not root.is_dir() or root.is_symlink()
                or configured != str(target) or
                legacy != root / LEGACY_FILENAME or legacy.is_symlink()
                or not legacy.is_file() or legacy.samefile(target) if target.exists() else
                not root.is_absolute() or not root.is_dir() or root.is_symlink()
                or configured != str(target) or
                legacy != root / LEGACY_FILENAME or legacy.is_symlink()
                or not legacy.is_file()):
            raise SharedStorageDenied("Database paths must remain on the existing persistent disk")
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise SharedStorageDenied("Tenant storage is not a regular private file")
    except (OSError, ValueError, RuntimeError) as exc:
        if isinstance(exc, SharedStorageDenied):
            raise
        raise SharedStorageDenied("Persistent database path validation failed") from None
    return target


def ensure_private_tenant_file(path, *, persistent_root=None):
    """Create only the fixed tenant file with 0600 or verify its existing mode.

    Call only after select_tenant_database grants opt-in. Never overwrite,
    unlink, chmod an existing file, or follow an existing symlink.
    """
    root = PERSISTENT_ROOT if persistent_root is None else Path(persistent_root)
    target = root / TENANT_FILENAME
    if Path(path) != target or root.is_symlink() or not root.is_dir():
        raise SharedStorageDenied("Unexpected tenant database destination")
    flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    try:
        try:
            fd = os.open(target, flags | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            fd = os.open(target, flags)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or stat.S_IMODE(info.st_mode) & 0o077):
                raise SharedStorageDenied("Tenant database permissions are unsafe")
            # A nonempty pre-existing database must already carry our tenant
            # schema marker; never silently adopt a foreign database file.
            if info.st_size:
                with sqlite3.connect(f"file:{target}?mode=ro", uri=True) as db:
                    found = db.execute("""SELECT 1 FROM sqlite_master
                        WHERE type='table' AND name='tenant_schema_meta'""").fetchone()
                if not found:
                    raise SharedStorageDenied("Tenant database schema cannot be verified")
        finally:
            os.close(fd)
    except (OSError, sqlite3.Error) as exc:
        raise SharedStorageDenied("Private tenant database could not be verified") from None
    return target
