"""Offline-only, encrypted SQLite backup and restore-rehearsal safeguards.

IMPORTANT: This module is NEVER imported by the hosted Flask application and
NEVER reads a production DB unless an operator separately runs the offline
tool with an explicit database path and approval phrase. No migration or
activation is implemented here. The current worker and Public secret are untouched.

Backups encrypt SQLite's consistent backup snapshot using AES-256-GCM.
The sensitive key is supplied separately (environment/secret manager).
Encrypted DB bytes do NOT include the unrelated Render encryption key
required for the existing Public credential vault. Preserve that separately.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import stat
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b"EDGEPILOT-BK1\x00"
NONCE_SIZE = 12
TAG_SIZE = 16
DIGEST_SIZE = 32
CHUNK_SIZE = 1024 * 1024
APPROVAL_PHRASE = "REHEARSE OFFLINE ONLY"
ENABLED_ENV = "EDGE_MIGRATION_TOOLS_ENABLED"


class MigrationSafetyError(RuntimeError):
    """Redacted failure without printing passwords, credentials or DB rows."""


def _enabled(phrase):
    if os.getenv(ENABLED_ENV, "false").lower() != "true":
        raise MigrationSafetyError("Offline migration tools are disabled")
    if phrase != APPROVAL_PHRASE:
        raise MigrationSafetyError("Explicit offline approval phrase required")


def _key(value):
    if not isinstance(value, str) or len(value) > 160:
        raise MigrationSafetyError("Backup encryption key invalid")
    try:
        raw = base64.b64decode(value.encode("ascii"), altchars=b"-_", validate=True)
    except (ValueError, UnicodeError):
        raise MigrationSafetyError("Backup encryption key invalid") from None
    if len(raw) != 32:
        raise MigrationSafetyError("Backup encryption key must be 32 random bytes")
    return raw


def _source(path):
    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file() or not stat.S_ISREG(source.stat().st_mode):
        raise MigrationSafetyError("Source must be an existing SQLite file")
    return source


def _target(path):
    target = Path(path).expanduser().absolute()
    if not target.parent.is_dir() or target.exists() or target.is_symlink():
        raise MigrationSafetyError("Output must be a new file in an existing directory")
    return target


def _connection(path):
    # mode=ro NEVER creates or mutates the source. Not immutable=1: WAL matters.
    return sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=30)


def _checks(connection):
    integrity = connection.execute("PRAGMA integrity_check").fetchall()
    if integrity != [("ok",)]:
        raise MigrationSafetyError("Database integrity validation failed")
    if connection.execute("PRAGMA foreign_key_check").fetchone():
        raise MigrationSafetyError("Database foreign-key validation failed")
    schema = connection.execute("""SELECT name,sql FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name""").fetchall()
    if not schema or not any(row[0] == "settings" for row in schema):
        raise MigrationSafetyError("Not a recognized EdgePilot database")
    counts = {}
    for name, _ in schema:
        if not isinstance(name, str) or len(name) > 180:
            raise MigrationSafetyError("Unsupported database table name")
        quoted = '"' + name.replace('"', '""') + '"'
        counts[name] = connection.execute("SELECT COUNT(*) FROM " + quoted).fetchone()[0]
    fingerprint = hashlib.sha256(
        json.dumps(schema, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    selected = connection.execute(
        "SELECT 1 FROM settings WHERE k='account_id' AND LENGTH(v)>0 LIMIT 1"
    ).fetchone() is not None
    connected = "broker_credentials" in counts and connection.execute(
        "SELECT 1 FROM broker_credentials WHERE provider='public' LIMIT 1"
    ).fetchone() is not None
    return {
        "integrity": "ok",
        "foreignKeys": "ok",
        "tableCounts": counts,
        "schemaSha256": fingerprint,
        "legacyAccountSelected": selected,
        "legacyCredentialRecordPresent": connected,
        "migrationExecuted": False,
    }


def inspect_database(path):
    """Read-only, sanitized report. Never return credential or account values."""
    source = _source(path)
    try:
        with _connection(source) as con:
            return _checks(con)
    except (sqlite3.Error, OSError) as exc:
        raise MigrationSafetyError("Database inspection failed") from None


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as reader:
        while True:
            chunk = reader.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.digest()


@contextmanager
def _private_temp_dir():
    # 0700 directory and 0600 output protect plaintext snapshot from other
    # local users. Temp storage may leave forensic remnants without disk encryption.
    with tempfile.TemporaryDirectory(prefix="edgepilot-offline-", ignore_cleanup_errors=False) as name:
        os.chmod(name, 0o700)
        yield Path(name)


def _secure_temp_in(parent):
    fd, path = tempfile.mkstemp(prefix=".edgepilot-work-", dir=str(parent))
    os.fchmod(fd, 0o600)
    return fd, Path(path)


def _install_once(temp_path, output):
    # Atomic publish, refuses to overwrite another file (even via race).
    os.link(temp_path, output)


def create_encrypted_backup(source_db, encrypted_output, *, key, phrase):
    """Opt-in consistent SQLite backup to brand-new AES-GCM archive.

    Returns sanitized verification metadata. Never overwrites output and does
    not write any existing database. Caller must have suspended writers before
    a future real migration; snapshot itself remains consistent if WAL is used.
    """
    _enabled(phrase)
    raw_key = _key(key)
    source, target = _source(source_db), _target(encrypted_output)
    if source == target:
        raise MigrationSafetyError("Backup cannot overwrite the source")
    source_report = inspect_database(source)
    fd = None
    temp_encrypted = None
    try:
        with _private_temp_dir() as private:
            snapshot = private / "snapshot.sqlite3"
            with _connection(source) as src, sqlite3.connect(snapshot) as dest:
                src.backup(dest)
            os.chmod(snapshot, 0o600)
            snapshot_report = inspect_database(snapshot)
            # Compare schema and counts across snapshots. In a real maintenance
            # window this must match. An active writer invalidates rehearsal.
            if (source_report["schemaSha256"] != snapshot_report["schemaSha256"] or
                source_report["tableCounts"] != snapshot_report["tableCounts"]):
                raise MigrationSafetyError("Database changed during backup; retry offline")
            digest = _sha256_file(snapshot)
            nonce = os.urandom(NONCE_SIZE)
            header = MAGIC + nonce
            fd, temp_encrypted = _secure_temp_in(target.parent)
            with os.fdopen(fd, "wb") as writer:
                fd = None
                writer.write(header)
                encryptor = Cipher(algorithms.AES(raw_key), modes.GCM(nonce)).encryptor()
                encryptor.authenticate_additional_data(header)
                writer.write(encryptor.update(digest))
                with open(snapshot, "rb") as plain:
                    while True:
                        chunk = plain.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        writer.write(encryptor.update(chunk))
                writer.write(encryptor.finalize())
                writer.write(encryptor.tag)
                writer.flush()
                os.fsync(writer.fileno())
            _install_once(temp_encrypted, target)
            return {
                "archiveSha256": _sha256_file(target).hex(),
                "snapshotSha256": digest.hex(),
                "schemaSha256": snapshot_report["schemaSha256"],
                "tableCounts": snapshot_report["tableCounts"],
                "encrypted": True,
                "migrated": False,
                "recoveryKeyIncluded": False,
            }
    except (sqlite3.Error, OSError, ValueError, InvalidTag) as exc:
        raise MigrationSafetyError("Encrypted backup failed; no source data changed") from None
    finally:
        if fd is not None:
            os.close(fd)
        if temp_encrypted is not None:
            temp_encrypted.unlink(missing_ok=True)


def restore_encrypted_backup(archive, restored_output, *, key, phrase):
    """Verify authenticated archive, SHA-256 and SQLite integrity before publish.

    Never overwrite an existing restored database. This is for a new isolated
    destination, NEVER the active production DB path.
    """
    _enabled(phrase)
    raw_key = _key(key)
    input_file = _source(archive)
    output = _target(restored_output)
    if input_file == output:
        raise MigrationSafetyError("Cannot overwrite backup archive")
    fd = None
    temp_restored = None
    try:
        archive_size = input_file.stat().st_size
        if archive_size < len(MAGIC) + NONCE_SIZE + TAG_SIZE + DIGEST_SIZE + 512:
            raise MigrationSafetyError("Backup archive incomplete")
        with open(input_file, "rb") as reader:
            header = reader.read(len(MAGIC) + NONCE_SIZE)
            if not header.startswith(MAGIC) or len(header) != len(MAGIC) + NONCE_SIZE:
                raise MigrationSafetyError("Unrecognized encrypted backup format")
            nonce = header[len(MAGIC):]
            reader.seek(-TAG_SIZE, os.SEEK_END)
            tag = reader.read(TAG_SIZE)
            reader.seek(len(header))
            decryptor = Cipher(algorithms.AES(raw_key), modes.GCM(nonce, tag)).decryptor()
            decryptor.authenticate_additional_data(header)
            fd, temp_restored = _secure_temp_in(output.parent)
            remaining = archive_size - len(header) - TAG_SIZE
            prefixed_digest = bytearray()
            digest = hashlib.sha256()
            with os.fdopen(fd, "wb") as writer:
                fd = None
                while remaining:
                    encrypted = reader.read(min(CHUNK_SIZE, remaining))
                    if not encrypted:
                        raise MigrationSafetyError("Backup archive truncated")
                    remaining -= len(encrypted)
                    plain = decryptor.update(encrypted)
                    if len(prefixed_digest) < DIGEST_SIZE:
                        take = min(DIGEST_SIZE - len(prefixed_digest), len(plain))
                        prefixed_digest.extend(plain[:take])
                        plain = plain[take:]
                    if plain:
                        writer.write(plain)
                        digest.update(plain)
                decryptor.finalize()  # Authentication MUST succeed before publish.
                writer.flush()
                os.fsync(writer.fileno())
        if len(prefixed_digest) != DIGEST_SIZE or digest.digest() != bytes(prefixed_digest):
            raise MigrationSafetyError("Backup content checksum mismatch")
        restored_report = inspect_database(temp_restored)
        _install_once(temp_restored, output)
        return {
            "snapshotSha256": digest.hexdigest(),
            "schemaSha256": restored_report["schemaSha256"],
            "tableCounts": restored_report["tableCounts"],
            "integrity": restored_report["integrity"],
            "foreignKeys": restored_report["foreignKeys"],
            "restoredToNewFile": True,
            "migrationExecuted": False,
        }
    except (sqlite3.Error, OSError, ValueError, InvalidTag) as exc:
        raise MigrationSafetyError("Restore verification failed; no existing data changed") from None
    finally:
        if fd is not None:
            os.close(fd)
        if temp_restored is not None:
            temp_restored.unlink(missing_ok=True)


def rehearse_restore(source_db, *, key, phrase):
    """Fully isolated end-to-end backup/restore verification, no live migration.

    Rehearsal requires the same explicit opt-in as backup and restore.
    It creates an encrypted backup and decrypted test restore in a temporary
    directory, validates records and then destroys the temporary files.
    """
    _enabled(phrase)
    source = _source(source_db)
    before = inspect_database(source)
    with _private_temp_dir() as temp:
        encrypted = temp / "backup.epbk"
        restored = temp / "restored.sqlite3"
        backup = create_encrypted_backup(source, encrypted, key=key, phrase=phrase)
        result = restore_encrypted_backup(encrypted, restored, key=key, phrase=phrase)
        after = inspect_database(source)
        if (before != after or
            backup["tableCounts"] != result["tableCounts"] or
            backup["schemaSha256"] != result["schemaSha256"] or
            backup["snapshotSha256"] != result["snapshotSha256"]):
            raise MigrationSafetyError("Rehearsal comparison failed; keep migration disabled")
        return {
            "rehearsalPassed": True,
            "sourceUnchangedAtLogicalLevel": True,
            "encryptedArchiveVerified": True,
            "isolatedRestoreVerified": True,
            "schemaSha256": result["schemaSha256"],
            "tableCounts": result["tableCounts"],
            "realAccountMigrationExecuted": False,
            "productionRolloutAuthorized": False,
            "note": "A passing rehearsal is not approval to migrate or activate tenancy.",
        }
