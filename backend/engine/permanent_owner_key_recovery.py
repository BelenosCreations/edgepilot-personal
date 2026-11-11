"""Console-only read-only check that an independently saved owner Fernet key works.

Neither Flask nor Render startup invokes this; no network, brokerage read,
trade, token disclosure, credential copy, or database mutation.
"""
from __future__ import annotations

import hmac
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from . import permanent_cutover_preflight as preflight
from . import shared_storage_cutover as storage


class OwnerKeyRecoveryDenied(RuntimeError):
    """Sanitized refusal; never echo secret, ciphertext or owner identity."""


APPROVAL = "VERIFY OWNER VAULT RECOVERY"
DORMANT_FLAGS = (
    "EDGE_ISOLATED_STAGING",
    "EDGE_AUTOMATION_WORKER_ENABLED",
    "ENABLE_LIVE_ORDERS",
    "EDGE_PERMANENT_TENANTS_ONLY",
    "EDGE_PERMANENT_READONLY_PILOT_ENABLED",
    "EDGE_TENANT_SIGNUP_ENABLED",
    "EDGE_TENANT_PUBLIC_VAULT_ENABLED",
    "EDGE_TENANT_PUBLIC_READONLY_ENABLED",
    "EDGE_TENANT_ACCOUNT_READS_ENABLED",
)


def verify_private_owner_key(env, legacy_path, *, recovery_key, approval,
                             persistent_root=None):
    """Verify entered key and saved owner ciphertext without disclosing data.

    Operator must supply recovery_key independently from secure offsite custody.
    Matching an active environment key is NOT proof of offsite recoverability.
    """
    if (approval != APPROVAL
            or str(env.get("EDGE_OWNER_VAULT_RECOVERY_AUDIT_ALLOWED", "")) != "true"):
        raise OwnerKeyRecoveryDenied("Read-only owner key inspection not approved")
    try:
        if any(storage._flag(env, key) for key in DORMANT_FLAGS):
            raise OwnerKeyRecoveryDenied("Owner credential inspection requires dormant access")
        root = storage.PERSISTENT_ROOT if persistent_root is None else Path(persistent_root)
        source = Path(legacy_path)
        if (source != root / storage.LEGACY_FILENAME
                or not root.is_absolute() or root.is_symlink()
                or not preflight._private_regular_file(source)
                or source.lstat().st_uid != os.geteuid()):
            raise OwnerKeyRecoveryDenied("Private owner database required")
        preflight._verify_database(source, preflight.LEGACY_TABLES,
                                   frozenset(("tenant_users",)))
        active_key = env.get("EDGE_CREDENTIAL_KEY", "")
        if (not isinstance(active_key, str) or not active_key
                or not isinstance(recovery_key, str) or not recovery_key):
            raise OwnerKeyRecoveryDenied("Independent credential key material unavailable")
        cipher = Fernet(recovery_key.encode("ascii"))
        Fernet(active_key.encode("ascii"))
        if not hmac.compare_digest(active_key.encode(), recovery_key.encode()):
            raise OwnerKeyRecoveryDenied("Independent recovery key does not match current vault")

        with closing(sqlite3.connect(source.as_uri() + "?mode=ro",
                                     uri=True, timeout=10)) as db:
            db.execute("PRAGMA query_only=ON")
            row = db.execute("""SELECT ciphertext FROM broker_credentials
                WHERE provider='public'""").fetchone()
        saved = row is not None and row[0] is not None
        unlocked = False
        if saved:
            ciphertext = row[0]
            if not isinstance(ciphertext, bytes) or not 32 <= len(ciphertext) <= 8192:
                raise OwnerKeyRecoveryDenied("Encrypted credential record invalid")
            plaintext = cipher.decrypt(ciphertext)
            try:
                recovered = plaintext.decode("utf-8")
                if (not 20 <= len(recovered) <= 2048
                        or any(c in recovered for c in "\r\n\x00")):
                    raise OwnerKeyRecoveryDenied("Saved credential failed format verification")
                unlocked = True
            finally:
                del plaintext
        return {
            "inspection": "passed",
            "entered_key_matches_running_server_key": True,
            "encrypted_public_credential_present": saved,
            "saved_credential_decryption_verified": unlocked,
            "independent_offsite_custody_verified": False,
            "authorized_to_activate": False,
            "live_trading_enabled": False,
            "bank_transfers_enabled": False,
        }
    except OwnerKeyRecoveryDenied:
        raise
    except (OSError, ValueError, TypeError, UnicodeError, sqlite3.Error,
            InvalidToken, preflight.CutoverPreflightDenied,
            storage.SharedStorageDenied):
        raise OwnerKeyRecoveryDenied("Owner credential inspection failed safely") from None
