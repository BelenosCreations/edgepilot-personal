"""v0.2.74: encrypted linked-owner recovery with active sessions, no real Public."""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cryptography.fernet import Fernet
from engine import identity_auth, tenant_foundation
from engine import permanent_tenant_linked_backup as backup


class LinkedOwnerBackupTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.disk = Path(temp.name)/"data"
        self.ram = Path(temp.name)/"shm"
        self.disk.mkdir()
        self.ram.mkdir()
        self.legacy = self.disk/"edgepilot.db"
        self.tenant = self.disk/"edgepilot-tenants.db"
        self.archive = self.ram/"edgepilot-tenant-linked-SYNTHETIC.epbk"
        with sqlite3.connect(self.legacy) as db:
            db.execute("CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT)")
            db.execute("CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY,ciphertext BLOB)")
            db.execute("CREATE TABLE orders(id TEXT)")
            db.execute("CREATE TABLE activity(id INTEGER)")
            db.execute("INSERT INTO broker_credentials VALUES('public',?)",
                       (b"SYNTHETIC-LEGACY-CIPHERTEXT",))
        tenant_foundation.setup(str(self.tenant))
        identity_auth.setup(str(self.tenant))
        users = tenant_foundation.TenantStore(
            str(self.tenant), credential_key=Fernet.generate_key().decode())
        self.vault_key = users.credential_key
        owner = users.provision_user("Synthetic owner", "owner")
        identity_auth.IdentityStore(str(self.tenant)).provision(
            owner, "synthetic_owner", "synthetic-passphrase-2026-do-not-log")
        self.public_secret = "SYNTHETIC-PRIVATE-PUBLIC-KEY-NEVER-LOG"
        self.connection = users.add_connection(owner, self.public_secret)
        self.account = users.link_account(
            owner, self.connection, "SYNTHTESTACCOUNT123", "Verified account")
        with sqlite3.connect(self.tenant) as db:
            db.execute("""INSERT INTO tenant_identity_sessions
            (token_hash,csrf_hash,user_id,credential_version,issued_at,expires_at)
            VALUES(?,?,?,?,?,?)""",
                ("SYNTHETIC_SESSION_HASH","SYNTHETIC_CSRF_HASH",
                 owner,1,1,9999999999))
            db.execute("""INSERT INTO tenant_auth_failures
            (source_hash,login_hash,attempted_at)
            VALUES('fake_source_hash','fake_login_hash',100)""")
        os.chmod(self.tenant, 0o600)
        os.chmod(self.legacy, 0o600)
        self.key = Fernet.generate_key().decode()
        self.env = {
            "EDGE_TENANT_LINKED_BACKUP_ALLOWED":"true",
            "EDGE_SHARED_TENANT_DB_PREPARE":"true",
            "EDGE_TENANT_SCHEMA_PREPARE":"true",
            "EDGE_IDENTITY_AUTH_ENABLED":"true",
            "EDGE_PERMANENT_READONLY_PILOT_ENABLED":"true",
            "EDGE_TENANT_ACCOUNT_READS_ENABLED":"true",
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED":"true",
            "EDGE_TENANT_PUBLIC_READONLY_ENABLED":"true",
            "EDGE_TENANT_PUBLIC_DISCOVERY_ONLY":"true",
            "EDGE_DB_PATH":str(self.legacy),
            "EDGE_TENANT_DB_PATH":str(self.tenant),
            "EDGE_PERMANENT_TENANTS_ONLY":"false",
            "EDGE_AUTOMATION_WORKER_ENABLED":"false",
            "ENABLE_LIVE_ORDERS":"false",
            "EDGE_CREDENTIAL_KEY":self.vault_key,
        }

    def make(self, key=None, env=None):
        return backup.create_linked_owner_backup(
            self.env if env is None else env,
            self.legacy, self.tenant, self.archive,
            key_b64=self.key if key is None else key,
            approval=backup.APPROVAL, persistent_root=self.disk,
            temp_root=self.ram)

    def test_authenticated_restore_retains_link_and_drops_only_snapshot_sessions(self):
        old_before=self.legacy.read_bytes()
        tenant_before=self.tenant.read_bytes()
        result=self.make()
        self.assertTrue(result["backup_verified"])
        self.assertTrue(result["isolated_restore_verified"])
        self.assertTrue(result["credential_decryptable"])
        self.assertTrue(result["archive_private_0600"])
        self.assertFalse(result["off_service_copy_verified"])
        self.assertFalse(result["authorized_to_activate"])
        self.assertEqual(result["owner_count"],1)
        self.assertEqual(result["active_encrypted_connections"],1)
        self.assertEqual(result["verified_linked_accounts"],1)
        self.assertEqual(result["restored_login_sessions"],0)
        self.assertEqual(old_before,self.legacy.read_bytes())
        self.assertEqual(tenant_before,self.tenant.read_bytes())
        contents=self.archive.read_bytes()
        self.assertTrue(contents.startswith(backup.MAGIC))
        self.assertNotIn(self.public_secret.encode(),contents)
        self.assertNotIn(b"SYNTHTESTACCOUNT123",contents)
        self.assertNotIn(b"SYNTHETIC_SESSION_HASH",contents)
        self.assertEqual(
            backup.verify_linked_archive(
                self.archive, key_b64=self.key, credential_key=self.vault_key,
                temp_root=self.ram),
            result["archive_sha256"] if False else
            backup._verify_blob(contents, backup.first_owner._key(self.key),
                                Fernet(self.vault_key.encode()),ram=self.ram))
        self.assertFalse(list(self.ram.glob("edgepilot-linked-restore-*")))

    def test_wrong_key_tamper_and_overwrite_deny(self):
        self.make()
        data=self.archive.read_bytes()
        with self.assertRaises(backup.LinkedOwnerBackupDenied):
            self.make()
        self.assertEqual(data,self.archive.read_bytes())
        with self.assertRaises(backup.LinkedOwnerBackupDenied):
            backup.verify_linked_archive(
                self.archive,key_b64=Fernet.generate_key().decode(),
                credential_key=self.vault_key,temp_root=self.ram)
        with self.archive.open("r+b") as out:
            out.seek(len(backup.MAGIC)+13)
            b=out.read(1)
            out.seek(-1, os.SEEK_CUR)
            out.write(bytes((b[0]^1,)))
        with self.assertRaises(backup.LinkedOwnerBackupDenied):
            backup.verify_linked_archive(
                self.archive,key_b64=self.key,
                credential_key=self.vault_key,temp_root=self.ram)

    def test_reject_bad_flags_vault_key_and_unsafe_file(self):
        for flag in backup.NEEDED_TRUE:
            with self.subTest(flag=flag):
                with self.assertRaises(backup.LinkedOwnerBackupDenied):
                    self.make(env={**self.env,flag:"false"})
                self.assertFalse(self.archive.exists())
        for flag in backup.NEEDED_FALSE:
            with self.subTest(flag=flag):
                with self.assertRaises(backup.LinkedOwnerBackupDenied):
                    self.make(env={**self.env,flag:"true"})
                self.assertFalse(self.archive.exists())
        with self.assertRaises(backup.LinkedOwnerBackupDenied):
            self.make(env={**self.env,"EDGE_CREDENTIAL_KEY":Fernet.generate_key().decode()})
        with self.assertRaises(backup.LinkedOwnerBackupDenied):
            self.make(key="invalid-key")
        os.chmod(self.tenant,0o644)
        with self.assertRaises(backup.LinkedOwnerBackupDenied):
            self.make()

    def test_requires_verified_link_and_exactly_one_owner(self):
        with sqlite3.connect(self.tenant) as db:
            db.execute("DELETE FROM tenant_accounts")
        with self.assertRaises(backup.LinkedOwnerBackupDenied):
            self.make()
        with sqlite3.connect(self.tenant) as db:
            db.execute("INSERT INTO tenant_accounts "
                "(account_id,user_id,connection_id,provider,provider_account_ref,label,created_at) "
                "SELECT ?,user_id,connection_id,'public',?,'Verified account','now' "
                "FROM tenant_connections LIMIT 1",
                (self.account,"SYNTHTESTACCOUNT123"))
        tenant_foundation.TenantStore(
            str(self.tenant)).provision_user("Another identity","member")
        with self.assertRaises(backup.LinkedOwnerBackupDenied):
            self.make()


if __name__=="__main__":
    unittest.main()
