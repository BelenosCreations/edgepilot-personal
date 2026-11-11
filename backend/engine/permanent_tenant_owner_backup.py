"""Offline backup of exactly one enrolled permanent owner, not a live restore.

Legacy migration_preflight cannot back up tenant databases (requires settings).
This tool remains dormant and uses only private RAM-backed temporary files.
"""
import base64
import hashlib
import os
import sqlite3
import stat
import tempfile
from contextlib import closing
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from . import permanent_cutover_preflight as preflight
from . import shared_storage_cutover as storage

MAGIC = b"EDGEPILOT-OWNER-TENANT-BK1\x00"
MAX_BYTES = 16 * 1024 * 1024
APPROVAL = "BACK UP PRIVATE EDGEPILOT OWNER"
DORMANT = (
    "EDGE_AUTOMATION_WORKER_ENABLED", "ENABLE_LIVE_ORDERS",
    "EDGE_PERMANENT_TENANTS_ONLY", "EDGE_PERMANENT_READONLY_PILOT_ENABLED",
    "EDGE_ISOLATED_STAGING", "EDGE_TENANT_SIGNUP_ENABLED",
    "EDGE_PERMANENT_OWNER_INVITES_ENABLED",
    "EDGE_TENANT_PUBLIC_VAULT_ENABLED", "EDGE_TENANT_PUBLIC_READONLY_ENABLED",
    "EDGE_TENANT_ACCOUNT_READS_ENABLED", "EDGE_TENANT_MONITOR_PREVIEW_ENABLED",
    "EDGE_TENANT_WATCHLIST_EDIT_ENABLED",
)


class OwnerArchiveDenied(RuntimeError):
    """Nonsecret refusal. Never include paths, SQL or actual exception text."""


def _private(path):
    try:
        st = Path(path).lstat()
        return (stat.S_ISREG(st.st_mode) and st.st_uid == os.geteuid()
                and st.st_nlink == 1 and stat.S_IMODE(st.st_mode) & 0o077 == 0)
    except OSError:
        return False


def _key(secret):
    try:
        raw = base64.b64decode(secret.encode("ascii"), altchars=b"-_",
                               validate=True)
        if len(raw) != 32:
            raise ValueError()
        return raw
    except (ValueError, UnicodeError, AttributeError):
        raise OwnerArchiveDenied("Offline owner backup key unavailable") from None


def _one_owner(path):
    count = preflight._verify_database(path, preflight.TENANT_TABLES,
                                       frozenset(("settings", "broker_credentials", "orders", "activity")))
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        owners = db.execute("""SELECT COUNT(*) FROM tenant_users u JOIN tenant_identities i
            ON i.user_id=u.user_id WHERE u.role='owner' AND u.disabled_at IS NULL
            AND i.password_hash LIKE '$argon2id$%'""").fetchone()[0]
        sessions = db.execute("SELECT COUNT(*) FROM tenant_identity_sessions").fetchone()[0]
    if count != 1 or owners != 1 or sessions != 0:
        raise OwnerArchiveDenied("A dormant first-owner identity is required")


