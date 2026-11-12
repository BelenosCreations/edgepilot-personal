"""Dormant read-only readiness audit BEFORE a first private family invitation.

Never imported by Flask or invoked by a startup hook. No credentials, user
identifiers, database writes, provider requests or invitation issuance.
An audit pass does NOT approve production activation or supersede backup proof.
"""
from __future__ import annotations

import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from cryptography.fernet import Fernet

from . import permanent_cutover_preflight as preflight
from . import permanent_tenant_linked_backup as linked
from . import permanent_tenant_owner_backup as backup
from . import shared_storage_cutover as storage

AUDIT_FLAG = "EDGE_FAMILY_ROLLOUT_PREFLIGHT_ALLOWED"

# The exact existing discovery-only pilot must be running safely, while
# additional registration and owner invitation flags are STILL disabled.
REQUIRED_TRUE = tuple(
    key for key in storage.FAMILY_INVITE_REQUIRED
    if key not in ("EDGE_TENANT_SIGNUP_ENABLED",
                   "EDGE_PERMANENT_OWNER_INVITES_ENABLED")
)
REQUIRED_FALSE = storage.FAMILY_INVITE_FORBIDDEN + (
    "EDGE_FAMILY_INVITE_COEXISTENCE_ENABLED",
    "EDGE_TENANT_SIGNUP_ENABLED",
    "EDGE_PERMANENT_OWNER_INVITES_ENABLED",
)


class FamilyRolloutReadinessDenied(RuntimeError):
    """Static, nonsecret diagnostic denial with no account metadata."""


def inspect_first_invitation_readiness(env, legacy_path, tenant_path, *,
                                      persistent_root=None, now=None):
    """Read two existing private files; report aggregate nonsecret state only.

    A successful result does not authorize changing ANY runtime setting,
    inviting a real member, exporting a backup or contacting Public.
    """
    try:
        if (not isinstance(env, dict) or env.get(AUDIT_FLAG) != "true"
                or any(not storage._flag(env, k) for k in REQUIRED_TRUE)
                or any(storage._flag(env, k) for k in REQUIRED_FALSE)):
            raise FamilyRolloutReadinessDenied(
                "Independent first-invitation inspection requires dormant safety flags")
        root = storage.PERSISTENT_ROOT if persistent_root is None else Path(persistent_root)
        legacy, tenant = Path(legacy_path), Path(tenant_path)
        if (not root.is_absolute() or not root.is_dir() or root.is_symlink()
                or legacy != root / storage.LEGACY_FILENAME
                or tenant != root / storage.TENANT_FILENAME
                or env.get("EDGE_DB_PATH") != str(legacy)
                or env.get("EDGE_TENANT_DB_PATH") != str(tenant)
                or not backup._private(legacy)
                or not backup._private(tenant)
                or legacy.samefile(tenant)
                or legacy.lstat().st_uid != os.geteuid()
                or tenant.lstat().st_uid != os.geteuid()):
            raise FamilyRolloutReadinessDenied(
                "Two separate private persistent SQLite files are required")
        selected = storage.select_tenant_database(
            env, legacy, persistent_root=root)
        if selected != tenant:
            raise FamilyRolloutReadinessDenied(
                "Original legacy and tenant accounts are not isolated")
        preflight._verify_database(
            legacy, preflight.LEGACY_TABLES,
            frozenset(("tenant_users", "tenant_identities")))
        value = env.get("EDGE_CREDENTIAL_KEY", "")
        if not isinstance(value, str) or not value:
            raise FamilyRolloutReadinessDenied(
                "Original encrypted Public credential key is unavailable")
        try:
            vault = Fernet(value.encode("ascii"))
        except (ValueError, TypeError, UnicodeError):
            raise FamilyRolloutReadinessDenied(
                "Original encrypted Public credential key is invalid") from None
        # Reuse the v0.2.74 *read-only* inspection of the already saved owner:
        # exactly one enrolled identity, one or more verified Public links, and
        # decryptable encrypted Public secrets. It never returns identifiers.
        existing = linked._inventory(tenant, vault)
        if existing["owner"] != 1 or existing["links"] < 1:
            raise FamilyRolloutReadinessDenied(
                "Owner's verified independent Public link is required")
        moment = int(time.time()) if now is None else now
        if type(moment) is not int or not 0 <= moment <= 253402300799:
            raise FamilyRolloutReadinessDenied(
                "Read-only invitation inspection time is invalid")
        with closing(sqlite3.connect(
                tenant.as_uri() + "?mode=ro", uri=True, timeout=15)) as db:
            db.execute("PRAGMA query_only=ON")
            tables = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            pending = 0
            if "tenant_signup_invites" in tables:
                pending = db.execute("""SELECT COUNT(*)
                    FROM tenant_signup_invites
                    WHERE consumed_at IS NULL AND expires_at>?""",
                    (moment,)).fetchone()[0]
            if pending:
                raise FamilyRolloutReadinessDenied(
                    "Active pending invitations must be resolved before rollout")
        return {
            "inspection": "passed",
            "original_legacy_login_preserved": True,
            "independent_owner_initialized": True,
            "existing_tenant_members": 0,
            "active_owner_public_connections": existing["connections"],
            "verified_owner_public_links": existing["links"],
            "active_identity_sessions": existing["sessions"],
            "enrollment_currently_disabled": True,
            "external_backup_custody_independently_proven": False,
            "second_physical_device_verified": False,
            "second_independent_public_account_verified": False,
            "member_registration_authorized": False,
            "live_trading_enabled": False,
            "autonomous_orders_enabled": False,
            "bank_transfers_enabled": False,
        }
    except FamilyRolloutReadinessDenied:
        raise
    except (ValueError, OSError, TypeError, sqlite3.Error,
            storage.SharedStorageDenied, preflight.CutoverPreflightDenied,
            linked.LinkedOwnerBackupDenied):
        raise FamilyRolloutReadinessDenied(
            "Private family invitation inspection denied safely") from None
