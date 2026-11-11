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
                or configured != str(target)
                or legacy != root / LEGACY_FILENAME
                or legacy.is_symlink() or not legacy.is_file()):
            raise SharedStorageDenied("Database paths must remain on the existing persistent disk")
        if target.exists() and legacy.samefile(target):
            raise SharedStorageDenied("Legacy and tenant files must not share an inode")
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



def _verify_first_permanent_owner(tenant_path):
    """Fail closed before retiring the old login without an enrolled owner.

    Read-only by design: no automatic member creation, token migration or
    password reset. Caller must independently prove a real login and recovery.
    """
    tenant = Path(tenant_path)
    try:
        info = tenant.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) & 0o077):
            raise SharedStorageDenied("Permanent owner identity storage unsafe")
        with sqlite3.connect(tenant.as_uri() + "?mode=ro", uri=True, timeout=10) as db:
            db.execute("PRAGMA query_only=ON")
            tables = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if (not {"tenant_schema_meta", "tenant_users", "tenant_identities"}.issubset(tables)
                    or {"broker_credentials", "settings", "orders"} & tables):
                raise SharedStorageDenied("Independent owner identity schema unavailable")
            if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise SharedStorageDenied("Independent owner identity integrity unavailable")
            if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise SharedStorageDenied("Independent owner identity integrity unavailable")
            owner_total = db.execute(
                "SELECT COUNT(*) FROM tenant_users WHERE role='owner'").fetchone()[0]
            owner_active = db.execute("""SELECT COUNT(*) FROM tenant_users u
                JOIN tenant_identities i ON i.user_id=u.user_id
                WHERE u.role='owner' AND u.disabled_at IS NULL
                  AND i.password_hash LIKE '$argon2id$%'""").fetchone()[0]
            user_total = db.execute("SELECT COUNT(*) FROM tenant_users").fetchone()[0]
            identity_total = db.execute("SELECT COUNT(*) FROM tenant_identities").fetchone()[0]
            if (owner_total != 1 or owner_active != 1 or user_total != identity_total
                    or user_total < 1 or user_total > 10):
                raise SharedStorageDenied("Independent first owner is not safely enrolled")
    except SharedStorageDenied:
        raise
    except (OSError, ValueError, sqlite3.Error):
        raise SharedStorageDenied("Permanent first owner cannot be verified") from None


def permanent_identity_policy(env, legacy_path, tenant_path):
    """Gate permanent tenant-only routing and Android app-origin verification.

    Both switches default off. Neither grants a Public connection, new member
    enrollment, orders, transfers or legacy owner credential inheritance.
    A prepared separate DB is required before either switch can activate.
    """
    tenant_only = _flag(env, "EDGE_PERMANENT_TENANTS_ONLY")
    native = _flag(env, "EDGE_PERMANENT_ANDROID_PASSKEY_ORIGIN_ENABLED")
    if not (tenant_only or native):
        return {"tenant_only": False, "android_signer_sha256": None}
    if (Path(tenant_path) == Path(legacy_path)
            or not _flag(env, "EDGE_SHARED_TENANT_DB_PREPARE")
            or not _flag(env, "EDGE_TENANT_SCHEMA_PREPARE")
            or not _flag(env, "EDGE_IDENTITY_AUTH_ENABLED")
            or _flag(env, "EDGE_ISOLATED_STAGING")
            or _flag(env, "EDGE_AUTOMATION_WORKER_ENABLED")
            or _flag(env, "ENABLE_LIVE_ORDERS")):
        raise SharedStorageDenied("Permanent identity requires the isolated inactive shared backend")
    # Never retire the known working legacy owner login before a valid
    # independently enrolled tenant owner exists. Read-only; cannot prove
    # the human can log in or recover their identity.
    if tenant_only:
        _verify_first_permanent_owner(tenant_path)
    if not native:
        return {"tenant_only": tenant_only, "android_signer_sha256": None}
    if not tenant_only or not _flag(env, "EDGE_TENANT_PASSKEYS_ENABLED"):
        raise SharedStorageDenied("Production app passkeys require explicit tenant-only identity mode")
    rp = str(env.get("EDGE_WEBAUTHN_RP_ID", ""))
    origin = str(env.get("EDGE_WEBAUTHN_ORIGIN", ""))
    package = str(env.get("EDGE_ANDROID_ASSOCIATION_PACKAGE", ""))
    fingerprint = str(env.get("EDGE_ANDROID_CERT_SHA256", "")).upper()
    import re
    if (rp != "edgepilot.belenoscreations.biz"
            or origin != "https://edgepilot.belenoscreations.biz"
            or package != ""
            or not re.fullmatch(r"(?:[0-9A-F]{2}:){31}[0-9A-F]{2}", fingerprint)):
        raise SharedStorageDenied("Production signed app association is not independently pinned")
    return {"tenant_only": True, "android_signer_sha256": fingerprint}
