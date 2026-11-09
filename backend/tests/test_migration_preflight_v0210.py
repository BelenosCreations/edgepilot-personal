"""Phase 4 offline migration backup/restore: safety and regression tests."""
import base64
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine import migration_preflight, tenant_foundation, identity_auth, account_scope

ROOT=Path(__file__).resolve().parents[2]
KEY=base64.urlsafe_b64encode(bytes(range(32))).decode()
OTHER_KEY=base64.urlsafe_b64encode(bytes(reversed(range(32)))).decode()
APPROVE=migration_preflight.APPROVAL_PHRASE


class MigrationRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.db=self.root/"owner.db"
        self.archive=self.root/"owner.epbk"
        self.restored=self.root/"verified.db"
        with sqlite3.connect(self.db) as db:
            db.executescript("""
                CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT NOT NULL);
                CREATE TABLE broker_credentials(
                    provider TEXT PRIMARY KEY,ciphertext BLOB,updated_at TEXT);
                CREATE TABLE account_snapshots(
                    id INTEGER PRIMARY KEY,account TEXT,ts TEXT,total_value TEXT,buying_power TEXT);
                CREATE TABLE observation_cycles(
                    id INTEGER PRIMARY KEY,completed_at TEXT,state TEXT);
                CREATE TABLE activity(id INTEGER PRIMARY KEY,ts TEXT,message TEXT);
            """)
            db.execute("INSERT INTO settings VALUES('account_id','PRIVATE-ACCOUNT-XYZ')")
            db.execute("INSERT INTO settings VALUES('protected_pct','50')")
            db.execute("INSERT INTO broker_credentials VALUES('public',?,?)",
                       (b'ENCRYPTED_PUBLIC_KEY_DO_NOT_SHOW','2026-11-09T00:00:00Z'))
            db.execute("INSERT INTO account_snapshots VALUES(1,'PRIVATE-ACCOUNT-XYZ','today','123.45','67.89')")
            db.execute("INSERT INTO observation_cycles VALUES(7,'today','OK')")
            db.execute("INSERT INTO activity VALUES(9,'today','PRIVATE_NOTE_DO_NOT_SHOW')")
        tenant_foundation.setup(str(self.db))
        identity_auth.setup(str(self.db))
        account_scope.setup(str(self.db))
        self.env=patch.dict(os.environ,{
            migration_preflight.ENABLED_ENV:"true",
            "EDGE_BACKUP_KEY_B64":KEY
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def backup(self, key=KEY, phrase=APPROVE):
        return migration_preflight.create_encrypted_backup(
            self.db,self.archive,key=key,phrase=phrase)

    def restore(self, key=KEY, phrase=APPROVE):
        return migration_preflight.restore_encrypted_backup(
            self.archive,self.restored,key=key,phrase=phrase)

    def test_sanitized_inspection_and_rehearsal_do_not_change_legacy_data(self):
        before=migration_preflight.inspect_database(self.db)
        self.assertTrue(before["legacyAccountSelected"])
        self.assertTrue(before["legacyCredentialRecordPresent"])
        self.assertEqual(before["integrity"],"ok")
        self.assertEqual(before["foreignKeys"],"ok")
        self.assertTrue("tenant_worker_leases" in before["tableCounts"])
        for secret in ("PRIVATE-ACCOUNT-XYZ","PRIVATE_NOTE_DO_NOT_SHOW",
                       "ENCRYPTED_PUBLIC_KEY_DO_NOT_SHOW"):
            self.assertNotIn(secret,json.dumps(before))
        file_before=hashlib.sha256(self.db.read_bytes()).digest()
        status=migration_preflight.rehearse_restore(self.db,key=KEY,phrase=APPROVE)
        self.assertTrue(status["rehearsalPassed"])
        self.assertTrue(status["sourceUnchangedAtLogicalLevel"])
        self.assertTrue(status["encryptedArchiveVerified"])
        self.assertTrue(status["isolatedRestoreVerified"])
        self.assertFalse(status["realAccountMigrationExecuted"])
        self.assertFalse(status["productionRolloutAuthorized"])
        self.assertEqual(file_before,hashlib.sha256(self.db.read_bytes()).digest())
        self.assertEqual(before,migration_preflight.inspect_database(self.db))
        self.assertEqual(set(self.root.iterdir()),{self.db})

    def test_backup_encryption_restore_integrity_and_permissions(self):
        original_file=hashlib.sha256(self.db.read_bytes()).digest()
        backed=self.backup()
        self.assertTrue(backed["encrypted"])
        self.assertFalse(backed["migrated"])
        self.assertFalse(backed["recoveryKeyIncluded"])
        self.assertTrue(self.archive.is_file())
        self.assertEqual(self.archive.stat().st_mode & 0o777,0o600)
        data=self.archive.read_bytes()
        self.assertTrue(data.startswith(migration_preflight.MAGIC))
        for plaintext in (b"PRIVATE-ACCOUNT-XYZ",b"PRIVATE_NOTE_DO_NOT_SHOW",
                          b"ENCRYPTED_PUBLIC_KEY_DO_NOT_SHOW",b"SQLite format 3"):
            self.assertNotIn(plaintext,data)
        result=self.restore()
        self.assertTrue(result["restoredToNewFile"])
        self.assertEqual(result["snapshotSha256"],backed["snapshotSha256"])
        self.assertEqual(result["schemaSha256"],backed["schemaSha256"])
        self.assertEqual(result["tableCounts"],backed["tableCounts"])
        self.assertEqual(self.restored.stat().st_mode & 0o777,0o600)
        self.assertEqual(original_file,hashlib.sha256(self.db.read_bytes()).digest())
        with sqlite3.connect(self.restored) as db:
            self.assertEqual(db.execute("SELECT v FROM settings WHERE k='account_id'").fetchone()[0],
                             "PRIVATE-ACCOUNT-XYZ")
            self.assertEqual(db.execute("SELECT state FROM observation_cycles WHERE id=7").fetchone()[0],
                             "OK")
            self.assertEqual(db.execute("SELECT ciphertext FROM broker_credentials").fetchone()[0],
                             b"ENCRYPTED_PUBLIC_KEY_DO_NOT_SHOW")

    def test_tampered_archive_and_wrong_key_never_publish_restored_file(self):
        self.backup()
        content=bytearray(self.archive.read_bytes())
        content[len(migration_preflight.MAGIC)+migration_preflight.NONCE_SIZE+45] ^= 0x01
        self.archive.write_bytes(content)
        with self.assertRaises(migration_preflight.MigrationSafetyError):
            self.restore()
        self.assertFalse(self.restored.exists())
        self.archive.unlink()
        self.backup()
        with self.assertRaises(migration_preflight.MigrationSafetyError):
            self.restore(key=OTHER_KEY)
        self.assertFalse(self.restored.exists())

    def test_disabled_by_default_and_wrong_approval_phrase(self):
        with patch.dict(os.environ,{migration_preflight.ENABLED_ENV:"false"}):
            with self.assertRaisesRegex(migration_preflight.MigrationSafetyError,"disabled"):
                self.backup()
        with self.assertRaisesRegex(migration_preflight.MigrationSafetyError,"phrase"):
            self.backup(phrase="MIGRATE NOW")
        self.assertFalse(self.archive.exists())
        self.assertFalse(self.restored.exists())

    def test_wrong_key_format_and_overwrite_always_fail_closed(self):
        with self.assertRaises(migration_preflight.MigrationSafetyError):
            self.backup(key="a-not-32-byte-key")
        self.backup()
        with self.assertRaises(migration_preflight.MigrationSafetyError):
            self.backup()
        with self.assertRaises(migration_preflight.MigrationSafetyError):
            migration_preflight.create_encrypted_backup(
                self.db,self.db,key=KEY,phrase=APPROVE)
        self.restored.write_bytes(b"leave-existing-database-untouched")
        with self.assertRaises(migration_preflight.MigrationSafetyError):
            self.restore()
        self.assertEqual(self.restored.read_bytes(),b"leave-existing-database-untouched")

    def test_missing_settings_or_corrupt_db_rejected_before_archive(self):
        other=self.root/"not-edgepilot.db"
        with sqlite3.connect(other) as db:
            db.execute("CREATE TABLE other_data(id INTEGER)")
        with self.assertRaises(migration_preflight.MigrationSafetyError):
            migration_preflight.create_encrypted_backup(
                other,self.archive,key=KEY,phrase=APPROVE)
        self.assertFalse(self.archive.exists())
        other.write_bytes(b"not a database")
        with self.assertRaises(migration_preflight.MigrationSafetyError):
            migration_preflight.inspect_database(other)

    def test_wal_snapshot_includes_committed_records(self):
        conn=sqlite3.connect(self.db)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("INSERT INTO activity VALUES(10,'today','COMMITTED-WAL-RECORD')")
            conn.commit()
            self.backup()
            self.restore()
            with sqlite3.connect(self.restored) as db:
                self.assertEqual(db.execute("SELECT message FROM activity WHERE id=10").fetchone()[0],
                                 "COMMITTED-WAL-RECORD")
        finally:
            conn.close()

    def test_offline_cli_inspect_and_rehearse_no_account_data_leaks(self):
        tool=ROOT/"backend/tools/migration_rehearsal.py"
        inspect=subprocess.run([sys.executable,str(tool),"inspect",
                "--database",str(self.db)],capture_output=True,text=True,
                timeout=20,check=False)
        self.assertEqual(inspect.returncode,0,inspect.stderr)
        self.assertNotIn("PRIVATE-ACCOUNT-XYZ",inspect.stdout)
        self.assertIn('"migrationExecuted": false',inspect.stdout)
        rehearse=subprocess.run([sys.executable,str(tool),"rehearse",
                "--database",str(self.db),"--approve",APPROVE],
                capture_output=True,text=True,timeout=35,check=False)
        self.assertEqual(rehearse.returncode,0,rehearse.stderr)
        self.assertIn('"rehearsalPassed": true',rehearse.stdout)
        self.assertNotIn("PRIVATE_NOTE_DO_NOT_SHOW",rehearse.stdout)

    def test_no_backend_integration_or_runtime_activation(self):
        app=(ROOT/"backend/app.py").read_text()
        self.assertNotIn("migration_preflight",app)
        self.assertNotIn("EDGE_MIGRATION_TOOLS_ENABLED",app)
        self.assertIn("EDGE_TENANT_ACCOUNT_READS_ENABLED",app)
        self.assertIn("'liveTradingAvailable':False",app)
        worker=(ROOT/"backend/engine/automation_worker.py").read_text()
        self.assertNotIn("migration_preflight",worker)
        source=(ROOT/"backend/engine/migration_preflight.py").read_text()
        self.assertNotIn("UPDATE settings",source)
        self.assertNotIn("ALTER TABLE",source)
        self.assertNotIn("CREATE USER",source)
        self.assertNotIn("INSERT INTO tenant_users",source)


if __name__=="__main__":
    unittest.main()
