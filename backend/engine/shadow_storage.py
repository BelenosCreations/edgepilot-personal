"""Fail-closed, Linux-only, memory-backed storage gate for offline rehearsals.

Plaintext is never created in the process-default temporary directory. Both
the recovered source and every disposable SQLite copy MUST live on the verified
/dev/shm tmpfs mount. No production server code imports this module.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path


class MemoryStorageError(RuntimeError):
    """Safe message: no plaintext path, secret or account reference."""


def memory_root():
    root = Path("/dev/shm")
    try:
        resolved = root.resolve(strict=True)
        mounts = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
        # The mount point must be /dev/shm itself, not a parent filesystem
        # or a symlink whose destination happens to be writable.
        mounts_ok = any(
            fields[4] == "/dev/shm" and details[0] == "tmpfs"
            for entry in mounts.splitlines()
            for halves in [entry.split(" - ", 1)]
            if len(halves) == 2
            for fields, details in [(halves[0].split(), halves[1].split())]
            if len(fields) >= 5 and len(details) >= 1
        )
        if resolved != root or not mounts_ok or not resolved.is_dir():
            raise MemoryStorageError("Verified memory-backed storage unavailable")
        return resolved
    except (OSError, ValueError, UnicodeError):
        raise MemoryStorageError("Verified memory-backed storage unavailable") from None


def require_isolated_source(path):
    """Reject any source outside real tmpfs, even with symlink/path tricks."""
    root = memory_root()
    try:
        candidate = Path(path).expanduser().resolve(strict=True)
        metadata = candidate.stat()
        if (candidate == root or root not in candidate.parents
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_dev != root.stat().st_dev):
            raise MemoryStorageError("Isolated plaintext source must be in verified tmpfs")
        # A detached restored source must be a self-contained SQLite file.
        # Open WAL sidecars may checkpoint into the main file during rehearsal
        # and change its bytes even when the logical contents are identical.
        wal = Path(str(candidate) + "-wal")
        if wal.exists() and (not wal.is_file() or wal.stat().st_size > 0):
            raise MemoryStorageError("Restored SQLite source has active WAL; refuse rehearsal")
        # Leave room for SQLite's backup, indexing, journals and integrity checks.
        fs = os.statvfs(root)
        free_bytes = fs.f_bavail * fs.f_frsize
        required = metadata.st_size * 3 + 4 * 1024 * 1024
        if free_bytes < required:
            raise MemoryStorageError("Insufficient verified tmpfs capacity")
        return candidate, root
    except (OSError, ValueError):
        raise MemoryStorageError("Isolated plaintext source unavailable") from None
