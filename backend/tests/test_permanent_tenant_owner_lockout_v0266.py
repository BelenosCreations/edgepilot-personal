"""v0.2.66: prevent legacy-owner lockout by missing tenant owner at startup."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from engine import identity_auth, tenant_foundation
from engine import shared_storage_cutover as storage


class TenantOnlyOwnerLockoutGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.legacy=self.root/"edgepilot.db"
        self.tenant=self.root/"edgepilot-tenants.db"
        with sqlite3.connect(self.legacy) as db:
            db.execute("CREATE TABLE settings(k TEXT PRIMARY KEY, v TEXT NOT NULL)")
            db.execute("CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY,ciphertext BLOB)")
            db.execute("INSERT INTO broker_credentials VALUES ('public',?)", (b'SYNTHETIC-LEGACY-SECRET',))
        self.env={
            "EDGE_SHARED_TENANT_DB_PREPARE":"true",
            "EDGE_TENANT_SCHEMA_PREPARE":"true",
            "EDGE_IDENTITY_AUTH_ENABLED":"true",
            "EDGE_PERMANENT_TENANTS_ONLY":"true",
            "EDGE_ISOLATED_STAGING":"false",
            "EDGE_AUTOMATION_WORKER_ENABLED":"false",
            "ENABLE_LIVE_ORDERS":"false",
        }

    def policy(self):
        return storage.permanent_identity_policy(self.env,self.legacy,self.tenant)

    def prepare(self):
        tenant_foundation.setup(str(self.tenant))
        identity_auth.setup(str(self.tenant))
        os.chmod(self.tenant,0o600)

    def create_owner(self):
        owner=tenant_foundation.TenantStore(str(self.tenant)).provision_user(
            "Synthetic Original Owner",role="owner")
        identity_auth.IdentityStore(str(self.tenant)).provision(
            owner,"original-owner","synthetic-owner-unique-password-2026")
        return owner

    def test_default_unset_leaves_original_owner_route_unchanged(self):
        self.assertEqual(storage.permanent_identity_policy(
            {},self.legacy,self.tenant),
            {"tenant_only":False,"android_signer_sha256":None})
        self.assertFalse(self.tenant.exists())

    def test_no_tenant_file_and_empty_tenant_db_refuse_cutover(self):
        before=self.legacy.read_bytes()
        with self.assertRaises(storage.SharedStorageDenied):
            self.policy()
        self.prepare()
        with self.assertRaises(storage.SharedStorageDenied):
            self.policy()
        self.assertEqual(self.legacy.read_bytes(),before)

    def test_bootstrap_owner_pair_allows_policy_but_not_brokerage_or_trade(self):
        self.prepare()
        self.create_owner()
        before=self.tenant.read_bytes()
        result=self.policy()
        self.assertTrue(result["tenant_only"])
        self.assertIsNone(result["android_signer_sha256"])
        self.assertEqual(self.tenant.read_bytes(),before)
        self.assertNotIn(b"SYNTHETIC-LEGACY-SECRET",self.tenant.read_bytes())
        self.assertFalse(any(key in result for key in ("broker", "trading", "transfer")))

    def test_orphan_owner_and_duplicate_owner_are_denied(self):
        self.prepare()
        tenant_foundation.TenantStore(str(self.tenant)).provision_user(
            "Missing Identity",role="owner")
        with self.assertRaises(storage.SharedStorageDenied):
            self.policy()
        # A complete new second owner is not a valid substitute for
        # manually resolving the malformed first owner.
        self.create_owner()
        with self.assertRaises(storage.SharedStorageDenied):
            self.policy()

    def test_unpaired_member_blocks_retirement(self):
        self.prepare()
        self.create_owner()
        tenant_foundation.TenantStore(str(self.tenant)).provision_user(
            "Half Created",role="member")
        with self.assertRaises(storage.SharedStorageDenied):
            self.policy()

    def test_insecure_tenant_permissions_and_links_denied(self):
        self.prepare()
        self.create_owner()
        os.chmod(self.tenant,0o644)
        with self.assertRaises(storage.SharedStorageDenied):
            self.policy()
        os.chmod(self.tenant,0o600)
        self.tenant.unlink()
        self.tenant.symlink_to(self.legacy)
        with self.assertRaises(storage.SharedStorageDenied):
            self.policy()

    def test_disabled_owner_blocks_retirement(self):
        self.prepare()
        owner=self.create_owner()
        with sqlite3.connect(self.tenant) as db:
            db.execute("UPDATE tenant_users SET disabled_at=? WHERE user_id=?",
                       ("synthetic-disabled",owner))
        with self.assertRaises(storage.SharedStorageDenied):
            self.policy()


if __name__=="__main__":
    unittest.main()
