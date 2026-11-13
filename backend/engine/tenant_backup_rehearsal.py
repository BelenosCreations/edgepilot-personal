"""Offline encrypted backup/restore rehearsal for SYNTHETIC tenant fixtures only.

IMPORTANT: Not a production backup product. Both source and restored plaintext
must be regular files under verified Linux /dev/shm tmpfs; never pass Render's
production database. No HTTP route, real API key, transfer, scanner, or worker
imports this module. The sealed in-memory archive uses a separate caller-held
Fernet key, not EdgePilot's Public credential encryption key.

Restore destroys saved login sessions, pending WebAuthn challenges,
unredeemed invitations and worker leases. It also quarantines ALL Public
connections, linked accounts and registered passkeys: an older backup must never resurrect a key
that was revoked after the snapshot. No real provider reconnect is possible.
"""
from __future__ import annotations

from contextlib import closing, ExitStack
from dataclasses import astuple
from datetime import datetime, timezone
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import stat
import time
import tempfile
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken

from . import shadow_storage, tenant_paper_authenticated_preflight, tenant_paper_recovery_audit

_MAGIC = b"EDGEPILOT-SYNTHETIC-TENANT-BACKUP-v1\n"
_PAPER_MAGIC = b"EDGEPILOT-PINNED-SYNTHETIC-PAPER-BACKUP-v1\n"
_MAX_DB_SIZE = 16 * 1024 * 1024
_REQUIRED_TABLES = frozenset({
    "tenant_schema_meta", "tenant_users", "tenant_connections",
    "tenant_accounts", "tenant_account_settings", "tenant_identities",
    "tenant_identity_sessions", "tenant_worker_leases",
    "tenant_runtime_status",
})
_SIDECARS = ("-journal", "-wal", "-shm")
_STAGE_PREFIX = ".edgepilot-synthetic-restore-"
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


