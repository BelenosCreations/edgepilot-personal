"""Console-only preparation of an independent, empty tenant SQLite database.

The legacy owner DB is opened READ-ONLY. The new tenant DB is constructed
privately in a same-disk staging file, inspected, and installed with a
no-replace hard-link. Nothing is copied or migrated from the legacy owner.
Neither Flask startup nor deployment imports or executes this tool.
"""
from __future__ import annotations

import os
import sqlite3
import stat
import tempfile
from pathlib import Path

from . import identity_auth, permanent_cutover_preflight as preflight
from . import shared_storage_cutover as storage, tenant_foundation


class PrivateStorageInitDenied(RuntimeError):
    """Nonsecret, fail-closed operator error."""


APPROVAL = "PREPARE ISOLATED EDGEPILOT STORAGE"

# Initialization must never coexist with active member onboarding, brokerage,
# monitoring, worker, order, or permanent tenant-only routing.
DORMANT_FLAGS = (
    "EDGE_PERMANENT_TENANTS_ONLY",
    "EDGE_PERMANENT_READONLY_PILOT_ENABLED",
    "EDGE_PERMANENT_ANDROID_PASSKEY_ORIGIN_ENABLED",
    "EDGE_IDENTITY_AUTH_ENABLED",
    "EDGE_OWNER_BOOTSTRAP_ALLOWED",
    "EDGE_TENANT_SIGNUP_ENABLED",
    "EDGE_TENANT_PASSKEYS_ENABLED",
    "EDGE_TENANT_PASSWORD_CHANGE_ENABLED",
    "EDGE_TENANT_SESSION_CONTROLS_ENABLED",
    "EDGE_PERMANENT_OWNER_INVITES_ENABLED",
    "EDGE_TENANT_PUBLIC_VAULT_ENABLED",
    "EDGE_TENANT_PUBLIC_READONLY_ENABLED",
    "EDGE_TENANT_ACCOUNT_READS_ENABLED",
    "EDGE_TENANT_MONITOR_PREVIEW_ENABLED",
    "EDGE_TENANT_WATCHLIST_EDIT_ENABLED",
    "EDGE_AUTOMATION_WORKER_ENABLED",
    "ENABLE_LIVE_ORDERS",
    "EDGE_ISOLATED_STAGING",
)

TENANT_REQUIRED = preflight.TENANT_TABLES
TENANT_FORBIDDEN = frozenset(("settings", "broker_credentials", "orders", "activity"))


def _private_owned(path: Path) -> bool:
    info = path.lstat()
    return (stat.S_ISREG(info.st_mode)
            and info.st_nlink == 1
            and info.st_uid == os.geteuid()
            and not (stat.S_IMODE(info.st_mode) & 0o077))


