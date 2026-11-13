"""Encrypted backup and no-overwrite restore of isolated synthetic latch fixtures.

NOT a production recovery path. Never imported by Flask or paper fill code.
All PLAINTEXT and SQLite work stays under verified Linux /dev/shm.
The authenticated, encrypted bytes leave this function ONLY as its return.
An externally held latest checkpoint is required to identify snapshot rollback;
there is no monotonic pin store and no durable disk/host-crash guarantee.
"""
from __future__ import annotations

from contextlib import closing
import os
from pathlib import Path
import sqlite3
import stat
import tempfile

from cryptography.fernet import Fernet, InvalidToken

from . import shadow_storage
from . import tenant_paper_latch_rehearsal as latch
from . import tenant_paper_latch_attestation as attest

_MAGIC = b"EDGEPILOT-OFFLINE-SYNTHETIC-LATCH-ARCHIVE-v1\n"
_MAX_SQLITE = 8 * 1024 * 1024
_EXPECTED_TABLES = frozenset({
    "offline_latch_marker", "offline_latch_policies", "offline_latch_journal",
})
_DENIED = "Offline synthetic latch archive unavailable"


class SyntheticLatchArchiveDenied(ValueError):
    """Nonsecret refusal; no paths or account data are exposed."""


def _cipher(archive_key, journal_key, anchor_key):
    journal, anchor = attest._keys(journal_key, anchor_key)
    if not isinstance(archive_key, bytes):
        raise SyntheticLatchArchiveDenied(_DENIED)
    try:
        cipher = Fernet(archive_key)
    except (ValueError, TypeError, Exception) as exc:
        raise SyntheticLatchArchiveDenied(_DENIED) from None
    # Separate independent encryption key. Do not reuse HMAC raw bytes.
    if archive_key in (journal, anchor):
        raise SyntheticLatchArchiveDenied(_DENIED)
    return cipher


def _audit(path, *, journal_key, anchor_key, trusted_checkpoint):
    """Check complete isolated schema and pinned chain, no write migrations."""
    with closing(latch._open(path)) as db:
        db.execute("BEGIN")
        if (db.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                or db.execute("PRAGMA foreign_key_check").fetchone() is not None
                or db.execute("PRAGMA journal_mode").fetchone()[0].lower()
                != "delete"):
            raise SyntheticLatchArchiveDenied(_DENIED)
        objects = db.execute("""SELECT name,type FROM sqlite_master
            WHERE type IN ('table','view','trigger')""").fetchall()
        if (frozenset(row["name"] for row in objects) != _EXPECTED_TABLES
                or any(row["type"] != "table" for row in objects)):
            raise SyntheticLatchArchiveDenied(_DENIED)
        # Trust comes from the external latest pin, never from a freshly
        # calculated checkpoint based on an untrusted restored fixture.
        attest._verify_pinned(
            db, journal_key, anchor_key, trusted_checkpoint)


def _parent_for_new_file(destination):
    root = shadow_storage.memory_root()
    target = Path(destination)
    if target.name in ("", ".", "..") or target.parent.is_symlink():
        raise SyntheticLatchArchiveDenied(_DENIED)
    parent = target.parent.resolve(strict=True)
    if (parent != root and root not in parent.parents) or target.parent != parent:
        raise SyntheticLatchArchiveDenied(_DENIED)
    if target.exists() or target.is_symlink():
        raise SyntheticLatchArchiveDenied(_DENIED)
    return target, parent


def seal_synthetic_latch_archive(
        source_path, *, journal_key, anchor_key, archive_key,
        trusted_checkpoint):
    """Return in-memory Fernet ciphertext of a consistent verified snapshot.

    No plaintext copy is ever written outside verified /dev/shm. The caller
    alone is responsible for secure storage of ciphertext and latest pin.
    """
    try:
        cipher = _cipher(archive_key, journal_key, anchor_key)
        source = latch._file(source_path)
        shadow_storage.require_isolated_source(source)
        if source.stat().st_size > _MAX_SQLITE:
            raise SyntheticLatchArchiveDenied(_DENIED)
        with tempfile.TemporaryDirectory(
                prefix=".edgepilot-latch-seal-", dir="/dev/shm") as folder:
            copy = Path(folder) / "snapshot.db"
            fd = os.open(str(copy), os.O_CREAT | os.O_EXCL |
                         os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            with closing(latch._open(source)) as original:
                if (original.execute("PRAGMA journal_mode").fetchone()[0]
                        .lower() != "delete"):
                    raise SyntheticLatchArchiveDenied(_DENIED)
                with closing(sqlite3.connect(str(copy), timeout=10)) as clone:
                    original.backup(clone)
            _audit(copy, journal_key=journal_key, anchor_key=anchor_key,
                   trusted_checkpoint=trusted_checkpoint)
            raw = copy.read_bytes()
            if (not raw.startswith(b"SQLite format 3\x00")
                    or len(raw) > _MAX_SQLITE):
                raise SyntheticLatchArchiveDenied(_DENIED)
            return cipher.encrypt(_MAGIC + raw)
    except Exception:
        raise SyntheticLatchArchiveDenied(_DENIED) from None


def restore_synthetic_latch_archive(
        ciphertext, destination_path, *, journal_key, anchor_key,
        archive_key, trusted_checkpoint, _fail_before_publish=False):
    """Validate privately, then atomically hardlink a NEW tmpfs fixture.

    The supplied trusted_checkpoint MUST be the independently held latest
    pin, or older valid archives cannot be differentiated from rollbacks.
    No implicit key rotation, policy reset, or latch clearing is permitted.
    """
    try:
        cipher = _cipher(archive_key, journal_key, anchor_key)
        if (type(ciphertext) is not bytes or not ciphertext
                or len(ciphertext) > 2 * _MAX_SQLITE + 8192):
            raise SyntheticLatchArchiveDenied(_DENIED)
        payload = cipher.decrypt(ciphertext)
        if (not payload.startswith(_MAGIC)
                or not payload[len(_MAGIC):].startswith(b"SQLite format 3\x00")
                or len(payload) - len(_MAGIC) > _MAX_SQLITE):
            raise SyntheticLatchArchiveDenied(_DENIED)
        target, parent = _parent_for_new_file(destination_path)
    except Exception:
        raise SyntheticLatchArchiveDenied(_DENIED) from None
    stage = None
    try:
        fd, name = tempfile.mkstemp(
            prefix=".edgepilot-latch-restore-", suffix=".db", dir=str(parent))
        stage = Path(name)
        with os.fdopen(fd, "wb") as writer:
            writer.write(payload[len(_MAGIC):])
            writer.flush()
            os.fsync(writer.fileno())
        if (stat.S_IMODE(stage.stat().st_mode) != 0o600
                or stage.stat().st_nlink != 1):
            raise SyntheticLatchArchiveDenied(_DENIED)
        _audit(stage, journal_key=journal_key, anchor_key=anchor_key,
               trusted_checkpoint=trusted_checkpoint)
        with stage.open("rb") as reader:
            os.fsync(reader.fileno())
        if _fail_before_publish:
            raise SyntheticLatchArchiveDenied(_DENIED)
        # Never expose an unvalidated destination and never replace one
        # that was created while this private staging file was verified.
        os.link(stage, target)
        return target
    except Exception:
        raise SyntheticLatchArchiveDenied(_DENIED) from None
    finally:
        if stage is not None:
            for ending in ("", "-journal", "-wal", "-shm"):
                try:
                    Path(str(stage) + ending).unlink(missing_ok=True)
                except OSError:
                    pass
