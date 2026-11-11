"""v0.2.63: manual empty tenant DB creation on the existing paid disk."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine import permanent_cutover_preflight as preflight
from engine import permanent_storage_init as init


class PermanentStorageInitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.owner = self.root / "edgepilot.db"
        self.tenant = self.root / "edgepilot-tenants.db"
        with sqlite3.connect(self.owner) as db:
            db.execute("CREATE TABLE settings (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
            db.execute("INSERT INTO settings VALUES ('account_id','OWNER PRIVATE')")
            db.execute("CREATE TABLE broker_credentials (provider TEXT PRIMARY KEY, ciphertext BLOB)")
            db.execute("INSERT INTO broker_credentials VALUES ('public',?)",
                       (b'SYNTHETIC-ENCRYPTED-OWNER-ONLY',))
            db.execute("CREATE TABLE orders (id TEXT)")
            db.execute("CREATE TABLE activity (id INTEGER)")
        os.chmod(self.owner, 0o600)
        self.env = {
            "EDGE_PERMANENT_STORAGE_INIT_ALLOWED": "true",
            "EDGE_SHARED_TENANT_DB_PREPARE": "true",
            "EDGE_TENANT_SCHEMA_PREPARE": "true",
            "EDGE_TENANT_DB_PATH": str(self.tenant),
            "EDGE_ISOLATED_STAGING": "false",
            "EDGE_AUTOMATION_WORKER_ENABLED": "false",
            "ENABLE_LIVE_ORDERS": "false",
        }

    def prepare(self, env=None, approval=init.APPROVAL):
        return init.prepare_private_tenant_storage(
            self.env if env is None else env,
            self.owner, self.tenant, approval=approval,
            persistent_root=self.root)

    def test_success_creates_empty_isolated_0600_tenant_and_preserves_owner(self):
        before = self.owner.read_bytes()
        result = self.prepare()
        self.assertTrue(result["prepared"])
        self.assertFalse(result["production_backup_and_restore_verified"])
        self.assertFalse(result["authorized_to_activate"])
        self.assertFalse(result["owner_data_migrated"])
        self.assertEqual(self.owner.read_bytes(), before)
        self.assertEqual(self.tenant.stat().st_mode & 0o777, 0o600)
        self.assertNotEqual(self.tenant.stat().st_ino, self.owner.stat().st_ino)
        self.assertEqual(self.tenant.stat().st_nlink, 1)
        self.assertEqual(preflight._verify_database(
            self.tenant, init.TENANT_REQUIRED, init.TENANT_FORBIDDEN), 0)
        with sqlite3.connect(self.tenant) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tenant_identities").fetchone()[0], 0)
            self.assertIsNone(db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='broker_credentials'").fetchone())
        with sqlite3.connect(self.owner) as db:
            self.assertEqual(db.execute("SELECT ciphertext FROM broker_credentials").fetchone()[0],
                             b'SYNTHETIC-ENCRYPTED-OWNER-ONLY')
        report = preflight.inspect_cutover(
            {**self.env, "EDGE_CUTOVER_PREFLIGHT_ALLOWED": "true"},
            self.owner, self.tenant, persistent_root=self.root)
        self.assertEqual(report["inspection"], "passed")
        self.assertFalse(report["authorized_to_activate"])
        self.assertFalse(list(self.root.glob(".edgepilot-tenant-stage-*")))

    def test_repeat_call_does_not_modify_existing_tenant(self):
        self.prepare()
        old = self.tenant.read_bytes()
        with self.assertRaises(init.PrivateStorageInitDenied):
            self.prepare()
        self.assertEqual(self.tenant.read_bytes(), old)

    def test_gates_and_feature_flags_fail_without_writing_tenant_file(self):
        for key in init.DORMANT_FLAGS:
            with self.subTest(flag=key):
                with self.assertRaises(init.PrivateStorageInitDenied):
                    self.prepare({**self.env, key: "true"})
                self.assertFalse(self.tenant.exists())
        with self.assertRaises(init.PrivateStorageInitDenied):
            self.prepare(approval="APPROVE")
        with self.assertRaises(init.PrivateStorageInitDenied):
            self.prepare({**self.env, "EDGE_PERMANENT_STORAGE_INIT_ALLOWED": "false"})
        with self.assertRaises(init.PrivateStorageInitDenied):
            self.prepare({**self.env, "EDGE_SHARED_TENANT_DB_PREPARE": "false"})
        self.assertFalse(self.tenant.exists())

    def test_rejects_unsafe_or_unrecognized_owner_without_changes(self):
        os.chmod(self.owner, 0o644)
        with self.assertRaises(init.PrivateStorageInitDenied):
            self.prepare()
        os.chmod(self.owner, 0o600)
        with sqlite3.connect(self.owner) as db:
            db.execute("DROP TABLE broker_credentials")
        with self.assertRaises(init.PrivateStorageInitDenied):
            self.prepare()
        self.assertFalse(self.tenant.exists())

    def test_rejects_existing_symlink_and_hardlink(self):
        self.tenant.symlink_to(self.owner)
        with self.assertRaises(init.PrivateStorageInitDenied):
            self.prepare()
        self.tenant.unlink()
        self.tenant.hardlink_to(self.owner)
        with self.assertRaises(init.PrivateStorageInitDenied):
            self.prepare()
        self.tenant.unlink()
        self.assertFalse(self.tenant.exists())

    def test_partial_schema_error_cleans_private_stage_and_preserves_owner(self):
        before = self.owner.read_bytes()
        with mock.patch.object(init.identity_auth, "setup", side_effect=sqlite3.DatabaseError):
            with self.assertRaises(init.PrivateStorageInitDenied):
                self.prepare()
        self.assertFalse(self.tenant.exists())
        self.assertFalse(list(self.root.glob(".edgepilot-tenant-stage-*")))
        self.assertEqual(self.owner.read_bytes(), before)

    def test_stage_diagnostics_are_sanitized_and_staging_is_removed(self):
        # Trigger the same generic failure path seen in production, without
        # relying on unknown SQL/OS errors being safe to display.
        secret = "SYNTHETIC-DO-NOT-LOG-BROKER-CIPHERTEXT"
        for phase, target, side_effect in [
            ("TENANT_SCHEMA_CREATE", init.tenant_foundation, OSError(secret)),
            ("IDENTITY_SCHEMA_CREATE", init.identity_auth, sqlite3.DatabaseError(secret)),
        ]:
            with self.subTest(phase=phase):
                with mock.patch.object(target, "setup", side_effect=side_effect):
                    with self.assertRaises(init.PrivateStorageInitDenied) as caught:
                        self.prepare()
                self.assertEqual(str(caught.exception),
                                 "PRIVATE_STORAGE_BLOCKED_AT_" + phase)
                self.assertNotIn(secret, str(caught.exception))
                self.assertFalse(self.tenant.exists())
                self.assertFalse(list(self.root.glob(".edgepilot-tenant-stage-*")))
        with mock.patch.object(init.os, "link", side_effect=OSError(secret)):
            with self.assertRaises(init.PrivateStorageInitDenied) as caught:
                self.prepare()
        self.assertEqual(str(caught.exception),
                         "PRIVATE_STORAGE_BLOCKED_AT_NO_REPLACE_PUBLISH")
        self.assertNotIn(secret, str(caught.exception))
        self.assertFalse(self.tenant.exists())
        self.assertFalse(list(self.root.glob(".edgepilot-tenant-stage-*")))

    def test_exclusive_publish_race_cannot_replace_existing_file(self):
        before = self.owner.read_bytes()
        with mock.patch.object(init.os, "link", side_effect=FileExistsError):
            with self.assertRaises(init.PrivateStorageInitDenied):
                self.prepare()
        self.assertFalse(self.tenant.exists())
        self.assertFalse(list(self.root.glob(".edgepilot-tenant-stage-*")))
        self.assertEqual(self.owner.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