def prepare_private_tenant_storage(
        env, legacy_path, tenant_path, *, approval, persistent_root=None):
    """Create one PRIVATE empty DB and nothing else; refuse reruns.

    Requires a separately verified fresh off-service encrypted backup and
    tested restore BEFORE an operator invokes this function. Those facts
    cannot be established remotely here; an approval phrase is not proof.
    """
    if (approval != APPROVAL
            or str(env.get("EDGE_PERMANENT_STORAGE_INIT_ALLOWED", "")) != "true"):
        raise PrivateStorageInitDenied("PRIVATE_STORAGE_APPROVAL_DENIED")
    phase = "RUNTIME_FLAGS"
    try:
        if any(storage._flag(env, key) for key in DORMANT_FLAGS):
            raise PrivateStorageInitDenied("Storage preparation requires every active feature disabled")
        phase = "STORAGE_SELECTOR"
        root = storage.PERSISTENT_ROOT if persistent_root is None else Path(persistent_root)
        legacy, target = Path(legacy_path), Path(tenant_path)
        selected = storage.select_tenant_database(
            env, legacy, persistent_root=root)
        phase = "DISK_LAYOUT"
        if (not root.is_absolute() or not root.is_dir() or root.is_symlink()
                or selected != root / storage.TENANT_FILENAME
                or target != selected
                or legacy != root / storage.LEGACY_FILENAME
                or not _private_owned(legacy)):
            raise PrivateStorageInitDenied("Unexpected or unprotected paid disk layout")
        phase = "DESTINATION_EXISTS"
        if target.exists() or target.is_symlink():
            raise PrivateStorageInitDenied("Tenant database exists; nothing will be overwritten")

        # This read-only inspection must never run a legacy schema initializer.
        phase = "LEGACY_READONLY_CHECK"
        preflight._verify_database(
            legacy, preflight.LEGACY_TABLES, frozenset(("tenant_users",)))
        original = legacy.lstat()
        staged = None
        old_umask = os.umask(0o077)
        try:
            phase = "PRIVATE_STAGE_CREATE"
            fd, temp_name = tempfile.mkstemp(prefix=".edgepilot-tenant-stage-", dir=root)
            staged = Path(temp_name)
            try:
                os.fchmod(fd, 0o600)
            finally:
                os.close(fd)

            phase = "TENANT_SCHEMA_CREATE"
            tenant_foundation.setup(str(staged))
            phase = "IDENTITY_SCHEMA_CREATE"
            identity_auth.setup(str(staged))
            phase = "STAGE_PRIVATE_MODE"
            if not _private_owned(staged):
                raise PrivateStorageInitDenied("Tenant staging permissions invalid")
            phase = "TENANT_READONLY_CHECK"
            members = preflight._verify_database(staged, TENANT_REQUIRED, TENANT_FORBIDDEN)
            if members != 0:
                raise PrivateStorageInitDenied("Tenant staging must contain zero members")
            phase = "EMPTY_IDENTITY_CHECK"
            with sqlite3.connect(staged.as_uri() + "?mode=ro", uri=True) as db:
                if db.execute("SELECT COUNT(*) FROM tenant_identities").fetchone()[0]:
                    raise PrivateStorageInitDenied("Tenant staging contains an identity")

            # Detect unexpected owner replacement before publishing any new file.
            phase = "LEGACY_RECHECK"
            after = legacy.lstat()
            if (after.st_dev != original.st_dev or after.st_ino != original.st_ino
                    or not _private_owned(legacy)):
                raise PrivateStorageInitDenied("Owner storage changed during preparation")
            preflight._verify_database(
                legacy, preflight.LEGACY_TABLES, frozenset(("tenant_users",))
            )
            phase = "DESTINATION_RACE_CHECK"
            if target.exists() or target.is_symlink():
                raise PrivateStorageInitDenied("Tenant storage appeared during preparation")

            phase = "STAGE_FSYNC"
            with open(staged, "rb") as source:
                os.fsync(source.fileno())
            # Atomic exclusive publication on the existing paid disk. A
            # competing initializer cannot overwrite or adopt its target.
            phase = "NO_REPLACE_PUBLISH"
            os.link(staged, target, follow_symlinks=False)
        finally:
            os.umask(old_umask)
            if staged is not None:
                phase = "STAGE_CLEANUP"
                staged.unlink(missing_ok=True)
        return {
            "prepared": True,
            "private_tenant_database": True,
            "separate_from_legacy": True,
            "initial_tenant_members": 0,
            "owner_data_migrated": False,
            "owner_credentials_copied": False,
            "production_backup_and_restore_verified": False,
            "authorized_to_activate": False,
            "live_trading_enabled": False,
            "bank_transfers_enabled": False,
        }
    except PrivateStorageInitDenied:
        # Report ONLY a fixed, audited stage identifier. Do not disclose paths,
        # environment values, SQL, account state, OS errors or stack traces.
        raise PrivateStorageInitDenied("PRIVATE_STORAGE_BLOCKED_AT_" + phase) from None
    except (OSError, ValueError, RuntimeError, sqlite3.Error, storage.SharedStorageDenied,
            preflight.CutoverPreflightDenied):
        raise PrivateStorageInitDenied("PRIVATE_STORAGE_BLOCKED_AT_" + phase) from None
