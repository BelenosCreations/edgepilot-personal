"""Offline authenticated encrypted snapshot of one owner with a verified Public link.

This is a STRICTLY OPERATOR-ONLY recovery/export utility. It is never
imported by the web app and never writes live tenant or legacy SQLite files.

Unlike the v0.2.70 first-owner backup, this accepts active identity
sessions in production but removes them from the *temporary snapshot*.
A restored archive cannot revive a logged-in browser session.
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

from . import permanent_cutover_preflight as preflight
from . import permanent_tenant_owner_backup as first_owner
from . import shared_storage_cutover as storage

MAGIC = b"EDGEPILOT-TENANT-LINKED-BK1\x00"
MAX_BYTES = 16 * 1024 * 1024
APPROVAL = "BACK UP LINKED EDGEPILOT ACCOUNT"
NEEDED_TRUE = (
    "EDGE_TENANT_LINKED_BACKUP_ALLOWED",
    "EDGE_SHARED_TENANT_DB_PREPARE",
    "EDGE_TENANT_SCHEMA_PREPARE",
    "EDGE_IDENTITY_AUTH_ENABLED",
    "EDGE_PERMANENT_READONLY_PILOT_ENABLED",
    "EDGE_TENANT_ACCOUNT_READS_ENABLED",
    "EDGE_TENANT_PUBLIC_VAULT_ENABLED",
    "EDGE_TENANT_PUBLIC_READONLY_ENABLED",
    "EDGE_TENANT_PUBLIC_DISCOVERY_ONLY",
)
NEEDED_FALSE = (
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


class LinkedOwnerBackupDenied(RuntimeError):
    """Sanitized, static failure messages without secret or account data."""


def _inventory(path, fernet):
    """Verify exactly one owner and linked credentials, without returning IDs."""
    members = preflight._verify_database(
        path, preflight.TENANT_TABLES,
        frozenset(("settings", "broker_credentials", "orders", "activity")))
    if members != 1:
        raise LinkedOwnerBackupDenied("First linked owner identity is not isolated")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True,
                                 timeout=15)) as db:
        db.execute("PRAGMA query_only=ON")
        user = db.execute("""SELECT u.user_id FROM tenant_users u
            JOIN tenant_identities i ON i.user_id=u.user_id
            WHERE u.role='owner' AND u.disabled_at IS NULL
              AND i.password_hash LIKE '$argon2id$%'""").fetchall()
        if len(user) != 1:
            raise LinkedOwnerBackupDenied("Enrolled owner is not available")
        owner_id = user[0][0]
        identities = db.execute(
            "SELECT COUNT(*) FROM tenant_identities").fetchone()[0]
        if identities != 1:
            raise LinkedOwnerBackupDenied("Only one identity is supported at this stage")
        connections = db.execute("""SELECT credential_ciphertext
            FROM tenant_connections
            WHERE user_id=? AND provider='public' AND revoked_at IS NULL""",
            (owner_id,)).fetchall()
        links = db.execute("""SELECT COUNT(*) FROM tenant_accounts a
            JOIN tenant_connections c ON c.connection_id=a.connection_id
                AND c.user_id=a.user_id
            WHERE a.user_id=? AND a.provider='public'
              AND a.disabled_at IS NULL AND c.revoked_at IS NULL
              AND c.provider='public'""", (owner_id,)).fetchone()[0]
        sessions = db.execute(
            "SELECT COUNT(*) FROM tenant_identity_sessions").fetchone()[0]
        if not connections or links < 1:
            raise LinkedOwnerBackupDenied("Owner does not have a verified active Public link")
        # Check that the same pre-existing Render Fernet key can decrypt
        # every active ciphertext. Never return or log the secret.
        for (ciphertext,) in connections:
            if not isinstance(ciphertext, bytes) or len(ciphertext) < 80:
                raise LinkedOwnerBackupDenied("Saved Public key is not encrypted")
            try:
                secret = fernet.decrypt(ciphertext)
                if not 20 <= len(secret) <= 2048:
                    raise ValueError()
            except (InvalidToken, ValueError, TypeError):
                raise LinkedOwnerBackupDenied(
                    "Saved Public key cannot be recovered with current vault key") from None
            finally:
                secret = None
    return {"owner": 1, "connections": len(connections),
            "links": links, "sessions": sessions}


def _verify_blob(blob, key, fernet, *, ram, expected_digest=None):
    if (not blob.startswith(MAGIC)
            or not len(MAGIC) + 12 + 16 + 512 <= len(blob) <=
                MAX_BYTES + len(MAGIC) + 12 + 16):
        raise LinkedOwnerBackupDenied("Encrypted linked owner archive invalid")
    nonce = blob[len(MAGIC):len(MAGIC)+12]
    try:
        raw = AESGCM(key).decrypt(nonce, blob[len(MAGIC)+12:], MAGIC)
    except (InvalidTag, ValueError):
        raise LinkedOwnerBackupDenied("Linked owner archive authentication failed") from None
    digest = hashlib.sha256(raw).hexdigest()
    if expected_digest is not None and digest != expected_digest:
        raise LinkedOwnerBackupDenied("Restored linked owner snapshot digest differs")
    with tempfile.TemporaryDirectory(prefix="edgepilot-linked-restore-", dir=ram) as tmp:
        restored = Path(tmp) / "restored.sqlite3"
        fd = os.open(restored, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as writer:
            writer.write(raw)
            writer.flush()
            os.fsync(writer.fileno())
        result = _inventory(restored, fernet)
        if result["sessions"] != 0:
            raise LinkedOwnerBackupDenied("Restored snapshot must have no active sessions")
    return digest


def create_linked_owner_backup(env, legacy_path, tenant_path, archive_path,
                               *, key_b64, approval, persistent_root=None,
                               temp_root=None):
    """Snapshot live tenant DB read-only, strip sessions only from RAM copy.

    Return only aggregate counts/cryptographic digests. The temporary
    /dev/shm archive is NOT an off-service backup until copied out.
    """
    if approval != APPROVAL:
        raise LinkedOwnerBackupDenied("Explicit nonsecret operator approval required")
    if (not isinstance(env, dict)
            or any(env.get(flag) != "true" for flag in NEEDED_TRUE)
            or any(storage._flag(env, flag) for flag in NEEDED_FALSE)):
        raise LinkedOwnerBackupDenied("Discovery-only safety gates are not satisfied")
    root = storage.PERSISTENT_ROOT if persistent_root is None else Path(persistent_root)
    ram = Path("/dev/shm") if temp_root is None else Path(temp_root)
    legacy, tenant, archive = map(
        Path, (legacy_path, tenant_path, archive_path))
    if (not root.is_absolute() or not root.is_dir() or root.is_symlink()
            or not ram.is_absolute() or not ram.is_dir() or ram.is_symlink()
            or legacy != root / storage.LEGACY_FILENAME
            or tenant != root / storage.TENANT_FILENAME
            or archive.parent != ram or archive.suffix != ".epbk"
            or archive.exists() or archive.is_symlink()
            or not first_owner._private(legacy)
            or not first_owner._private(tenant)
            or legacy.samefile(tenant)
            or env.get("EDGE_DB_PATH") != str(legacy)
            or env.get("EDGE_TENANT_DB_PATH") != str(tenant)):
        raise LinkedOwnerBackupDenied("Private paired paid-storage layout required")
    try:
        preflight._verify_database(legacy, preflight.LEGACY_TABLES,
                                   frozenset(("tenant_users",)))
        key = first_owner._key(key_b64)
        vaultkey = env.get("EDGE_CREDENTIAL_KEY", "")
        if not vaultkey:
            raise LinkedOwnerBackupDenied("Existing credential recovery key unavailable")
        try:
            fernet = Fernet(vaultkey.encode("ascii"))
        except (ValueError, TypeError, UnicodeError):
            raise LinkedOwnerBackupDenied("Existing credential recovery key invalid") from None
        before = _inventory(tenant, fernet)
        with tempfile.TemporaryDirectory(
                prefix="edgepilot-linked-snapshot-", dir=ram) as tmp:
            snapshot = Path(tmp) / "snapshot.sqlite3"
            with closing(sqlite3.connect(tenant.as_uri()+"?mode=ro",
                                         uri=True, timeout=30)) as source:
                source.execute("PRAGMA query_only=ON")
                with closing(sqlite3.connect(snapshot)) as target:
                    source.backup(target)
            os.chmod(snapshot, 0o600)
            with closing(sqlite3.connect(snapshot)) as db:
                db.execute("PRAGMA foreign_keys=ON")
                db.execute("DELETE FROM tenant_identity_sessions")
                db.execute("DELETE FROM tenant_auth_failures")
                db.commit()
            if snapshot.stat().st_size > MAX_BYTES:
                raise LinkedOwnerBackupDenied("Linked owner snapshot exceeds limit")
            after = _inventory(snapshot, fernet)
            # First linked-owner stage must not change ownership/linkage
            # between the live check and consistent snapshot.
            if (after["owner"] != before["owner"]
                    or after["connections"] != before["connections"]
                    or after["links"] != before["links"]
                    or after["sessions"] != 0):
                raise LinkedOwnerBackupDenied("Linked owner changed during snapshot")
            raw = snapshot.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            nonce = os.urandom(12)
            blob = MAGIC + nonce + AESGCM(key).encrypt(nonce, raw, MAGIC)
            del raw
        fd, staged_name = tempfile.mkstemp(
            prefix=".edgepilot-linked-archive-", dir=ram)
        staged = Path(staged_name)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as writer:
                fd = -1
                writer.write(blob)
                writer.flush()
                os.fsync(writer.fileno())
            os.link(staged, archive, follow_symlinks=False)
        finally:
            if fd != -1:
                os.close(fd)
            staged.unlink(missing_ok=True)
        verified = _verify_blob(archive.read_bytes(), key, fernet,
                                ram=ram, expected_digest=digest)
        if verified != digest:
            raise LinkedOwnerBackupDenied("Linked owner restore was not verified")
        return {
            "backup_verified": True,
            "isolated_restore_verified": True,
            "owner_count": 1,
            "active_encrypted_connections": after["connections"],
            "verified_linked_accounts": after["links"],
            "restored_login_sessions": 0,
            "credential_decryptable": True,
            "archive_private_0600": first_owner._private(archive),
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "off_service_copy_verified": False,
            "authorized_to_activate": False,
            "live_trading_enabled": False,
            "bank_transfers_enabled": False,
        }
    except LinkedOwnerBackupDenied:
        raise
    except (OSError, ValueError, TypeError, sqlite3.Error, InvalidTag,
            preflight.CutoverPreflightDenied, first_owner.OwnerArchiveDenied):
        raise LinkedOwnerBackupDenied("Linked owner backup refused safely") from None


def verify_linked_archive(archive_path, *, key_b64, credential_key, temp_root=None):
    """Reverify an existing archive in isolated RAM without changing /data."""
    ram = Path("/dev/shm") if temp_root is None else Path(temp_root)
    archive = Path(archive_path)
    if archive.parent != ram or not first_owner._private(archive):
        raise LinkedOwnerBackupDenied("Private linked owner archive required")
    try:
        fernet = Fernet(credential_key.encode("ascii") if isinstance(
            credential_key, str) else credential_key)
        return _verify_blob(archive.read_bytes(), first_owner._key(key_b64),
                            fernet, ram=ram)
    except LinkedOwnerBackupDenied:
        raise
    except (OSError, ValueError, sqlite3.Error, TypeError,
            first_owner.OwnerArchiveDenied):
        raise LinkedOwnerBackupDenied("Linked owner archive verification refused safely") from None
