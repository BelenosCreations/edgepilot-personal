"""v0.2.70: genuine encrypted owner backup verified on synthetic DB only."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet
from engine import identity_auth, tenant_foundation
from engine import permanent_tenant_owner_backup as backup


class FirstOwnerBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.disk = self.root / "data"
        self.ram = self.root / "shm"
        self.disk.mkdir()
        self.ram.mkdir()
        self.legacy = self.disk / "edgepilot.db"
        self.tenant = self.disk / "edgepilot-tenants.db"
        self.output = self.ram / "owner.epbk"
        with sqlite3.connect(self.legacy) as db:
            db.execute("CREATE TABLE settings (k TEXT PRIMARY KEY, v TEXT)")
            db.execute("CREATE TABLE broker_credentials (provider TEXT PRIMARY KEY, ciphertext BLOB)")
            db.execute("CREATE TABLE orders (id TEXT)")
            db.execute("CREATE TABLE activity (id INTEGER)")
            db.execute("INSERT INTO broker_credentials VALUES ('public',?)",
                       (b'SYNTHETIC-LEGACY-CIPHERTEXT',))
        tenant_foundation.setup(str(self.tenant))
        identity_auth.setup(str(self.tenant))
        store = tenant_foundation.TenantStore(str(self.tenant))
        uid = store.provision_user("Belenos-Owner", role="owner")
        identity_auth.IdentityStore(str(self.tenant)).provision(
            uid, "Belenos-Owner", "synthetic-owner-password-for-test-only")
        os.chmod(self.legacy, 0o600)
        os.chmod(self.tenant, 0o600)
        self.key = Fernet.generate_key().decode()
        self.env = {
            "EDGE_TENANT_OWNER_BACKUP_ALLOWED": "true",
            "EDGE_SHARED_TENANT_DB_PREPARE": "true",
            "EDGE_TENANT_SCHEMA_PREPARE": "true",
            "EDGE_TENANT_DB_PATH": str(self.tenant),
            "EDGE_AUTOMATION_WORKER_ENABLED": "false",
            "ENABLE_LIVE_ORDERS": "false",
        }

    def create(self, env=None, key=None):
        return backup.create_verified_owner_archive(
            self.env if env is None else env, self.legacy, self.tenant, self.output,
            key_b64=self.key if key is None else key, approval=backup.APPROVAL,
            persistent_root=self.disk, temp_root=self.ram)

    def test_sealed_snapshot_restores_without_changing_existing_owner_data(self):
        legacy = self.legacy.read_bytes()
        tenant = self.tenant.read_bytes()
        result = self.create()
        self.assertTrue(result["backup_verified"])
        self.assertTrue(result["isolated_restore_verified"])
        self.assertFalse(result["off_service_copy_verified"])
        self.assertFalse(result["authorized_to_activate"])
        self.assertEqual(result["first_owner_count"], 1)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.legacy.read_bytes(), legacy)
        self.assertEqual(self.tenant.read_bytes(), tenant)
        encrypted = self.output.read_bytes()
        self.assertTrue(encrypted.startswith(backup.MAGIC))
        self.assertNotIn(b"Belenos-Owner", encrypted)
        self.assertNotIn(b"SYNTHETIC-LEGACY-CIPHERTEXT", encrypted)
        self.assertEqual(len(backup.verify_owner_archive(
            self.output, key_b64=self.key, temp_root=self.ram)), 64)
        self.assertEqual(list(self.ram.glob("edgepilot-owner-restore-*")), [])

    def test_existing_archive_not_overwritten(self):
        self.create()
        before = self.output.read_bytes()
        with self.assertRaises(backup.OwnerArchiveDenied):
            self.create()
        self.assertEqual(self.output.read_bytes(), before)

    def test_wrong_key_or_tampering_refuses_restore(self):
        self.create()
        with self.assertRaises(backup.OwnerArchiveDenied):
            backup.verify_owner_archive(self.output, key_b64=Fernet.generate_key().decode(),
                                        temp_root=self.ram)
        with self.output.open("r+b") as out:
            out.seek(len(backup.MAGIC) + 13)
            old = out.read(1)
            out.seek(-1, os.SEEK_CUR)
            out.write(bytes((old[0] ^ 1,)))
        with self.assertRaises(backup.OwnerArchiveDenied):
            backup.verify_owner_archive(self.output, key_b64=self.key, temp_root=self.ram)

    def test_disabled_owner_and_live_worker_or_trading_are_denied(self):
        for flag in backup.DORMANT:
            with self.subTest(flag=flag):
                with self.assertRaises(backup.OwnerArchiveDenied):
                    self.create({**self.env, flag: "true"})
        with self.assertRaises(backup.OwnerArchiveDenied):
            self.create({**self.env, "EDGE_TENANT_OWNER_BACKUP_ALLOWED": "false"})
        with sqlite3.connect(self.tenant) as db:
            db.execute("UPDATE tenant_users SET disabled_at='test-disabled'")
        with self.assertRaises(backup.OwnerArchiveDenied):
            self.create()
        self.assertFalse(self.output.exists())

    def test_unprotected_or_linked_tenant_denied(self):
        os.chmod(self.tenant, 0o644)
        with self.assertRaises(backup.OwnerArchiveDenied):
            self.create()
        os.chmod(self.tenant, 0o600)
        other = self.disk / "actual-owner.db"
        self.tenant.rename(other)
        self.tenant.symlink_to(other)
        with self.assertRaises(backup.OwnerArchiveDenied):
            self.create()
        self.tenant.unlink()
        self.tenant.hardlink_to(other)
        with self.assertRaises(backup.OwnerArchiveDenied):
            self.create()


if __name__ == "__main__":
    unittest.main()