def _check_contents(db, *, require_quiescent, policies=None):
    try:
        tables = {
            r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if not _REQUIRED_TABLES.issubset(tables):
            raise OfflineBackupDenied("Synthetic tenant schema not supported")
        # Verify dormant paper-wallet cash, event replay and per-account
        # positions before sealing OR accepting a recovered fixture.
        try:
            provider = None
            if policies is not None:
                markers = db.execute("SELECT label FROM offline_paper_preflight").fetchall()
                trigger = db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='trigger' LIMIT 1").fetchone()
                if (markers != [(tenant_paper_authenticated_preflight._MARKER,)]
                        or trigger is not None):
                    raise OfflineBackupDenied("Marked synthetic paper fixture required")
                scopes = _paper_scope(db)
                if (len(scopes) != db.execute("SELECT COUNT(*) FROM tenant_accounts").fetchone()[0]
                        or not policies.keys() <= {(user, account) for user, account, *_ in scopes}):
                    raise OfflineBackupDenied("Synthetic paper scope unavailable")
                provider = tenant_paper_authenticated_preflight.SYNTHETIC_PROVIDER
            tenant_paper_recovery_audit.audit_tenant_paper_ledger(
                db, policies=policies, required_provider=provider)
        except tenant_paper_recovery_audit.PaperRecoveryDenied:
            raise OfflineBackupDenied("Synthetic paper ledger verification failed") from None
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


def _paper_policies(policies):
    if type(policies) is not dict or not policies:
        raise OfflineBackupDenied("Synthetic paper policies unavailable")
    checked = policies.copy()
    for scope, policy in checked.items():
        if (type(scope) is not tuple or len(scope) != 2
                or not all(tenant_paper_recovery_audit._canonical_uuid(value) for value in scope)
                or type(policy) is not tenant_paper_recovery_audit.PaperRestorePolicy):
            raise OfflineBackupDenied("Synthetic paper policies unavailable")
    return checked


def _paper_pin(token, policies):
    if type(token) is not bytes or not 0 < len(token) <= 2 * _MAX_DB_SIZE + 8192:
        raise OfflineBackupDenied("Pinned synthetic archive unavailable")
    policy_data = [[*scope, *astuple(policy)] for scope, policy in sorted(policies.items())]
    return hashlib.sha256(_PAPER_MAGIC + json.dumps(
        policy_data, separators=(",", ":")).encode("ascii") + token).hexdigest()


def seal_pinned_paper_fixture(source_path, archive_key, *, policies):
    """Seal a marked fixture and return its exact pin for independent custody."""
    checked = _paper_policies(policies)
    token = _seal(source_path, archive_key, magic=_PAPER_MAGIC, policies=checked)
    return token, _paper_pin(token, checked)


def _require_paper_pin(token, policies, trusted_pin):
    checked = _paper_policies(policies)
    if (type(trusted_pin) is not str or not trusted_pin.isascii()
            or not hmac.compare_digest(trusted_pin, _paper_pin(token, checked))):
        raise OfflineBackupDenied("Pinned synthetic archive unavailable")
    return checked


def restore_pinned_paper_fixture(token, archive_key, destination_path, *, policies, trusted_pin):
    """Restore the externally pinned archive with its original synthetic policies."""
    checked = _require_paper_pin(token, policies, trusted_pin)
    return _restore(token, archive_key, destination_path, magic=_PAPER_MAGIC, policies=checked)


def sealed_snapshot(source_path, archive_key):
    """Return Fernet-authenticated bytes; never create disk plaintext copies.

    A consistent SQLite backup is first made to an ephemeral tmpfs file;
    encryption is performed in process memory and the temp directory removed.
    The snapshot is invalidated when source uses WAL or leaves /dev/shm.
    """
    return _seal(source_path, archive_key, magic=_MAGIC, policies=None)


def _seal(source_path, archive_key, *, magic, policies):
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
                check.execute("PRAGMA trusted_schema=OFF")
                _check_contents(check, require_quiescent=True, policies=policies)
            raw = backup_path.read_bytes()
            if not raw.startswith(b"SQLite format 3\x00") or len(raw) > _MAX_DB_SIZE:
                raise OfflineBackupDenied("Synthetic database format unavailable")
            return cipher.encrypt(magic + raw)
    except OfflineBackupDenied:
        raise
    except (sqlite3.Error, OSError, shadow_storage.MemoryStorageError):
        raise OfflineBackupDenied("Synthetic backup rehearsal unavailable") from None


def _paper_scope(db):
    return db.execute("""SELECT a.user_id,a.account_id,a.connection_id,
        a.provider_account_ref,u.disabled_at,a.disabled_at,c.revoked_at
        FROM tenant_accounts a JOIN tenant_users u ON u.user_id=a.user_id
        JOIN tenant_connections c ON c.connection_id=a.connection_id AND c.user_id=a.user_id
        ORDER BY a.user_id,a.account_id""").fetchall()


def _paper_data_digest(db):
    digest = hashlib.sha256()
    for table in sorted(tenant_paper_recovery_audit.PAPER_TABLES):
        digest.update(table.encode("ascii") + b"\n")
        for row in db.execute("SELECT * FROM " + table + " ORDER BY rowid"):
            digest.update(json.dumps(row, separators=(",", ":")).encode("ascii") + b"\n")
    return digest.digest()


def restore_sealed_fixture(token, archive_key, destination_path):
    """Validate, quarantine, then atomically publish a NEW tmpfs fixture.

    Synthetic only. An unverified database is never visible at the requested
    destination, not even briefly. Stage privately under the same verified
    tmpfs directory; publish with a no-replace hard link only AFTER all
    integrity checks, revocation and rollback-sensitive cleanup have committed.
    Neither an existing destination nor its contents may be removed on error.
    """
    return _restore(token, archive_key, destination_path, magic=_MAGIC, policies=None)


def _decrypt(token, archive_key, magic):
    cipher = _archive_cipher(archive_key)
    if not isinstance(token, bytes) or len(token) > 2 * _MAX_DB_SIZE + 8192:
        raise OfflineBackupDenied("Synthetic archive input unavailable")
    try:
        payload = cipher.decrypt(token)
    except (InvalidToken, ValueError):
        raise OfflineBackupDenied("Synthetic archive verification failed") from None
    if (not payload.startswith(magic) or
            not payload[len(magic):].startswith(b"SQLite format 3\x00") or
            len(payload) - len(magic) > _MAX_DB_SIZE):
        raise OfflineBackupDenied("Synthetic archive format unavailable")
    return payload[len(magic):]


def _publication_info(path):
    source, _ = shadow_storage.require_isolated_source(path)
    info = path.lstat()
    if (source != path or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink not in (1, 2)
            or any(os.path.lexists(str(path) + suffix) for suffix in _SIDECARS)):
        raise OfflineBackupDenied("Synthetic restore candidate unavailable")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_nlink)


