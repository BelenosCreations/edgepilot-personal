"""Independently approved encrypted backups of offline Decimal fixtures."""
from contextlib import closing
import base64
import hashlib
import hmac
import os
from pathlib import Path
import sqlite3
import stat
import tempfile

from cryptography.fernet import Fernet

from . import shadow_storage
from . import tenant_paper_decimal_atomic_rehearsal as ledger
from . import tenant_paper_decimal_recovery as recovery

_MAGIC = b"EDGEPILOT-OFFLINE-DECIMAL-ARCHIVE-v1\n"
_SQLITE_HEADER = b"SQLite format 3\x00"
_MAX_DB = 8 * 1024 * 1024
_MAX_TOKEN = 2 * _MAX_DB + 8192


def _cipher(archive_key, *keys):
    # Compare the decoded secret, so base64-encoding an existing HMAC key
    # cannot pass the independence check.
    raw_key = base64.b64decode(archive_key, altchars=b"-_", validate=True)
    recovery._keys(raw_key, *keys)
    return Fernet(archive_key)


def _audit(path, record, journal, anchor):
    with recovery._fixture(path) as db:
        recovery._require_checkpoint(db, journal, anchor, record["current"])


def _digest(ciphertext):
    if type(ciphertext) is not bytes or not 0 < len(ciphertext) <= _MAX_TOKEN:
        recovery._deny()
    return hashlib.sha256(ciphertext).hexdigest()


def _destination(path):
    root = shadow_storage.memory_root()
    target = Path(path)
    parent = target.parent.resolve(strict=True)
    info = parent.stat()
    if (root not in parent.parents or target.parent != parent
            or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700
            or info.st_dev != root.stat().st_dev
            or any(os.path.lexists(str(target) + suffix) for suffix in ("", *recovery._SIDECARS))):
        recovery._deny()
    return target


def seal_decimal_archive(source, *, record, trusted_tip, journal_key, anchor_key,
                         operator_key, archive_key):
    """Encrypt one consistent snapshot after an exact active-checkpoint audit."""
    try:
        journal, anchor, operator = recovery._keys(journal_key, anchor_key, operator_key)
        recovery._review(record, trusted_tip, operator, "ACTIVE")
        cipher = _cipher(archive_key, journal, anchor, operator)
        path, root = shadow_storage.require_isolated_source(recovery._source(source))
        if path.stat().st_size > _MAX_DB:
            recovery._deny()
        with tempfile.TemporaryDirectory(prefix="edgepilot-decimal-seal-", dir=root) as folder:
            snapshot = Path(folder) / "snapshot.db"
            snapshot.touch(mode=0o600, exist_ok=False)
            with closing(ledger._open(path, read_only=True)) as original:
                with closing(sqlite3.connect(str(snapshot))) as copy:
                    original.backup(copy)
            _audit(snapshot, record, journal, anchor)
            with snapshot.open("rb") as reader:
                raw = reader.read(_MAX_DB + 1)
            if len(raw) > _MAX_DB or not raw.startswith(_SQLITE_HEADER):
                recovery._deny()
            return cipher.encrypt(_MAGIC + raw)
    except Exception:
        raise recovery.DecimalRecoveryDenied("Offline Decimal recovery unavailable") from None


def approve_decimal_restore(ciphertext, destination, *, record, trusted_tip, operator_key):
    """Sign explicit offline restore intent bound to this archive, tip and destination."""
    try:
        operator = ledger._key(operator_key)
        recovery._review(record, trusted_tip, operator, "ACTIVE")
        target = _destination(destination)
        return ledger._mac(operator, recovery._PROTOCOL, "RESTORE",
                           record["mac"], _digest(ciphertext), str(target))
    except Exception:
        raise recovery.DecimalRecoveryDenied("Offline Decimal recovery unavailable") from None


def restore_decimal_archive(ciphertext, destination, *, approval, record, trusted_tip,
                            journal_key, anchor_key, operator_key, archive_key,
                            _interrupt_before_publish=False):
    """Audit in private tmpfs and publish a new fixture only after explicit approval."""
    try:
        journal, anchor, operator = recovery._keys(journal_key, anchor_key, operator_key)
        target = _destination(destination)
        expected = approve_decimal_restore(
            ciphertext, target, record=record, trusted_tip=trusted_tip, operator_key=operator)
        if type(approval) is not str or not hmac.compare_digest(approval, expected):
            recovery._deny()
        cipher = _cipher(archive_key, journal, anchor, operator)
        payload = cipher.decrypt(ciphertext)
        raw = payload[len(_MAGIC):]
        if (not payload.startswith(_MAGIC) or not raw.startswith(_SQLITE_HEADER)
                or len(raw) > _MAX_DB):
            recovery._deny()
        with tempfile.TemporaryDirectory(prefix=".decimal-restore-", dir=target.parent) as folder:
            fd, name = tempfile.mkstemp(suffix=".db", dir=folder)
            staged = Path(name)
            with os.fdopen(fd, "wb") as writer:
                writer.write(raw)
                writer.flush()
                os.fsync(writer.fileno())
            _audit(staged, record, journal, anchor)
            if _interrupt_before_publish:
                recovery._deny()
            _destination(target)
            # Atomic no-replace publication. An interrupted cleanup can leave
            # two links; the fixture opener then refuses until operator review.
            os.link(staged, target)
        return target
    except Exception:
        raise recovery.DecimalRecoveryDenied("Offline Decimal recovery unavailable") from None
