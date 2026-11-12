"""Default-off, offline first-owner Argon2id password proof without login.

A successful result does NOT prove an HTTPS session, Android device,
passkey, Public API owner binding, or authorize live tenant routing.
Never logs, prints, returns or stores the entered password or hash.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path

from argon2 import exceptions as argon_errors

from . import identity_auth
from . import permanent_owner_readiness
from . import shared_storage_cutover as storage


class OwnerPasswordProofDenied(RuntimeError):
    """Fixed nonsecret refusal code only."""


def prove_first_owner_password(env, legacy_path, tenant_path, supplied_password,
                               *, persistent_root=None):
    if (not isinstance(env, dict)
            or str(env.get("EDGE_OWNER_PASSWORD_PROOF_ALLOWED", "")) != "true"
            or storage._flag(env, "EDGE_IDENTITY_AUTH_ENABLED")):
        raise OwnerPasswordProofDenied("Operator-only password proof requires inactive identity endpoints")
    try:
        if (not isinstance(supplied_password, str)
                or not 14 <= len(supplied_password) <= 128
                or any(c in supplied_password for c in "\x00\r\n")):
            raise OwnerPasswordProofDenied("Password was not verified")
        check_env = dict(env)
        check_env["EDGE_OWNER_READINESS_AUDIT_ALLOWED"] = "true"
        ready = permanent_owner_readiness.inspect_owner_readiness(
            check_env, legacy_path, tenant_path, persistent_root=persistent_root)
        if (not ready["tenant_owner_initialized"]
                or not ready["tenant_owner_has_password_identity"]
                or ready["tenant_member_count"] != 1):
            raise OwnerPasswordProofDenied("One prepared owner identity required")
        tenant = Path(tenant_path)
        with closing(sqlite3.connect(tenant.as_uri() + "?mode=ro",
                                     uri=True, timeout=10)) as db:
            db.execute("PRAGMA query_only=ON")
            record = db.execute("""SELECT i.password_hash
                FROM tenant_identities i JOIN tenant_users u ON u.user_id=i.user_id
                WHERE u.role='owner' AND u.disabled_at IS NULL""").fetchone()
            if not record or not record[0].startswith("$argon2id$"):
                raise OwnerPasswordProofDenied("Owner Argon2id identity is unavailable")
            try:
                verified = bool(identity_auth._HASHER.verify(record[0], supplied_password))
            except (argon_errors.VerifyMismatchError,
                    argon_errors.VerificationError,
                    argon_errors.InvalidHashError):
                verified = False
        return {
            "first_owner_password_verified": verified,
            "independent_http_login_verified": False,
            "identity_sessions_created": False,
            "owner_public_connection_verified": False,
            "original_login_preserved": True,
            "authorized_to_activate": False,
            "live_trading_enabled": False,
            "bank_transfers_enabled": False,
        }
    except OwnerPasswordProofDenied:
        raise
    except (ValueError, OSError, sqlite3.Error,
            storage.SharedStorageDenied,
            permanent_owner_readiness.OwnerReadinessDenied):
        raise OwnerPasswordProofDenied("Independent owner password proof denied safely") from None
