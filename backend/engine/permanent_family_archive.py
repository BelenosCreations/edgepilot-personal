"""Dormant encrypted snapshot/isolated restore rehearsal for 2-10 private users.

NEVER imported by the EdgePilot web application. No live database writes.
The existing v0.2.74 one-owner backup is intentionally left unchanged.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import family_recovery_readiness as readiness
from . import permanent_cutover_preflight as preflight
from . import permanent_tenant_owner_backup as old_backup
from . import shared_storage_cutover as storage

MAGIC = b"EDGEPILOT-TENANT-FAMILY-BK1\x00"
MAX_BYTES = 16 * 1024 * 1024
APPROVAL = "BACK UP PRIVATE FAMILY ACCOUNTS"
ARCHIVE_FLAG = "EDGE_FAMILY_ARCHIVE_ALLOWED"
CLEAR_TRANSIENT = (
    "tenant_identity_sessions",
    "tenant_auth_failures",
    "tenant_signup_attempts",
    "tenant_passkey_challenges",
)


class FamilyArchiveDenied(RuntimeError):
    """Only prewritten nonsecret refusal strings may reach a caller."""


def _snapshot_inventory(path, fernet, *, sessions_must_be_gone):
    """Audit a consistent temporary database without reporting any identity."""
    n = preflight._verify_database(
        path, preflight.TENANT_TABLES,
        frozenset(("settings", "broker_credentials", "orders", "activity")))
    if not 2 <= n <= readiness.MAX_PRIVATE_USERS:
        raise FamilyArchiveDenied("Private family snapshot requires two or more users")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro",
                                 uri=True, timeout=15)) as db:
        db.execute("PRAGMA query_only=ON")
        users = db.execute(
            "SELECT user_id, role, disabled_at FROM tenant_users").fetchall()
        identities = db.execute(
            "SELECT user_id, password_hash FROM tenant_identities").fetchall()
        if (len(users) != n or len(identities) != n or
                {u for u, _, _ in users} != {u for u, _ in identities} or
                sum(role == "owner" and disabled is None
                    for _, role, disabled in users) != 1 or
                sum(role == "owner" for _, role, _ in users) != 1 or
                any(not isinstance(pwd, str) or
                    not pwd.startswith("$argon2id$")
                    for _, pwd in identities)):
            raise FamilyArchiveDenied("Private family identities are not paired")
        active = {u for u, _, disabled in users if disabled is None}
        seen_digests = {}
        connections = db.execute(
            "SELECT user_id,credential_ciphertext FROM tenant_connections "
            "WHERE provider='public'").fetchall()
        for user, encrypted in connections:
            if not isinstance(encrypted, bytes):
                raise FamilyArchiveDenied("Family credential ciphertext is invalid")
            try:
                secret = fernet.decrypt(encrypted)
                if not 20 <= len(secret) <= 2048:
                    raise ValueError()
            except (InvalidToken, ValueError, TypeError):
                raise FamilyArchiveDenied(
                    "Stored family Public credential cannot be decrypted") from None
            digest = hashlib.sha256(secret).digest()
            secret = None
            prior = seen_digests.get(digest)
            if prior is not None and prior != user:
                raise FamilyArchiveDenied(
                    "A Public API secret cannot belong to two users")
            seen_digests[digest] = user
        links = db.execute("""SELECT a.user_id,a.disabled_at,c.revoked_at
            FROM tenant_accounts a JOIN tenant_connections c
              ON c.connection_id=a.connection_id AND c.user_id=a.user_id
            WHERE a.provider='public' AND c.provider='public'""").fetchall()
        if (len(links) != db.execute(
                "SELECT COUNT(*) FROM tenant_accounts").fetchone()[0] or
                any(disabled is None and revoked is not None
                    for _, disabled, revoked in links)):
            raise FamilyArchiveDenied("Family brokerage link isolation is invalid")
        linked = sum(u in active and disabled is None and revoked is None
                     for u, disabled, revoked in links)
        sessions = db.execute(
            "SELECT COUNT(*) FROM tenant_identity_sessions").fetchone()[0]
        pending = 0
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if sessions_must_be_gone:
            if sessions:
                raise FamilyArchiveDenied(
                    "Restored archive cannot contain login sessions")
            for name in CLEAR_TRANSIENT[1:]:
                if name in tables and db.execute(
                        "SELECT COUNT(*) FROM " + name).fetchone()[0]:
                    raise FamilyArchiveDenied(
                        "Restored archive contains temporary authentication state")
            if "tenant_signup_invites" in tables:
                pending = db.execute("""SELECT COUNT(*) FROM tenant_signup_invites
                    WHERE consumed_at IS NULL""").fetchone()[0]
                if pending:
                    raise FamilyArchiveDenied(
                        "Restored archive contains active invitations")
        return {"users": n, "connections": len(connections),
                "links": linked, "sessions": sessions}


def _decrypt_and_inspect(blob, key, fernet, ram, expected_digest=None):
    if (not isinstance(blob, bytes) or not blob.startswith(MAGIC)
            or not len(MAGIC) + 12 + 16 + 512 <= len(blob) <=
                MAX_BYTES + len(MAGIC) + 12 + 16):
        raise FamilyArchiveDenied("Encrypted family archive format is invalid")
    try:
        raw = AESGCM(key).decrypt(
            blob[len(MAGIC):len(MAGIC)+12],
            blob[len(MAGIC)+12:], MAGIC)
    except (InvalidTag, ValueError):
        raise FamilyArchiveDenied("Family archive authentication failed") from None
    digest = hashlib.sha256(raw).hexdigest()
    if expected_digest is not None and digest != expected_digest:
        raise FamilyArchiveDenied("Family archive snapshot digest mismatch")
    with tempfile.TemporaryDirectory(
            prefix="edgepilot-family-restore-", dir=ram) as tmp:
        restored = Path(tmp) / "restore.sqlite3"
        fd = os.open(restored, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        report = _snapshot_inventory(
            restored, fernet, sessions_must_be_gone=True)
    del raw
    return digest, report


def create_family_archive(env, legacy_path, tenant_path, output_path, *,
                          key_b64, approval, persistent_root=None,
                          temp_root=None):
    """Read-only source snapshot; strip bearer state only inside RAM copy."""
    if approval != APPROVAL or env.get(ARCHIVE_FLAG) != "true":
        raise FamilyArchiveDenied("Exact family archive approval required")
    root = (storage.PERSISTENT_ROOT if persistent_root is None
            else Path(persistent_root))
    ram = Path("/dev/shm") if temp_root is None else Path(temp_root)
    legacy, tenant, output = (
        Path(legacy_path), Path(tenant_path), Path(output_path))
    if (not ram.is_absolute() or not ram.is_dir() or ram.is_symlink()
            or output.parent != ram or output.suffix != ".epbk"
            or output.exists() or output.is_symlink()):
        raise FamilyArchiveDenied("Private RAM archive target is required")
    try:
        # Full policy, private-path, Fernet and identity ownership checks
        # are delegated to the v0.2.75 read-only family preflight.
        before = readiness.inspect_family_recovery(
            env, legacy, tenant, persistent_root=root)
        if (before["independent_identities"] < 2 or
                before["active_identities"] < 2):
            raise FamilyArchiveDenied(
                "Two active independent identities required for family archive")
        key = old_backup._key(key_b64)
        try:
            fernet = Fernet(env["EDGE_CREDENTIAL_KEY"].encode("ascii"))
        except (ValueError, TypeError, UnicodeError, KeyError):
            raise FamilyArchiveDenied("Original credential key unavailable") from None
        with tempfile.TemporaryDirectory(
                prefix="edgepilot-family-snapshot-", dir=ram) as tmp:
            snapshot = Path(tmp) / "snapshot.sqlite3"
            with closing(sqlite3.connect(
                    tenant.as_uri() + "?mode=ro", uri=True, timeout=30)) as src:
                src.execute("PRAGMA query_only=ON")
                with closing(sqlite3.connect(snapshot)) as dest:
                    src.backup(dest)
            os.chmod(snapshot, 0o600)
            with closing(sqlite3.connect(snapshot)) as db:
                db.execute("PRAGMA foreign_keys=ON")
                tables = {row[0] for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                for name in CLEAR_TRANSIENT:
                    if name in tables:
                        db.execute("DELETE FROM " + name)
                if "tenant_signup_invites" in tables:
                    db.execute("""DELETE FROM tenant_signup_invites
                        WHERE consumed_at IS NULL""")
                db.commit()
            if snapshot.stat().st_size > MAX_BYTES:
                raise FamilyArchiveDenied(
                    "Family database exceeds private recovery size limit")
            after = _snapshot_inventory(
                snapshot, fernet, sessions_must_be_gone=True)
            if (after["users"] != before["independent_identities"] or
                    after["connections"] != before["encrypted_public_connections"] or
                    after["links"] != before["active_linked_accounts"]):
                raise FamilyArchiveDenied(
                    "Member accounts changed during recovery snapshot")
            raw = snapshot.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            nonce = os.urandom(12)
            encrypted = MAGIC + nonce + AESGCM(key).encrypt(nonce, raw, MAGIC)
            del raw
        fd, filename = tempfile.mkstemp(
            prefix=".edgepilot-family-archive-", dir=ram)
        staging = Path(filename)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as out:
                fd = -1
                out.write(encrypted)
                out.flush()
                os.fsync(out.fileno())
            os.link(staging, output, follow_symlinks=False)
        finally:
            if fd != -1:
                os.close(fd)
            staging.unlink(missing_ok=True)
        checked, report = _decrypt_and_inspect(
            output.read_bytes(), key, fernet, ram, expected_digest=digest)
        if checked != digest or report != after:
            raise FamilyArchiveDenied("Restored family archive differs")
        return {
            "backup_verified": True,
            "isolated_restore_verified": True,
            "independent_users_restored": report["users"],
            "encrypted_connections_restored": report["connections"],
            "active_links_restored": report["links"],
            "restored_login_sessions": report["sessions"],
            "archive_private_0600": old_backup._private(output),
            "archive_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "off_service_copy_verified": False,
            "authorized_to_activate": False,
            "live_trading_enabled": False,
            "bank_transfers_enabled": False,
        }
    except FamilyArchiveDenied:
        raise
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error,
            readiness.FamilyRecoveryReadinessDenied,
            preflight.CutoverPreflightDenied, old_backup.OwnerArchiveDenied):
        raise FamilyArchiveDenied(
            "Private family archive was refused safely") from None


def verify_family_archive(path, *, key_b64, credential_key, temp_root=None):
    """Authenticate an existing encrypted RAM archive into isolated RAM only."""
    ram = Path("/dev/shm") if temp_root is None else Path(temp_root)
    target = Path(path)
    if target.parent != ram or not old_backup._private(target):
        raise FamilyArchiveDenied("Private family archive required")
    try:
        vault = Fernet(credential_key.encode("ascii") if isinstance(
            credential_key, str) else credential_key)
        return _decrypt_and_inspect(
            target.read_bytes(), old_backup._key(key_b64), vault, ram)
    except FamilyArchiveDenied:
        raise
    except (OSError, ValueError, TypeError, sqlite3.Error,
            old_backup.OwnerArchiveDenied, preflight.CutoverPreflightDenied):
        raise FamilyArchiveDenied(
            "Private family archive verification refused safely") from None