def _audit_publication(candidate, raw, policies):
    with closing(sqlite3.connect(":memory:")) as archived:
        archived.deserialize(raw)
        archived.execute("PRAGMA trusted_schema=OFF")
        _check_contents(archived, require_quiescent=True, policies=policies)
        candidate.execute("PRAGMA trusted_schema=OFF")
        tables = _check_contents(candidate, require_quiescent=True, policies=policies)
        schema = "SELECT name,type,tbl_name,sql FROM sqlite_master ORDER BY name"
        if (archived.execute(schema).fetchall() != candidate.execute(schema).fetchall()
                or _paper_data_digest(archived) != _paper_data_digest(candidate)
                or not _quarantine_preserved(archived, candidate)
                or any(candidate.execute("SELECT 1 FROM " + name + " LIMIT 1").fetchone()
                       for name in _INVALIDATE_RESTORED if name in tables)
                or ("tenant_passkey_credentials" in tables and candidate.execute(
                    "SELECT 1 FROM tenant_passkey_credentials WHERE revoked_at IS NULL LIMIT 1"
                ).fetchone())):
            raise OfflineBackupDenied("Synthetic restore candidate differs from archive")


def inspect_pinned_paper_publication(token, archive_key, destination_path, *, policies, trusted_pin):
    """Audit a candidate after interrupted publication without changing any file."""
    checked = _require_paper_pin(token, policies, trusted_pin)
    raw = _decrypt(token, archive_key, _PAPER_MAGIC)
    try:
        target = Path(destination_path)
        info = _publication_info(target)
        uri = "file:" + quote(str(target), safe="/") + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as candidate:
            candidate.execute("BEGIN")
            _audit_publication(candidate, raw, checked)
            if _publication_info(target) != info:
                raise OfflineBackupDenied("Synthetic restore candidate changed during inspection")
        return {"quarantineVerified": True, "additionalLinkPresent": info[-1] == 2}
    except (OSError, sqlite3.Error, ValueError, shadow_storage.MemoryStorageError):
        raise OfflineBackupDenied("Synthetic restore candidate unavailable") from None


