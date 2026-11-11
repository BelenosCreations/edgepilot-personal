"""v0.2.65: owner readiness audit, no secret reads or SQL writes."""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from engine import identity_auth, tenant_foundation
from engine import permanent_owner_readiness as readiness


class OwnerReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.legacy = self.root / "edgepilot.db"
        self.tenant = self.root / "edgepilot-tenants.db"
        with sqlite3.connect(self.legacy) as db:
            db.execute("CREATE TABLE settings (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
            db.execute("CREATE TABLE broker_credentials (provider TEXT PRIMARY KEY, ciphertext BLOB)")
            db.execute("CREATE TABLE orders (id TEXT)")
            db.execute("CREATE TABLE activity (id INTEGER)")
            db.execute("INSERT INTO broker_credentials VALUES ('public',?)",
                       (b'SYNTHETIC-OWNER-CIPHERTEXT',))
        tenant_foundation.setup(str(self.tenant))
        identity_auth.setup(str(self.tenant))
        os.chmod(self.legacy, 0o600)
        os.chmod(self.tenant, 0o600)
        self.env = {
            "EDGE_OWNER_READINESS_AUDIT_ALLOWED": "true",
            "EDGE_SHARED_TENANT_DB_PREPARE": "true",
            "EDGE_TENANT_SCHEMA_PREPARE": "true",
            "EDGE_TENANT_DB_PATH": str(self.tenant),
            "EDGE_AUTOMATION_WORKER_ENABLED": "false",
            "ENABLE_LIVE_ORDERS": "false",
        }

    def audit(self, env=None):
        return readiness.inspect_owner_readiness(
            self.env if env is None else env, self.legacy, self.tenant,
            persistent_root=self.root)

    def test_empty_separate_db_reports_only_manual_bootstrap_stage(self):
        old = self.legacy.read_bytes()
        ten = self.tenant.read_bytes()
        status = self.audit()
        self.assertFalse(status["tenant_owner_initialized"])
        self.assertEqual(status["next_operator_stage"], "manual_first_owner_bootstrap")
        self.assertFalse(status["authorized_to_activate"])
        self.assertEqual(old, self.legacy.read_bytes())
        self.assertEqual(ten, self.tenant.read_bytes())
        self.assertNotIn("SYNTHETIC-OWNER-CIPHERTEXT", json.dumps(status))

    def test_one_real_synthetic_owner_reports_login_still_unverified(self):
        owner = tenant_foundation.TenantStore(str(self.tenant)).provision_user(
            "Example Owner", role="owner")
        identity_auth.IdentityStore(str(self.tenant)).provision(
            owner, "synthetic-owner", "long-enough-synthetic-private-password")
        status = self.audit()
        self.assertTrue(status["tenant_owner_initialized"])
        self.assertTrue(status["tenant_owner_has_password_identity"])
        self.assertEqual(status["tenant_member_count"], 1)
        self.assertEqual(status["next_operator_stage"], "manual_owner_identity_login_test")
        self.assertFalse(status["independent_owner_login_verified"])
        self.assertFalse(status["authorized_to_activate"])
        for secret in ("synthetic-owner", "Example Owner", "long-enough-synthetic-private-password"):
            self.assertNotIn(secret, json.dumps(status))

    def test_owner_and_multiple_members_remain_accountable_and_aggregate_only(self):
        store = tenant_foundation.TenantStore(str(self.tenant))
        ids = [store.provision_user("Owner", role="owner"),
               store.provision_user("Person 1", role="member"),
               store.provision_user("Person 2", role="member")]
        auth = identity_auth.IdentityStore(str(self.tenant))
        for i, uid in enumerate(ids):
            auth.provision(uid, "example-"+str(i), "long-enough-synthetic-private-password")
        result = self.audit()
        self.assertEqual(result["tenant_member_count"], 3)
        self.assertTrue(result["tenant_owner_initialized"])
        self.assertFalse(result["second_physical_device_verified"])

    def test_partial_unpaired_owner_or_member_is_denied(self):
        owner = tenant_foundation.TenantStore(str(self.tenant)).provision_user(
            "Orphan", role="owner")
        with self.assertRaises(readiness.OwnerReadinessDenied):
            self.audit()
        identity_auth.IdentityStore(str(self.tenant)).provision(
            owner, "synthetic-owner", "long-enough-synthetic-private-password")
        tenant_foundation.TenantStore(str(self.tenant)).provision_user(
            "Unpaired", role="member")
        with self.assertRaises(readiness.OwnerReadinessDenied):
            self.audit()

    def test_duplicate_owners_denied(self):
        store = tenant_foundation.TenantStore(str(self.tenant))
        ids = [store.provision_user("Owner One", role="owner"),
               store.provision_user("Owner Two", role="owner")]
        auth = identity_auth.IdentityStore(str(self.tenant))
        for idx, uid in enumerate(ids):
            auth.provision(uid, "owner-"+str(idx), "long-enough-synthetic-private-password")
        with self.assertRaises(readiness.OwnerReadinessDenied):
            self.audit()

    def test_flags_and_unsafe_paths_denied_without_mutation(self):
        for flag in readiness.DORMANT_FLAGS:
            with self.subTest(flag=flag):
                with self.assertRaises(readiness.OwnerReadinessDenied):
                    self.audit({**self.env, flag: "true"})
        for key in ("EDGE_OWNER_READINESS_AUDIT_ALLOWED",
                    "EDGE_SHARED_TENANT_DB_PREPARE", "EDGE_TENANT_SCHEMA_PREPARE"):
            with self.subTest(flag=key):
                with self.assertRaises(readiness.OwnerReadinessDenied):
                    self.audit({**self.env, key: "false"})
        before = self.legacy.read_bytes()
        os.chmod(self.tenant, 0o644)
        with self.assertRaises(readiness.OwnerReadinessDenied):
            self.audit()
        os.chmod(self.tenant, 0o600)
        self.tenant.unlink()
        self.tenant.symlink_to(self.legacy)
        with self.assertRaises(readiness.OwnerReadinessDenied):
            self.audit()
        self.assertEqual(self.legacy.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
