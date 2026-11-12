"""v0.2.71 synthetic owner password verification with zero sessions/writes."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from engine import identity_auth, tenant_foundation
from engine import permanent_owner_password_proof as proof


class OwnerPasswordProofTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.legacy = self.root/"edgepilot.db"
        self.tenant = self.root/"edgepilot-tenants.db"
        with sqlite3.connect(self.legacy) as db:
            db.execute("CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT NOT NULL)")
            db.execute("CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY,ciphertext BLOB)")
            db.execute("CREATE TABLE orders(id TEXT)")
            db.execute("CREATE TABLE activity(id INTEGER)")
            db.execute("INSERT INTO broker_credentials VALUES('public',?)",
                       (b"DO-NOT-LOG-LEGACY-SECRET",))
        tenant_foundation.setup(str(self.tenant))
        identity_auth.setup(str(self.tenant))
        self.owner = tenant_foundation.TenantStore(str(self.tenant)).provision_user(
            "Synthetic first owner", role="owner")
        self.secret = "synthetic-owner-password-that-is-private-2026"
        identity_auth.IdentityStore(str(self.tenant)).provision(
            self.owner, "synthetic-owner", self.secret)
        os.chmod(self.legacy, 0o600)
        os.chmod(self.tenant, 0o600)
        self.env = {
            "EDGE_OWNER_PASSWORD_PROOF_ALLOWED": "true",
            "EDGE_SHARED_TENANT_DB_PREPARE": "true",
            "EDGE_TENANT_SCHEMA_PREPARE": "true",
            "EDGE_TENANT_DB_PATH": str(self.tenant),
            "EDGE_IDENTITY_AUTH_ENABLED": "false",
            "EDGE_AUTOMATION_WORKER_ENABLED": "false",
            "ENABLE_LIVE_ORDERS": "false",
        }

    def run_proof(self, password=None, env=None):
        return proof.prove_first_owner_password(
            self.env if env is None else env, self.legacy, self.tenant,
            self.secret if password is None else password,
            persistent_root=self.root)

    def test_correct_password_read_only_no_sessions_and_no_secret_output(self):
        before_owner = self.tenant.read_bytes()
        before_legacy = self.legacy.read_bytes()
        result = self.run_proof()
        self.assertTrue(result["first_owner_password_verified"])
        self.assertFalse(result["independent_http_login_verified"])
        self.assertFalse(result["identity_sessions_created"])
        self.assertFalse(result["authorized_to_activate"])
        self.assertNotIn(self.secret, str(result))
        self.assertNotIn("synthetic-owner", str(result))
        self.assertEqual(self.tenant.read_bytes(), before_owner)
        self.assertEqual(self.legacy.read_bytes(), before_legacy)
        with sqlite3.connect(self.tenant) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM tenant_identity_sessions").fetchone()[0], 0)

    def test_wrong_password_rejected_without_change(self):
        before = self.tenant.read_bytes()
        result = self.run_proof("completely-incorrect-password-2026")
        self.assertFalse(result["first_owner_password_verified"])
        self.assertEqual(self.tenant.read_bytes(), before)

    def test_missing_approval_and_active_identity_routes_refused(self):
        for key, value in [("EDGE_OWNER_PASSWORD_PROOF_ALLOWED","false"),
                           ("EDGE_IDENTITY_AUTH_ENABLED","true"),
                           ("EDGE_AUTOMATION_WORKER_ENABLED","true"),
                           ("EDGE_PERMANENT_TENANTS_ONLY","true"),
                           ("EDGE_TENANT_PUBLIC_VAULT_ENABLED","true")]:
            with self.subTest(key=key):
                with self.assertRaises(proof.OwnerPasswordProofDenied):
                    self.run_proof(env={**self.env,key:value})

    def test_unpaired_owner_duplicate_member_and_unsafe_file_refused(self):
        with sqlite3.connect(self.tenant) as db:
            db.execute("DELETE FROM tenant_identities")
        with self.assertRaises(proof.OwnerPasswordProofDenied):
            self.run_proof()
        identity_auth.IdentityStore(str(self.tenant)).provision(
            self.owner, "synthetic-owner", self.secret)
        tenant_foundation.TenantStore(str(self.tenant)).provision_user(
            "Unpaired", role="member")
        with self.assertRaises(proof.OwnerPasswordProofDenied):
            self.run_proof()
        os.chmod(self.tenant, 0o644)
        with self.assertRaises(proof.OwnerPasswordProofDenied):
            self.run_proof()


if __name__ == "__main__":
    unittest.main()
