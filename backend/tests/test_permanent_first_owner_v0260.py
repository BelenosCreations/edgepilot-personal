"""v0.2.60 one-time offline owner identity proof, zero real provider actions."""
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from engine import identity_auth, permanent_owner_bootstrap as bootstrap
from engine import shared_storage_cutover, tenant_foundation

PASSWORD="long-fixture-password-with-no-real-account-data"
APPROVAL=bootstrap.APPROVAL


class FirstPermanentOwnerBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.legacy=self.root/"edgepilot.db"
        self.tenant=self.root/"edgepilot-tenants.db"
        with sqlite3.connect(self.legacy) as db:
            db.execute("CREATE TABLE settings(k TEXT PRIMARY KEY, v TEXT NOT NULL)")
            db.execute("INSERT INTO settings VALUES('account_id','UNMIGRATED-OWNER-ID')")
            db.execute("""CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY,
                ciphertext BLOB, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            db.execute("INSERT INTO broker_credentials(provider,ciphertext) VALUES('public',?)",
                       (b'PREEXISTING-SYNTHETIC-ENCRYPTED-DATA',))
        self.env={
            "EDGE_DB_PATH":str(self.legacy),
            "EDGE_TENANT_DB_PATH":str(self.tenant),
            "EDGE_SHARED_TENANT_DB_PREPARE":"true",
            "EDGE_TENANT_SCHEMA_PREPARE":"true",
            "EDGE_IDENTITY_AUTH_ENABLED":"true",
            "EDGE_OWNER_BOOTSTRAP_ALLOWED":"true",
            "EDGE_TENANT_SIGNUP_ENABLED":"false",
            "EDGE_PERMANENT_TENANTS_ONLY":"false",
            "EDGE_ISOLATED_STAGING":"false",
            "EDGE_AUTOMATION_WORKER_ENABLED":"false",
            "ENABLE_LIVE_ORDERS":"false",
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED":"false",
            "EDGE_TENANT_PUBLIC_READONLY_ENABLED":"false",
            "EDGE_TENANT_ACCOUNT_READS_ENABLED":"false",
        }
        self.assertEqual(shared_storage_cutover.select_tenant_database(
            self.env,self.legacy,persistent_root=self.root),self.tenant)
        shared_storage_cutover.ensure_private_tenant_file(
            self.tenant,persistent_root=self.root)
        tenant_foundation.setup(self.tenant)
        identity_auth.setup(self.tenant)

    def create(self, env=None, *, approval=APPROVAL, label="Initial Owner",
               login="edge-owner", password=PASSWORD):
        return bootstrap.create_first_owner(
            self.env if env is None else env, self.legacy,self.tenant,
            label=label,login_name=login,password=password,approval=approval,
            persistent_root=self.root)

    def test_create_once_and_preserve_unmigrated_owner_data(self):
        created=self.create()
        self.assertEqual(created,{"created":True,"role":"owner",
            "legacyDataMigrated":False,"brokerConnected":False,
            "tradingEnabled":False,"fundTransfersEnabled":False})
        with sqlite3.connect(self.legacy) as db:
            self.assertEqual(db.execute("SELECT v FROM settings WHERE k='account_id'")
                             .fetchone()[0],"UNMIGRATED-OWNER-ID")
            self.assertEqual(db.execute(
                "SELECT ciphertext FROM broker_credentials WHERE provider='public'"
            ).fetchone()[0],b'PREEXISTING-SYNTHETIC-ENCRYPTED-DATA')
            self.assertIsNone(db.execute(
                "SELECT name FROM sqlite_master WHERE name='tenant_users'").fetchone())
        with sqlite3.connect(self.tenant) as db:
            self.assertEqual(db.execute(
                "SELECT role FROM tenant_users").fetchone()[0],"owner")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tenant_identities")
                             .fetchone()[0],1)
            self.assertEqual(db.execute(
                "SELECT action FROM tenant_audit_events").fetchone()[0],
                "USER_PROVISIONED")
            self.assertNotEqual(db.execute(
                "SELECT password_hash FROM tenant_identities").fetchone()[0],PASSWORD)
            self.assertIsNone(db.execute(
                "SELECT name FROM sqlite_master WHERE name='broker_credentials'").fetchone())
        self.assertTrue(identity_auth.IdentityStore(str(self.tenant)).authenticate(
            "edge-owner",PASSWORD,source="local-test"))
        with self.assertRaises(bootstrap.OwnerBootstrapDenied):
            self.create(login="second-owner")
        with sqlite3.connect(self.tenant) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tenant_users")
                             .fetchone()[0],1)

    def test_fail_closed_on_missing_authorization_or_unsafe_flags(self):
        cases=[
            ("EDGE_OWNER_BOOTSTRAP_ALLOWED","false"),
            ("EDGE_SHARED_TENANT_DB_PREPARE","false"),
            ("EDGE_TENANT_SCHEMA_PREPARE","false"),
            ("EDGE_IDENTITY_AUTH_ENABLED","false"),
            ("EDGE_TENANT_SIGNUP_ENABLED","true"),
            ("EDGE_PERMANENT_TENANTS_ONLY","true"),
            ("EDGE_ISOLATED_STAGING","true"),
            ("EDGE_AUTOMATION_WORKER_ENABLED","true"),
            ("ENABLE_LIVE_ORDERS","true"),
            ("EDGE_TENANT_PUBLIC_VAULT_ENABLED","true"),
            ("EDGE_TENANT_PUBLIC_READONLY_ENABLED","true"),
            ("EDGE_TENANT_ACCOUNT_READS_ENABLED","true"),
        ]
        for key,value in cases:
            with self.subTest(key=key,value=value):
                with self.assertRaises(bootstrap.OwnerBootstrapDenied):
                    self.create({**self.env,key:value})
        with self.assertRaises(bootstrap.OwnerBootstrapDenied):
            self.create(approval="NO")
        with self.assertRaises(bootstrap.OwnerBootstrapDenied):
            self.create(password="short")
        with self.assertRaises(bootstrap.OwnerBootstrapDenied):
            self.create(login="invalid username")
        with sqlite3.connect(self.tenant) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tenant_users").fetchone()[0],0)

    def test_existing_members_or_symlink_private_file_blocked(self):
        tenant_foundation.TenantStore(str(self.tenant)).provision_user("Existing")
        with self.assertRaises(bootstrap.OwnerBootstrapDenied):
            self.create()
        with sqlite3.connect(self.tenant) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tenant_users").fetchone()[0],1)
        self.tenant.unlink()
        self.tenant.symlink_to(self.legacy)
        with self.assertRaises(bootstrap.OwnerBootstrapDenied):
            self.create()

    def test_missing_identity_schema_and_unprotected_permissions_blocked(self):
        with sqlite3.connect(self.tenant) as db:
            db.execute("DROP TABLE tenant_identities")
        with self.assertRaises(bootstrap.OwnerBootstrapDenied):
            self.create()
        os.chmod(self.tenant,0o644)
        with self.assertRaises(bootstrap.OwnerBootstrapDenied):
            self.create()

    def test_racing_bootstrap_requests_serialize_to_one_owner(self):
        def attempt(_):
            try:
                return self.create()
            except bootstrap.OwnerBootstrapDenied:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(attempt,range(2)))
        self.assertEqual(sum(v is not None for v in outcomes),1)
        with sqlite3.connect(self.tenant) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tenant_users").fetchone()[0],1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tenant_identities").fetchone()[0],1)


if __name__=="__main__":
    unittest.main()
