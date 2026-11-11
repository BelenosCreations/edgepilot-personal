"""v0.2.58: one paid disk, two isolated SQLite files, no migration or orders."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from engine import shared_storage_cutover as cutover, tenant_foundation


class SharedStorageCutoverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.legacy = self.root / "edgepilot.db"
        self.tenant = self.root / "edgepilot-tenants.db"
        with sqlite3.connect(self.legacy) as con:
            con.execute("CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT NOT NULL)")
            con.execute("INSERT INTO settings VALUES('account_id','OWNER-PRIVATE-ID')")
            con.execute("""CREATE TABLE broker_credentials(
                provider TEXT PRIMARY KEY, ciphertext BLOB,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            con.execute("INSERT INTO broker_credentials(provider,ciphertext) VALUES('public',?)",
                        (b'FAKE-ENCRYPTED-OWNER-BYTES',))
        self.env = {
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

    def select(self, env=None):
        return cutover.select_tenant_database(
            self.env if env is None else env, self.legacy,
            persistent_root=self.root)

    def test_no_flags_does_not_touch_any_file(self):
        self.assertEqual(
            cutover.select_tenant_database({}, self.legacy,
                                           persistent_root=self.root), self.legacy)
        self.assertFalse(self.tenant.exists())

    def test_create_private_and_restart_preserves_legacy_owner(self):
        self.assertEqual(self.select(), self.tenant)
        selected = cutover.ensure_private_tenant_file(self.tenant,
                                                      persistent_root=self.root)
        self.assertEqual(selected, self.tenant)
        self.assertEqual(self.tenant.stat().st_mode & 0o777, 0o600)
        tenant_foundation.setup(self.tenant)
        store = tenant_foundation.TenantStore(self.tenant)
        alice = store.provision_user("Alice")
        bob = store.provision_user("Bob")
        self.assertNotEqual(alice, bob)
        self.assertEqual(cutover.ensure_private_tenant_file(
            self.tenant, persistent_root=self.root), self.tenant)
        with sqlite3.connect(self.legacy) as db:
            self.assertEqual(db.execute(
                "SELECT v FROM settings WHERE k='account_id'").fetchone()[0],
                "OWNER-PRIVATE-ID")
            self.assertEqual(db.execute(
                "SELECT ciphertext FROM broker_credentials WHERE provider='public'"
            ).fetchone()[0], b'FAKE-ENCRYPTED-OWNER-BYTES')
            self.assertIsNone(db.execute(
                "SELECT name FROM sqlite_master WHERE name='tenant_users'").fetchone())
        with sqlite3.connect(self.tenant) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tenant_users").fetchone()[0], 2)
            self.assertIsNone(db.execute(
                "SELECT name FROM sqlite_master WHERE name='broker_credentials'").fetchone())

    def test_missing_gate_or_unsafe_feature_denied(self):
        for key, value in [
            ("EDGE_SHARED_TENANT_DB_PREPARE", "false"),
            ("EDGE_TENANT_SCHEMA_PREPARE", "false"),
            ("EDGE_ISOLATED_STAGING", "true"),
            ("EDGE_AUTOMATION_WORKER_ENABLED", "true"),
            ("ENABLE_LIVE_ORDERS", "true"),
            ("EDGE_TENANT_PUBLIC_VAULT_ENABLED", "true"),
            ("EDGE_TENANT_PUBLIC_READONLY_ENABLED", "true"),
            ("EDGE_TENANT_ACCOUNT_READS_ENABLED", "true"),
            ("EDGE_TENANT_MONITOR_PREVIEW_ENABLED", "true"),
            ("EDGE_TENANT_WATCHLIST_EDIT_ENABLED", "true"),
            ("EDGE_SHARED_TENANT_DB_PREPARE", "trueish"),
        ]:
            with self.subTest(key=key, value=value):
                with self.assertRaises(cutover.SharedStorageDenied):
                    self.select({**self.env, key: value})
        with self.assertRaises(cutover.SharedStorageDenied):
            self.select({**self.env, "EDGE_TENANT_DB_PATH": ""})
        with self.assertRaises(cutover.SharedStorageDenied):
            self.select({**self.env, "EDGE_TENANT_DB_PATH": str(self.root / "other.db")})

    def test_absent_legacy_and_hardlink_symlink_paths_denied(self):
        alias = self.root / "edgepilot.db"
        alias.unlink()
        with self.assertRaises(cutover.SharedStorageDenied):
            self.select()
        alias.symlink_to(self.root / "missing.db")
        with self.assertRaises(cutover.SharedStorageDenied):
            self.select()
        alias.unlink()
        alias.touch()
        self.tenant.hardlink_to(alias)
        with self.assertRaises(cutover.SharedStorageDenied):
            self.select()
        self.tenant.unlink()
        self.tenant.symlink_to(alias)
        with self.assertRaises(cutover.SharedStorageDenied):
            self.select()

    def test_existing_public_file_and_foreign_database_refused(self):
        self.tenant.touch(mode=0o644)
        os.chmod(self.tenant, 0o644)
        with self.assertRaises(cutover.SharedStorageDenied):
            cutover.ensure_private_tenant_file(self.tenant, persistent_root=self.root)
        os.chmod(self.tenant, 0o600)
        with sqlite3.connect(self.tenant) as db:
            db.execute("CREATE TABLE unexpected(secret TEXT)")
        with self.assertRaises(cutover.SharedStorageDenied):
            cutover.ensure_private_tenant_file(self.tenant, persistent_root=self.root)

    def test_flask_startup_routes_tenant_stores_to_second_file(self):
        # Real backend import/startup in a subprocess: no network, broker calls,
        # real account secrets, worker, or production /data access.
        script = """
import json, sqlite3, sys
from pathlib import Path
from engine import shared_storage_cutover
shared_storage_cutover.PERSISTENT_ROOT = Path(sys.argv[1])
import app
assert app.DB != app.TENANT_DB
assert app.identity_store.path == str(app.TENANT_DB)
user = app.tenant_foundation.TenantStore(str(app.TENANT_DB)).provision_user('Alice')
app.identity_store.provision(user, 'alice', 'this is a long dummy password')
with sqlite3.connect(app.DB) as c:
    old = c.execute("SELECT ciphertext FROM broker_credentials WHERE provider='public'").fetchone()[0]
    assert old == b'FAKE-ENCRYPTED-OWNER-BYTES'
    assert c.execute("SELECT name FROM sqlite_master WHERE name='tenant_identities'").fetchone() is None
with sqlite3.connect(app.TENANT_DB) as c:
    assert c.execute("SELECT COUNT(*) FROM tenant_identities").fetchone()[0] == 1
    assert c.execute("SELECT name FROM sqlite_master WHERE name='broker_credentials'").fetchone() is None
print(json.dumps({"separate": True, "legacy_credential_preserved": True}))
"""
        env = os.environ.copy()
        env.update(self.env)
        env.update({
            "EDGE_DB_PATH": str(self.legacy),
            "EDGE_IDENTITY_AUTH_ENABLED": "true",
            "EDGE_APP_TOKEN": "",
            "PUBLIC_API_SECRET": "",
            "EDGE_CREDENTIAL_KEY": "",
            "EDGE_STAGING_OPERATOR_SHA256": "",
            "EDGE_TENANT_SIGNUP_ENABLED": "false",
            "EDGE_TENANT_PASSKEYS_ENABLED": "false",
        })
        run = subprocess.run(
            [sys.executable, "-c", script, str(self.root)],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env, capture_output=True, text=True, timeout=35)
        self.assertEqual(run.returncode, 0, run.stderr[-1500:])
        self.assertTrue(json.loads(run.stdout.strip().splitlines()[-1])["separate"])


if __name__ == "__main__":
    unittest.main()
