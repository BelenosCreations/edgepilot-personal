"""v0.2.76: synthetic two-user encrypted archive, no production or broker requests."""
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from engine import identity_auth, tenant_foundation
from engine import family_recovery_readiness as audit
from engine import permanent_family_archive as family
from engine import permanent_tenant_owner_backup as owner_key


class EncryptedFamilyArchiveTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="edgepilot-family-archive-")
        self.addCleanup(tmp.cleanup)
        self.disk = Path(tmp.name) / "data"
        self.ram = Path(tmp.name) / "shm"
        self.disk.mkdir()
        self.ram.mkdir()
        self.legacy = self.disk / "edgepilot.db"
        self.tenant = self.disk / "edgepilot-tenants.db"
        self.archive = self.ram / "edgepilot-family-SYNTHETIC.epbk"
        with sqlite3.connect(self.legacy) as db:
            db.execute("CREATE TABLE settings(k TEXT PRIMARY KEY, v TEXT)")
            db.execute("CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY, ciphertext BLOB)")
            db.execute("CREATE TABLE orders(id TEXT)")
            db.execute("CREATE TABLE activity(id INTEGER)")
            db.execute("INSERT INTO broker_credentials VALUES('public',?)",
                       (b"ORIGINAL_LEGACY_FAKE_CIPHERTEXT",))
        tenant_foundation.setup(str(self.tenant))
        identity_auth.setup(str(self.tenant))
        self.vault = Fernet.generate_key().decode()
        self.key = Fernet.generate_key().decode()
        self.users = tenant_foundation.TenantStore(
            str(self.tenant), credential_key=self.vault)
        self.auth = identity_auth.IdentityStore(str(self.tenant))
        self.owner = self.users.provision_user("Owner", "owner")
        self.auth.provision(self.owner, "family_owner",
                            "synthetic-owner-long-password-2026")
        self.secret_a = "SYNTHETIC-OWNER-PUBLIC-API-KEY-2026-AAAA"
        a = self.users.add_connection(self.owner, self.secret_a)
        self.users.link_account(self.owner, a, "SYNTHETIC-OWNER-PUBLIC-ACCOUNT",
                                "Owner account")
        self.member = None
        self.secret_b = "SYNTHETIC-MEMBER-PUBLIC-API-KEY-2026-BBBB"
        self.env = {
            **{key:"true" for key in audit.REQUIRED_TRUE},
            **{key:"false" for key in audit.REQUIRED_FALSE},
            audit.APPROVAL_FLAG:"true",
            family.ARCHIVE_FLAG:"true",
            "EDGE_DB_PATH":str(self.legacy),
            "EDGE_TENANT_DB_PATH":str(self.tenant),
            "EDGE_CREDENTIAL_KEY":self.vault,
        }
        os.chmod(self.legacy, 0o600)
        os.chmod(self.tenant, 0o600)

    def add_second_user(self, *, same_key=False):
        self.member = self.users.provision_user("Other family member","member")
        self.auth.provision(self.member, "family_member",
                            "synthetic-member-long-password-2026")
        b = self.users.add_connection(
            self.member, self.secret_a if same_key else self.secret_b)
        self.users.link_account(
            self.member, b, "SYNTHETIC-MEMBER-PUBLIC-ACCOUNT", "Member account")
        os.chmod(self.tenant, 0o600)

    def add_transient_rows(self):
        with sqlite3.connect(self.tenant) as db:
            for user in (self.owner, self.member):
                db.execute("""INSERT INTO tenant_identity_sessions
                    (token_hash,csrf_hash,user_id,credential_version,issued_at,expires_at)
                    VALUES(?,?,?,?,?,?)""",
                    ("SYNTHETIC_SESSION_"+user,"CSRF",user,1,1,9999999999))
            db.execute("""INSERT INTO tenant_auth_failures
                (source_hash,login_hash,attempted_at) VALUES('source','name',1)""")
            db.execute("""CREATE TABLE tenant_signup_attempts(
                id INTEGER PRIMARY KEY, source_hash TEXT, at_seconds INTEGER)""")
            db.execute("INSERT INTO tenant_signup_attempts VALUES(1,'hashed',1)")
            db.execute("""CREATE TABLE tenant_passkey_challenges(
                token_hash TEXT PRIMARY KEY, challenge BLOB)""")
            db.execute("INSERT INTO tenant_passkey_challenges VALUES('session', X'F1')")
            db.execute("""CREATE TABLE tenant_signup_invites(
                token_hash TEXT PRIMARY KEY, consumed_at INTEGER)""")
            db.execute("""INSERT INTO tenant_signup_invites VALUES('UNUSED_INVITE_HASH',NULL)""")
            db.execute("""INSERT INTO tenant_signup_invites VALUES('CONSUMED_INVITE_HASH',1)""")
        os.chmod(self.tenant, 0o600)

    def make(self, env=None, key=None):
        return family.create_family_archive(
            self.env if env is None else env,
            self.legacy, self.tenant, self.archive,
            key_b64=self.key if key is None else key,
            approval=family.APPROVAL,
            persistent_root=self.disk, temp_root=self.ram)

    def test_encrypted_two_user_archive_restores_without_sessions_or_invites(self):
        self.add_second_user()
        self.add_transient_rows()
        before_old = self.legacy.read_bytes()
        before_tenant = self.tenant.read_bytes()
        result = self.make()
        self.assertTrue(result["backup_verified"])
        self.assertTrue(result["isolated_restore_verified"])
        self.assertTrue(result["archive_private_0600"])
        self.assertEqual(result["independent_users_restored"],2)
        self.assertEqual(result["encrypted_connections_restored"],2)
        self.assertEqual(result["active_links_restored"],2)
        self.assertEqual(result["restored_login_sessions"],0)
        self.assertFalse(result["off_service_copy_verified"])
        self.assertFalse(result["authorized_to_activate"])
        self.assertFalse(result["live_trading_enabled"])
        self.assertFalse(result["bank_transfers_enabled"])
        self.assertEqual(before_old,self.legacy.read_bytes())
        self.assertEqual(before_tenant,self.tenant.read_bytes())
        encrypted = self.archive.read_bytes()
        self.assertTrue(encrypted.startswith(family.MAGIC))
        for forbidden in (self.secret_a,self.secret_b,
                          "SYNTHETIC-OWNER-PUBLIC-ACCOUNT",
                          "SYNTHETIC-MEMBER-PUBLIC-ACCOUNT"):
            self.assertNotIn(forbidden.encode(),encrypted)
            self.assertNotIn(forbidden,str(result))
        self.assertEqual(hashlib.sha256(encrypted).hexdigest(),
                         result["archive_sha256"])
        digest, checked=family.verify_family_archive(
            self.archive,key_b64=self.key,credential_key=self.vault,
            temp_root=self.ram)
        self.assertEqual(checked["users"],2)
        self.assertEqual(checked["sessions"],0)
        self.assertTrue(len(digest)==64)
        self.assertFalse(list(self.ram.glob("edgepilot-family-restore-*")))

        key=owner_key._key(self.key)
        raw=AESGCM(key).decrypt(
            encrypted[len(family.MAGIC):len(family.MAGIC)+12],
            encrypted[len(family.MAGIC)+12:],family.MAGIC)
        copy=self.ram/"snapshot-to-inspect.sqlite"
        copy.write_bytes(raw)
        with sqlite3.connect(copy) as db:
            for name in family.CLEAR_TRANSIENT:
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM "+name).fetchone()[0],0)
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM tenant_signup_invites WHERE consumed_at IS NULL"
            ).fetchone()[0],0)
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM tenant_signup_invites").fetchone()[0],1)

    def test_one_owner_or_shared_key_rejected(self):
        with self.assertRaises(family.FamilyArchiveDenied):
            self.make()
        self.add_second_user(same_key=True)
        with self.assertRaises(family.FamilyArchiveDenied):
            self.make()

    def test_wrong_key_tamper_no_overwrite_and_unsafe_flags(self):
        self.add_second_user()
        self.make()
        original=self.archive.read_bytes()
        with self.assertRaises(family.FamilyArchiveDenied):
            self.make()
        self.assertEqual(self.archive.read_bytes(),original)
        with self.assertRaises(family.FamilyArchiveDenied):
            family.verify_family_archive(
                self.archive,key_b64=Fernet.generate_key().decode(),
                credential_key=self.vault,temp_root=self.ram)
        for changes in (
            {family.ARCHIVE_FLAG:"false"},
            {audit.APPROVAL_FLAG:"false"},
            {"ENABLE_LIVE_ORDERS":"true"},
            {"EDGE_AUTOMATION_WORKER_ENABLED":"true"},
            {"EDGE_PERMANENT_OWNER_INVITES_ENABLED":"true"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(family.FamilyArchiveDenied):
                    family.create_family_archive(
                        {**self.env,**changes},self.legacy,self.tenant,
                        self.ram/"another.epbk",key_b64=self.key,
                        approval=family.APPROVAL,persistent_root=self.disk,
                        temp_root=self.ram)
        with self.archive.open("r+b") as out:
            out.seek(len(family.MAGIC)+13)
            b=out.read(1)
            out.seek(len(family.MAGIC)+13)
            out.write(bytes([b[0]^0x01]))
        with self.assertRaises(family.FamilyArchiveDenied):
            family.verify_family_archive(
                self.archive,key_b64=self.key,credential_key=self.vault,
                temp_root=self.ram)

    def test_unsafe_private_storage_denied_without_archive(self):
        self.add_second_user()
        os.chmod(self.tenant, 0o644)
        with self.assertRaises(family.FamilyArchiveDenied):
            self.make()
        self.assertFalse(self.archive.exists())


if __name__=="__main__":
    unittest.main()
