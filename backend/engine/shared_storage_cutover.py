"""Fail-closed selection of a *separate* tenant SQLite file on owner's disk.

This is a dormant, one-instance migration preparation step, not automatic
legacy data migration or an authorization to onboard real Public accounts.
The existing paid web service already mounts /data. Without BOTH explicit
new settings this module preserves the original DB path exactly.
"""
from __future__ import annotations

from pathlib import Path

PERSISTENT_ROOT = Path("/data")
TENANT_FILENAME = "edgepilot-tenants.db"


class SharedStorageDenied(RuntimeError):
    """Configuration rejected without disclosing any secrets or DB contents."""


def select_tenant_database(env, legacy_path, *, persistent_root=None):
    """Choose tenant database before any new tenant schemas are initialized.

    No data is copied or deleted. The returned path is not opened here.
    This never accepts an attacker-chosen directory, URL or arbitrary file,
    nor silently falls back from an explicitly requested split database
    to the existing owner database.
    """
    legacy = Path(legacy_path)
    configured = str(env.get("EDGE_TENANT_DB_PATH", ""))
    gate = str(env.get("EDGE_SHARED_TENANT_DB_PREPARE", "false")).lower()
    if gate not in ("true", "false", ""):
        raise SharedStorageDenied("Invalid shared-storage preparation flag")
    if not configured:
        if gate == "true":
            raise SharedStorageDenied("Shared tenant database path required")
        return legacy
    if (gate != "true" or
            str(env.get("EDGE_TENANT_SCHEMA_PREPARE", "false")).lower() != "true" or
            str(env.get("EDGE_ISOLATED_STAGING", "false")).lower() != "false"):
        raise SharedStorageDenied("Shared paid-backend storage requires explicit dormant preparation")
    if (str(env.get("EDGE_TENANT_PUBLIC_VAULT_ENABLED", "false")).lower() != "false" or
            str(env.get("EDGE_TENANT_PUBLIC_READONLY_ENABLED", "false")).lower() != "false" or
            str(env.get("EDGE_TENANT_ACCOUNT_READS_ENABLED", "false")).lower() != "false" or
            str(env.get("ENABLE_LIVE_ORDERS", "false")).lower() != "false"):
        raise SharedStorageDenied("Separate tenant database cannot activate brokerage access")
    root = PERSISTENT_ROOT if persistent_root is None else Path(persistent_root)
    target = root / TENANT_FILENAME
    try:
        if (not root.is_absolute() or not root.is_dir() or root.is_symlink()
                or target.is_symlink()
                or configured != str(target)
                or not legacy.is_absolute() or legacy.is_symlink()
                or legacy.parent != root or legacy == target):
            raise SharedStorageDenied("Shared storage path is not an isolated persistent disk file")
        if target.exists() and not target.is_file():
            raise SharedStorageDenied("Shared storage target is not a regular file")
    except (ValueError, OSError, RuntimeError) as exc:
        if isinstance(exc, SharedStorageDenied):
            raise
        raise SharedStorageDenied("Shared storage path is unavailable") from None
    return target
