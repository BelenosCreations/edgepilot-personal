"""v0.2.59: permanent tenant-only retirement switch and pinned app passkey origin."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from engine import shared_storage_cutover


CERT = ":".join(["A1"] * 32)
RP = "edgepilot.belenoscreations.biz"


class PermanentIdentityPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.legacy = self.root / "edgepilot.db"
        self.tenant = self.root / "edgepilot-tenants.db"
        with sqlite3.connect(self.legacy) as db:
            db.execute("CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT NOT NULL)")
            db.execute("INSERT INTO settings VALUES('account_id','OWNER-LEGACY')")
            db.execute("""CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY,
                ciphertext BLOB, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            db.execute("INSERT INTO broker_credentials(provider,ciphertext) VALUES('public',?)",
                       (b'SYNTHETIC-OWNER-CIPHERTEXT',))
        self.env = {
            "EDGE_SHARED_TENANT_DB_PREPARE": "true",
            "EDGE_TENANT_SCHEMA_PREPARE": "true",
            "EDGE_TENANT_DB_PATH": str(self.tenant),
            "EDGE_PERMANENT_TENANTS_ONLY": "true",
            "EDGE_PERMANENT_ANDROID_PASSKEY_ORIGIN_ENABLED": "true",
            "EDGE_IDENTITY_AUTH_ENABLED": "true",
            "EDGE_TENANT_PASSKEYS_ENABLED": "true",
            "EDGE_ISOLATED_STAGING": "false",
            "EDGE_AUTOMATION_WORKER_ENABLED": "false",
            "ENABLE_LIVE_ORDERS": "false",
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED": "false",
            "EDGE_TENANT_PUBLIC_READONLY_ENABLED": "false",
            "EDGE_TENANT_ACCOUNT_READS_ENABLED": "false",
            "EDGE_WEBAUTHN_RP_ID": RP,
            "EDGE_WEBAUTHN_ORIGIN": "https://" + RP,
            "EDGE_ANDROID_ASSOCIATION_PACKAGE": "",
            "EDGE_ANDROID_CERT_SHA256": CERT,
        }

    def policy(self, env=None, same_db=False):
        return shared_storage_cutover.permanent_identity_policy(
            self.env if env is None else env, self.legacy,
            self.legacy if same_db else self.tenant)

    def test_disabled_defaults_preserve_owner_routes(self):
        self.assertEqual(self.policy({}),
                         {"tenant_only": False, "android_signer_sha256": None})

    def test_explicitly_pinned_production_origin(self):
        result = self.policy()
        self.assertTrue(result["tenant_only"])
        self.assertEqual(result["android_signer_sha256"], CERT)
        self.assertEqual(self.policy({**self.env,
            "EDGE_PERMANENT_ANDROID_PASSKEY_ORIGIN_ENABLED": "false"}),
            {"tenant_only": True, "android_signer_sha256": None})

    def test_rejects_unsafe_retirement_or_unpinned_app_origin(self):
        cases = [
            ("EDGE_SHARED_TENANT_DB_PREPARE","false"),
            ("EDGE_TENANT_SCHEMA_PREPARE","false"),
            ("EDGE_IDENTITY_AUTH_ENABLED","false"),
            ("EDGE_ISOLATED_STAGING","true"),
            ("EDGE_AUTOMATION_WORKER_ENABLED","true"),
            ("ENABLE_LIVE_ORDERS","true"),
            ("EDGE_PERMANENT_TENANTS_ONLY","false"),
            ("EDGE_TENANT_PASSKEYS_ENABLED","false"),
            ("EDGE_WEBAUTHN_RP_ID","staging-edgepilot.belenoscreations.biz"),
            ("EDGE_WEBAUTHN_ORIGIN","https://evil.example"),
            ("EDGE_ANDROID_ASSOCIATION_PACKAGE","com.edgepilot.mobile.staging"),
            ("EDGE_ANDROID_CERT_SHA256","00:11"),
        ]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                with self.assertRaises(shared_storage_cutover.SharedStorageDenied):
                    self.policy({**self.env, key: value})
        with self.assertRaises(shared_storage_cutover.SharedStorageDenied):
            self.policy(same_db=True)

    def test_real_flask_import_blocks_legacy_owner_api_without_destroying_data(self):
        script = """
import json, sqlite3, sys
from pathlib import Path
from engine import shared_storage_cutover
shared_storage_cutover.PERSISTENT_ROOT = Path(sys.argv[1])
import app
assert app.TENANT_POLICY['tenant_only']
assert app.DB != app.TENANT_DB
assert app.tenant_passkey_store is not None
assert len(app.tenant_passkey_store.allowed_origins) == 2
assert app.tenant_passkey_store.allowed_origins[0] == 'https://edgepilot.belenoscreations.biz'
assert app.tenant_passkey_store.allowed_origins[1].startswith('android:apk-key-hash:')
client = app.app.test_client()
assert client.get('/').status_code == 302
assert client.get('/').headers['Location'] == '/account'
assert client.get('/api/session').status_code == 404
assert client.get('/api/settings').status_code == 404
assert client.get('/api/automation/status').status_code == 404
assert client.get('/api/identity/session').status_code == 401
assert client.get('/healthz').status_code == 200
with sqlite3.connect(app.DB) as db:
    assert db.execute("SELECT ciphertext FROM broker_credentials WHERE provider='public'").fetchone()[0] == b'SYNTHETIC-OWNER-CIPHERTEXT'
    assert db.execute("SELECT name FROM sqlite_master WHERE name='tenant_passkey_credentials'").fetchone() is None
with sqlite3.connect(app.TENANT_DB) as db:
    assert db.execute("SELECT name FROM sqlite_master WHERE name='tenant_passkey_credentials'").fetchone()
    assert db.execute("SELECT name FROM sqlite_master WHERE name='broker_credentials'").fetchone() is None
print(json.dumps({"tenantOnly": True, "preserved": True}))
"""
        env = os.environ.copy()
        env.update(self.env)
        env.update({
            "EDGE_DB_PATH": str(self.legacy),
            "EDGE_APP_TOKEN": "",
            "PUBLIC_API_SECRET": "",
            "EDGE_CREDENTIAL_KEY": "",
            "EDGE_STAGING_OPERATOR_SHA256": "",
            "EDGE_TENANT_SIGNUP_ENABLED": "false",
        })
        run = subprocess.run(
            [sys.executable, "-c", script, str(self.root)],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env, capture_output=True, text=True, timeout=35)
        self.assertEqual(run.returncode, 0, run.stderr[-1600:])
        self.assertTrue(json.loads(run.stdout.strip().splitlines()[-1])["tenantOnly"])


if __name__ == "__main__":
    unittest.main()
