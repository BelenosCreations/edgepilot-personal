"""v0.2.61: safe offline read-only separate-database inspection."""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from engine import identity_auth, tenant_foundation
from engine import permanent_cutover_preflight as preflight


class PermanentCutoverPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.legacy = self.root / "edgepilot.db"
        self.tenant = self.root / "edgepilot-tenants.db"
        with sqlite3.connect(self.legacy) as db:
            db.execute("CREATE TABLE settings(k TEXT PRIMARY KEY, v TEXT NOT NULL)")
            db.execute("INSERT INTO settings VALUES('account_id','OWNER-SECRET')")
            db.execute("CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY, ciphertext BLOB)")
            db.execute("INSERT INTO broker_credentials VALUES('public',?)", (b'ENCRYPTED-SYNTHETIC-SECRET',))
            db.execute("CREATE TABLE orders(id TEXT)")
            db.execute("CREATE TABLE activity(id INTEGER)")
        tenant_foundation.setup(str(self.tenant))
        identity_auth.setup(str(self.tenant))
        os.chmod(self.legacy, 0o600)
        os.chmod(self.tenant, 0o600)
        self.env = {
            "EDGE_CUTOVER_PREFLIGHT_ALLOWED": "true",
            "EDGE_SHARED_TENANT_DB_PREPARE": "true",
            "EDGE_TENANT_SCHEMA_PREPARE": "true",
            "EDGE_TENANT_DB_PATH": str(self.tenant),
            "EDGE_ISOLATED_STAGING": "false",
            "EDGE_AUTOMATION_WORKER_ENABLED": "false",
            "ENABLE_LIVE_ORDERS": "false",
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED": "false",
            "EDGE_TENANT_PUBLIC_READONLY_ENABLED": "false",
            "EDGE_TENANT_ACCOUNT_READS_ENABLED": "false",
        }

    def inspect(self, env=None):
        return preflight.inspect_cutover(
            self.env if env is None else env,
            self.legacy, self.tenant, persistent_root=self.root)

    def test_read_only_pass_preserves_legacy_ciphertext_and_reports_no_authorization(self):
        status = self.inspect()
        self.assertEqual(status["inspection"], "passed")
        self.assertFalse(status["tenant_has_members"])
        self.assertFalse(status["authorized_to_activate"])
        self.assertFalse(status["production_backup_and_restore_verified"])
        self.assertNotIn("SECRET", json.dumps(status))
        with sqlite3.connect(self.legacy) as db:
            self.assertEqual(db.execute("SELECT ciphertext FROM broker_credentials").fetchone()[0],
                             b'ENCRYPTED-SYNTHETIC-SECRET')
            self.assertEqual(db.execute("SELECT v FROM settings").fetchone()[0],
                             'OWNER-SECRET')
        with sqlite3.connect(self.tenant) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tenant_users").fetchone()[0], 0)

    def test_refuses_unapproved_or_unsafe_runtime(self):
        for key, value in [
            ("EDGE_CUTOVER_PREFLIGHT_ALLOWED", "false"),
            ("EDGE_PERMANENT_TENANTS_ONLY", "true"),
            ("EDGE_PERMANENT_ANDROID_PASSKEY_ORIGIN_ENABLED", "true"),
            ("EDGE_AUTOMATION_WORKER_ENABLED", "true"),
            ("ENABLE_LIVE_ORDERS", "true"),
            ("EDGE_TENANT_SIGNUP_ENABLED", "true"),
            ("EDGE_TENANT_PUBLIC_READONLY_ENABLED", "true"),
        ]:
            with self.subTest(key=key):
                with self.assertRaises(preflight.CutoverPreflightDenied):
                    self.inspect({**self.env, key: value})

    def test_refuses_insecure_file_and_unexpected_schema(self):
        os.chmod(self.tenant, 0o644)
        with self.assertRaises(preflight.CutoverPreflightDenied):
            self.inspect()
        os.chmod(self.tenant, 0o600)
        with sqlite3.connect(self.tenant) as db:
            db.execute("CREATE TABLE broker_credentials(secret TEXT)")
        with self.assertRaises(preflight.CutoverPreflightDenied):
            self.inspect()

    def test_refuses_symlinks_and_absent_files_without_creation(self):
        self.tenant.unlink()
        self.tenant.symlink_to(self.legacy)
        with self.assertRaises(preflight.CutoverPreflightDenied):
            self.inspect()
        self.tenant.unlink()
        with self.assertRaises(preflight.CutoverPreflightDenied):
            self.inspect()
        self.assertFalse(self.tenant.exists())


if __name__ == "__main__":
    unittest.main()
