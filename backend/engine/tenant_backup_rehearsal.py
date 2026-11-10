"""Offline encrypted backup/restore rehearsal for SYNTHETIC tenant fixtures only.

IMPORTANT: Not a production backup product. Both source and restored plaintext
must be regular files under verified Linux /dev/shm tmpfs; never pass Render's
production database. No HTTP route, real API key, transfer, scanner, or worker
imports this module. The sealed in-memory archive uses a separate caller-held
Fernet key, not EdgePilot's Public credential encryption key.

The restore intentionally destroys all saved login sessions, pending WebAuthn
challenges and unredeemed invitations: a copied old session must not become
valid merely because an older database was restored.
"""
from __future__ import annotations

from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile

from cryptography.fernet import Fernet, InvalidToken

from . import shadow_storage

_MAGIC = b"EDGEPILOT-SYNTHETIC-TENANT-BACKUP-v1\n"
_MAX_DB_SIZE = 16 * 1024 * 1024
_REQUIRED_TABLES = frozenset({
    "tenant_schema_meta", "tenant_users", "tenant_connections",
    "tenant_accounts", "tenant_account_settings", "tenant_identities",
    "tenant_identity_sessions", "tenant_worker_leases",
    "tenant_runtime_status",
})
_INVALIDATE_RESTORED = (
    "tenant_identity_sessions", "tenant_passkey_challenges",
    "tenant_signup_invites", "tenant_worker_leases",
)


class OfflineBackupDenied(RuntimeError):
    """Fixed diagnostic; never includes a file path, user, key or SQL row."""


def _archive_cipher(archive_key):
    if not isinstance(archive_key, bytes) or len(archive_key) != 44:
        raise OfflineBackupDenied("Offline archive encryption key unavailable")
    try:
        return Fernet(archive_key)
    except (ValueError, TypeError):
        raise OfflineBackupDenied("Offline archive encryption key unavailable") from None


def _check_contents(db, *, require_quiescent):
    try:
        tables = {
            r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if not _REQUIRED_TABLES.issubset(tables):
            raise OfflineBackupDenied("Synthetic tenant schema not supported")
        integrity = db.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise OfflineBackupDenied("Synthetic tenant integrity unavailable")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise OfflineBackupDenied("Synthetic tenant relationships invalid")
        # If the table has ever held an active runtime state, refuse even an
        # offline rehearsal. No archived worker may be accidentally restored.
        if db.execute("""SELECT 1 FROM tenant_runtime_status
            WHERE requested_mode!='observe' OR worker_enabled!=0
            OR paper_enabled!=0 OR live_enabled!=0 LIMIT 1""").fetchone():
            raise OfflineBackupDenied("Active tenant runtime is prohibited")
        if require_quiescent and db.execute(
            "SELECT 1 FROM tenant_worker_leases LIMIT 1"
        ).fetchone():
            raise OfflineBackupDenied("Running worker leases are prohibited")
    except sqlite3.Error:
        raise OfflineBackupDenied("Synthetic tenant validation unavailable") from None
    return tables


def sealed_snapshot(source_path, archive_key):
    """Return Fernet-authenticated bytes; never create disk plaintext copies.

    A consistent SQLite backup is first made to an ephemeral tmpfs file;
    encryption is performed in process memory and the temp directory removed.
    The snapshot is invalidated when source uses WAL or leaves /dev/shm.
    """
    cipher = _archive_cipher(archive_key)
    try:
        source, root = shadow_storage.require_isolated_source(source_path)
        if source.stat().st_size > _MAX_DB_SIZE:
            raise OfflineBackupDenied("Synthetic fixture is too large")
        with tempfile.TemporaryDirectory(prefix="edgepilot-synthetic-archive-",
                                         dir=str(root)) as ephemeral:
            backup_path = Path(ephemeral) / "snapshot.db"
            with closing(sqlite3.connect(str(source), timeout=10)) as original:
                original.execute("PRAGMA foreign_keys=ON")
                with closing(sqlite3.connect(str(backup_path), timeout=10)) as clone:
                    original.backup(clone)
            shadow_storage.require_isolated_source(backup_path)
            with closing(sqlite3.connect(str(backup_path), timeout=10)) as check:
                check.execute("PRAGMA foreign_keys=ON")
                _check_contents(check, require_quiescent=True)
            raw = backup_path.read_bytes()
            if not raw.startswith(b"SQLite format 3\x00") or len(raw) > _MAX_DB_SIZE:
                raise OfflineBackupDenied("Synthetic database format unavailable")
            return cipher.encrypt(_MAGIC + raw)
    except OfflineBackupDenied:
        raise
    except (sqlite3.Error, OSError, shadow_storage.MemoryStorageError):
        raise OfflineBackupDenied("Synthetic backup rehearsal unavailable") from None


def restore_sealed_fixture(token, archive_key, destination_path):
    """Restore to a NEW verified tmpfs path; never overwrite any existing DB.

    The destination is entirely removed on failure. Restored sessions,
    challenges, invitations and stale leases are purged in one transaction.
    The return value is the isolated file path, NOT an authenticated session.
    """
    cipher = _archive_cipher(archive_key)
    if not isinstance(token, bytes) or len(token) > 2 * _MAX_DB_SIZE + 8192:
        raise OfflineBackupDenied("Synthetic archive input unavailable")
    try:
        payload = cipher.decrypt(token)
    except (InvalidToken, ValueError):
        raise OfflineBackupDenied("Synthetic archive verification failed") from None
    if (not payload.startswith(_MAGIC) or
            not payload[len(_MAGIC):].startswith(b"SQLite format 3\x00") or
            len(payload) - len(_MAGIC) > _MAX_DB_SIZE):
        raise OfflineBackupDenied("Synthetic archive format unavailable")
    try:
        root = shadow_storage.memory_root()
        target = Path(destination_path)
        parent = target.parent.resolve(strict=True)
        if parent != root and root not in parent.parents:
            raise OfflineBackupDenied("Synthetic restore destination unavailable")
        if target.exists() or target.is_symlink() or target.name in ("", ".", ".."):
            raise OfflineBackupDenied("Synthetic restore destination unavailable")
        # O_NOFOLLOW and O_EXCL prevent symlink swaps and existing file
        # overwrite; mode 0600 keeps the test plaintext private.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os,"O_NOFOLLOW",0)
        fd = os.open(target, flags, 0o600)
    except OfflineBackupDenied:
        raise
    except (OSError, ValueError, shadow_storage.MemoryStorageError):
        raise OfflineBackupDenied("Synthetic restore destination unavailable") from None
    try:
        with os.fdopen(fd,"wb") as writer:
            writer.write(payload[len(_MAGIC):])
            writer.flush()
        shadow_storage.require_isolated_source(target)
        with closing(sqlite3.connect(str(target),timeout=10)) as restored:
            restored.execute("PRAGMA foreign_keys=ON")
            tables = _check_contents(restored,require_quiescent=False)
            restored.execute("BEGIN IMMEDIATE")
            for name in _INVALIDATE_RESTORED:
                if name in tables:
                    restored.execute("DELETE FROM "+name)
            _check_contents(restored,require_quiescent=True)
            restored.commit()
        return target
    except Exception:
        # Any failure leaves no unverified plaintext recovery source behind.
        for suffix in ("","-journal","-wal","-shm"):
            try:
                Path(str(target)+suffix).unlink(missing_ok=True)
            except OSError:
                pass
        raise OfflineBackupDenied("Synthetic restore verification failed") from None