def _verify_blob(blob, cipher_key, *, ram, expected_digest=None):
    if not blob.startswith(MAGIC) or len(blob) > MAX_BYTES + len(MAGIC) + 48:
        raise OwnerArchiveDenied("Encrypted first-owner archive invalid")
    nonce = blob[len(MAGIC):len(MAGIC)+12]
    ciphertext = blob[len(MAGIC)+12:]
    try:
        raw = AESGCM(cipher_key).decrypt(nonce, ciphertext, MAGIC)
    except (InvalidTag, ValueError):
        raise OwnerArchiveDenied("Encrypted first-owner archive authentication failed") from None
    digest = hashlib.sha256(raw).hexdigest()
    if expected_digest is not None and digest != expected_digest:
        raise OwnerArchiveDenied("First-owner snapshot digest mismatch")
    with tempfile.TemporaryDirectory(prefix="edgepilot-owner-restore-", dir=ram) as temp:
        restored = Path(temp) / "restore.sqlite3"
        fd = os.open(restored, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as dest:
            dest.write(raw)
            dest.flush()
            os.fsync(dest.fileno())
        _one_owner(restored)
    return digest


def create_verified_owner_archive(env, legacy_path, tenant_path, output_path,
                                  *, key_b64, approval,
                                  persistent_root=None, temp_root=None):
    """No production file writes; only publish a new encrypted RAM archive."""
    if approval != APPROVAL or env.get("EDGE_TENANT_OWNER_BACKUP_ALLOWED") != "true":
        raise OwnerArchiveDenied("Explicit first-owner backup approval required")
    if any(storage._flag(env, f) for f in DORMANT):
        raise OwnerArchiveDenied("Tenant, trading and worker features must remain dormant")
    root = storage.PERSISTENT_ROOT if persistent_root is None else Path(persistent_root)
    ram = Path("/dev/shm") if temp_root is None else Path(temp_root)
    legacy, tenant, output = Path(legacy_path), Path(tenant_path), Path(output_path)
    if (not root.is_absolute() or root.is_symlink() or not root.is_dir()
            or not ram.is_absolute() or ram.is_symlink() or not ram.is_dir()
            or legacy != root / storage.LEGACY_FILENAME
            or tenant != root / storage.TENANT_FILENAME or output.parent != ram
            or output.suffix != ".epbk" or output.exists() or output.is_symlink()
            or not _private(legacy) or not _private(tenant)
            or legacy.samefile(tenant)
            or env.get("EDGE_SHARED_TENANT_DB_PREPARE") != "true"
            or env.get("EDGE_TENANT_SCHEMA_PREPARE") != "true"
            or env.get("EDGE_TENANT_DB_PATH") != str(tenant)):
        raise OwnerArchiveDenied("Private existing paid-disk layout required")
    try:
        preflight._verify_database(legacy, preflight.LEGACY_TABLES,
                                   frozenset(("tenant_users",)))
        _one_owner(tenant)
        cipher_key = _key(key_b64)
        with tempfile.TemporaryDirectory(prefix="edgepilot-owner-snapshot-", dir=ram) as temp:
            snapshot = Path(temp) / "snapshot.sqlite3"
            with closing(sqlite3.connect(tenant.as_uri()+"?mode=ro", uri=True)) as src:
                src.execute("PRAGMA query_only=ON")
                with closing(sqlite3.connect(snapshot)) as dst:
                    src.backup(dst)
            os.chmod(snapshot, 0o600)
            if snapshot.stat().st_size > MAX_BYTES:
                raise OwnerArchiveDenied("First-owner snapshot exceeds limited archive size")
            _one_owner(snapshot)
            _one_owner(tenant)
            raw = snapshot.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            nonce = os.urandom(12)
            blob = MAGIC + nonce + AESGCM(cipher_key).encrypt(nonce, raw, MAGIC)
            del raw
        fd, staged_name = tempfile.mkstemp(prefix=".edgepilot-owner-archive-", dir=ram)
        staged = Path(staged_name)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as dst:
                fd = -1
                dst.write(blob)
                dst.flush()
                os.fsync(dst.fileno())
            os.link(staged, output, follow_symlinks=False)
        finally:
            if fd != -1:
                os.close(fd)
            staged.unlink(missing_ok=True)
        verified = _verify_blob(output.read_bytes(), cipher_key, ram=ram,
                                expected_digest=digest)
        return {
            "backup_verified": True,
            "isolated_restore_verified": verified == digest,
            "first_owner_count": 1,
            "archive_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "archive_private_0600": _private(output),
            "off_service_copy_verified": False,
            "authorized_to_activate": False,
            "legacy_data_migrated": False,
            "live_trading_enabled": False,
            "bank_transfers_enabled": False,
        }
    except OwnerArchiveDenied:
        raise
    except (OSError, ValueError, TypeError, sqlite3.Error,
            preflight.CutoverPreflightDenied):
        raise OwnerArchiveDenied("Encrypted first-owner backup refused safely") from None


def verify_owner_archive(path, *, key_b64, temp_root=None):
    """Read-only authenticated test restoration to a new private tmpfs file."""
    ram = Path("/dev/shm") if temp_root is None else Path(temp_root)
    target = Path(path)
    if target.parent != ram or not _private(target):
        raise OwnerArchiveDenied("Private owner archive required")
    try:
        return _verify_blob(target.read_bytes(), _key(key_b64), ram=ram)
    except OwnerArchiveDenied:
        raise
    except (OSError, ValueError, sqlite3.Error):
        raise OwnerArchiveDenied("Owner archive verification denied safely") from None