def cleanup_pinned_paper_staging_link(token, archive_key, destination_path, staging_path, *,
                                    policies, trusted_pin):
    """Explicitly remove one reviewed orphan staging name from a private fixture."""
    checked = _require_paper_pin(token, policies, trusted_pin)
    raw = _decrypt(token, archive_key, _PAPER_MAGIC)
    try:
        target, stage = Path(destination_path), Path(staging_path)
        if (stage == target or stage.parent != target.parent
                or not stage.name.startswith(_STAGE_PREFIX) or stage.suffix != ".db"):
            raise OfflineBackupDenied("Synthetic restore staging link unavailable")
        with ExitStack() as handles:
            parent_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            handles.callback(os.close, parent_fd)
            parent = os.fstat(parent_fd)
            if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
                raise OfflineBackupDenied("Private synthetic restore directory required")
            info = _publication_info(target)
            if info[-1] != 2 or _publication_info(stage) != info:
                raise OfflineBackupDenied("Synthetic restore staging link unavailable")
            stage_fd = os.open(stage.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
            handles.callback(os.close, stage_fd)
            held = os.fstat(stage_fd)
            if (held.st_dev, held.st_ino) != info[:2]:
                raise OfflineBackupDenied("Synthetic restore staging link changed")
            fcntl.flock(stage_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # SQLite header read/write versions must both indicate rollback mode.
            # Opening a detached WAL database read/write can create sidecars.
            if os.pread(stage_fd, 2, 18) != b"\x01\x01":
                raise OfflineBackupDenied("Synthetic restore journaling unavailable")
            uri = "file:" + quote(str(target), safe="/") + "?mode=rw"
            candidate = handles.enter_context(closing(sqlite3.connect(uri, uri=True, timeout=0)))
            candidate.execute("BEGIN EXCLUSIVE")
            candidate.execute("PRAGMA query_only=ON")
            if candidate.execute("PRAGMA journal_mode").fetchone() != ("delete",):
                raise OfflineBackupDenied("Synthetic restore journaling unavailable")
            _audit_publication(candidate, raw, checked)
            if (_publication_info(target) != info or _publication_info(stage) != info
                    or not os.path.samestat(parent, target.parent.stat())
                    or not os.path.samestat(held, os.stat(stage.name, dir_fd=parent_fd,
                                                          follow_symlinks=False))):
                raise OfflineBackupDenied("Synthetic restore staging link changed")
            os.unlink(stage.name, dir_fd=parent_fd)
    except (OSError, sqlite3.Error, ValueError, shadow_storage.MemoryStorageError):
        raise OfflineBackupDenied("Synthetic restore staging link unavailable") from None


def _quarantine_preserved(archived, candidate):
    original, restored = _paper_scope(archived), _paper_scope(candidate)
    if len(original) != len(restored):
        return False
    for before, after in zip(original, restored):
        if before[:-2] != after[:-2]:
            return False
        for prior, current in zip(before[-2:], after[-2:]):
            if prior is not None:
                if prior != current:
                    return False
            else:
                tenant_paper_recovery_audit._event_time(current)
    return True


def _restore(token, archive_key, destination_path, *, magic, policies):
    raw = _decrypt(token, archive_key, magic)
    try:
        root = shadow_storage.memory_root()
        target = Path(destination_path)
        parent = target.parent.resolve(strict=True)
        if parent != root and root not in parent.parents:
            raise OfflineBackupDenied("Synthetic restore destination unavailable")
        if target.exists() or target.is_symlink() or target.name in ("", ".", ".."):
            raise OfflineBackupDenied("Synthetic restore destination unavailable")
    except OfflineBackupDenied:
        raise
    except (OSError, ValueError, shadow_storage.MemoryStorageError):
        raise OfflineBackupDenied("Synthetic restore destination unavailable") from None

    if policies is not None and any(os.path.lexists(str(target) + suffix) for suffix in _SIDECARS):
        raise OfflineBackupDenied("Synthetic restore destination unavailable")
    stage = None
    fd = None
    try:
        # mkstemp creates a private 0600 regular file using O_EXCL. Do not
        # create the caller's destination until the synthetic archive has
        # passed all audits and revoked its restored credentials and sessions.
        fd, name = tempfile.mkstemp(prefix=_STAGE_PREFIX, suffix=".db", dir=str(parent))
        stage = Path(name)
        fcntl.flock(fd, fcntl.LOCK_EX)
        with os.fdopen(fd, "wb", closefd=False) as writer:
            writer.write(raw)
            writer.flush()
            os.fsync(writer.fileno())
        shadow_storage.require_isolated_source(stage)
        with closing(sqlite3.connect(str(stage), timeout=10)) as restored:
            restored.execute("PRAGMA foreign_keys=ON")
            restored.execute("PRAGMA trusted_schema=OFF")
            restored.execute("BEGIN IMMEDIATE")
            tables = _check_contents(restored, require_quiescent=False, policies=policies)
            if policies is not None:
                prior_scope = _paper_scope(restored)
                prior_digest = _paper_data_digest(restored)
            for name in _INVALIDATE_RESTORED:
                if name in tables:
                    restored.execute("DELETE FROM " + name)
            quarantined_at = datetime.now(timezone.utc).isoformat()
            restored.execute("""UPDATE tenant_accounts
                SET disabled_at=COALESCE(disabled_at,?)""", (quarantined_at,))
            restored.execute("""UPDATE tenant_connections
                SET revoked_at=COALESCE(revoked_at,?)""", (quarantined_at,))
            if "tenant_passkey_credentials" in tables:
                restored.execute("""UPDATE tenant_passkey_credentials
                    SET revoked_at=COALESCE(revoked_at,?)""", (int(time.time()),))
            _check_contents(restored, require_quiescent=True, policies=policies)
            if policies is not None:
                expected = [(*scope, disabled if disabled is not None else quarantined_at,
                             revoked if revoked is not None else quarantined_at)
                            for *scope, disabled, revoked in prior_scope]
                if (expected != _paper_scope(restored)
                        or prior_digest != _paper_data_digest(restored)):
                    raise OfflineBackupDenied("Synthetic paper scope changed during quarantine")
            restored.commit()
        # The staged file is complete before publication; a failed fsync
        # cannot leave a partial database at the caller's final path.
        with stage.open("rb") as checked:
            os.fsync(checked.fileno())
        # Atomic link is no-replace, including if the target appeared during
        # validation. Never use os.replace or unlink an existing destination.
        if policies is not None and any(os.path.lexists(str(target) + suffix) for suffix in _SIDECARS):
            raise OfflineBackupDenied("Synthetic restore destination unavailable")
        os.link(stage, target)
        return target
    except Exception:
        raise OfflineBackupDenied("Synthetic restore verification failed") from None
    finally:
        # Success removes the staging name; failure removes only our staging
        # name and SQLite sidecars, never an unrelated destination path.
        if stage is not None:
            for suffix in ("", *_SIDECARS):
                try:
                    Path(str(stage) + suffix).unlink(missing_ok=True)
                except OSError:
                    pass
        if fd is not None:
            os.close(fd)
