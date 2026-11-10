"""v0.2.39: no-production synthetic encrypted backup and restore validation."""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cryptography.fernet import Fernet
from engine import (
    account_scope, identity_auth, tenant_backup_rehearsal,
    tenant_foundation, tenant_passkeys, tenant_registration,
)

class TwoTenantEncryptedRestoreTests(unittest.TestCase):
    def setUp(self):
        # A Linux tmpfs is required. A normal disk path MUST NOT be used.
        self.tmp=tempfile.TemporaryDirectory(prefix="edgepilot-backup-fixture-",dir="/dev/shm")
        self.path=Path(self.tmp.name)/"tenant.db"
        self.backup_key=Fernet.generate_key()
        self.vault_key=Fernet.generate_key()
        tenant_foundation.setup(self.path)
        identity_auth.setup(self.path)
        account_scope.setup(self.path)
        tenant_passkeys.setup(self.path)
        tenant_registration.setup(self.path)
        self.db=tenant_foundation.TenantStore(self.path,credential_key=self.vault_key)
        self.a=self.db.provision_user("Alice","member")
        self.b=self.db.provision_user("Bob","member")
        self.ca=self.db.add_connection(self.a,"SYNTHETIC-ONLY-NOT-REAL-PUBLIC-ALICE-123")
        self.cb=self.db.add_connection(self.b,"SYNTHETIC-ONLY-NOT-REAL-PUBLIC-BOB-456")
        self.aa=self.db.link_account(self.a,self.ca,"FAKE-A","Alice account")
        self.ba=self.db.link_account(self.b,self.cb,"FAKE-B","Bob account")
        self.db.account_setting(self.a,self.aa,"watchlist_csv","SPY,QQQ")
        self.db.account_setting(self.b,self.ba,"watchlist_csv","MSFT")
        self.login=identity_auth.IdentityStore(str(self.path))
        self.login.provision(self.a,"restore_alice","example-alice-password-long-v039")
        self.login.provision(self.b,"restore_bob","example-bob-password-long-v039")
        self.alice_session=self.login.authenticate(
            "restore_alice","example-alice-password-long-v039","phone-a")
        self.bob_session=self.login.authenticate(
            "restore_bob","example-bob-password-long-v039","phone-b")
        with sqlite3.connect(self.path) as con:
            con.execute("""INSERT INTO tenant_passkey_challenges
                (token_hash,operation,user_id,challenge,expires_at,rp_id,origin)
                VALUES(?,?,?,?,?,?,?)""",
                ("a"*64,"authenticate",None,b"synthetic-only",9999999999,
                 "edgepilot.example.test","https://edgepilot.example.test"))
            con.execute("""INSERT INTO tenant_signup_invites
                (token_hash,created_at,expires_at)
                VALUES(?,?,?)""",("b"*64,100,9999999999))

    def tearDown(self):
        self.tmp.cleanup()

    def test_encrypted_restore_preserves_isolation_but_invalidates_sessions(self):
        encrypted=tenant_backup_rehearsal.sealed_snapshot(self.path,self.backup_key)
        self.assertIsInstance(encrypted,bytes)
        self.assertNotIn(b"SQLite format 3",encrypted)
        self.assertNotIn(b"SYNTHETIC-ONLY-NOT-REAL-PUBLIC",encrypted)
        restored=tenant_backup_rehearsal.restore_sealed_fixture(
            encrypted,self.backup_key,Path(self.tmp.name)/"isolated-restored.db")
        self.assertTrue(restored.exists())
        self.assertEqual(restored.stat().st_mode & 0o777,0o600)
        rebuilt=identity_auth.IdentityStore(str(restored))
        self.assertIsNone(rebuilt.principal(self.alice_session["token"]))
        self.assertIsNone(rebuilt.principal(self.bob_session["token"]))
        sa=rebuilt.authenticate("restore_alice","example-alice-password-long-v039","new-phone-a")
        sb=rebuilt.authenticate("restore_bob","example-bob-password-long-v039","new-phone-b")
        scopes=account_scope.AccountScopeStore(str(restored),rebuilt)
        # Restoring an old archive must quarantine ALL broker bindings:
        # a later revoked key may not be resurrected by disaster recovery.
        self.assertEqual(scopes.list_accounts(sa["token"]),[])
        self.assertEqual(scopes.list_accounts(sb["token"]),[])
        for token,acct in ((sa["token"],self.aa),(sa["token"],self.ba),
                           (sb["token"],self.ba),(sb["token"],self.aa)):
            with self.assertRaises(tenant_foundation.TenantAccessError):
                scopes.account_summary(token,acct)
        with sqlite3.connect(restored) as con:
            self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0],"ok")
            self.assertIsNone(con.execute("PRAGMA foreign_key_check").fetchone())
            for table in ("tenant_identity_sessions","tenant_passkey_challenges",
                          "tenant_signup_invites","tenant_worker_leases"):
                if table != "tenant_identity_sessions":
                    self.assertEqual(con.execute(
                        "SELECT COUNT(*) FROM "+table).fetchone()[0],0)
            rows=con.execute("""SELECT user_id,credential_ciphertext
                FROM tenant_connections ORDER BY user_id""").fetchall()
            self.assertEqual(len(rows),2)
            # Ownership and settings survive as encrypted historical data,
            # but all recovered connections/accounts are unusable until
            # explicit later re-enrollment and provider re-verification.
            state=con.execute("""SELECT c.user_id,c.revoked_at,a.disabled_at
                FROM tenant_connections c JOIN tenant_accounts a
                ON a.connection_id=c.connection_id
                ORDER BY c.user_id""").fetchall()
            self.assertEqual(len(state),2)
            self.assertEqual({r[0] for r in state},{self.a,self.b})
            self.assertTrue(all(r[1] and r[2] for r in state))
            self.assertEqual({uid:Fernet(self.vault_key).decrypt(blob).decode()
                              for uid,blob in rows},
                {self.a:"SYNTHETIC-ONLY-NOT-REAL-PUBLIC-ALICE-123",
                 self.b:"SYNTHETIC-ONLY-NOT-REAL-PUBLIC-BOB-456"})
            settings=con.execute("""SELECT user_id,account_id,setting_value
                FROM tenant_account_settings WHERE setting_key='watchlist_csv'""").fetchall()
            self.assertEqual({(r[0],r[1]):r[2] for r in settings},
                             {(self.a,self.aa):"SPY,QQQ",(self.b,self.ba):"MSFT"})

    def test_wrong_key_corrupted_archive_existing_target_and_outside_paths_fail(self):
        token=tenant_backup_rehearsal.sealed_snapshot(self.path,self.backup_key)
        target=Path(self.tmp.name)/"refused.db"
        for bad,key in ((token,Fernet.generate_key()),
                        (token[:-8]+b"12345678",self.backup_key),
                        (b"fake",self.backup_key)):
            with self.assertRaises(tenant_backup_rehearsal.OfflineBackupDenied):
                tenant_backup_rehearsal.restore_sealed_fixture(bad,key,target)
            self.assertFalse(target.exists())
        wrong_format=Fernet(self.backup_key).encrypt(
            tenant_backup_rehearsal._MAGIC+b"SQLite format 3\x00fake database")
        with self.assertRaises(tenant_backup_rehearsal.OfflineBackupDenied):
            tenant_backup_rehearsal.restore_sealed_fixture(
                wrong_format,self.backup_key,target)
        self.assertFalse(target.exists())
        target.write_text("preserve-existing-file",encoding="utf-8")
        with self.assertRaises(tenant_backup_rehearsal.OfflineBackupDenied):
            tenant_backup_rehearsal.restore_sealed_fixture(token,self.backup_key,target)
        self.assertEqual(target.read_text(),"preserve-existing-file")
        with tempfile.TemporaryDirectory() as disk:
            forbidden=Path(disk)/"plain.db"
            with self.assertRaises(tenant_backup_rehearsal.OfflineBackupDenied):
                tenant_backup_rehearsal.restore_sealed_fixture(
                    token,self.backup_key,forbidden)
            self.assertFalse(forbidden.exists())
        with self.assertRaises(tenant_backup_rehearsal.OfflineBackupDenied):
            tenant_backup_rehearsal.sealed_snapshot(Path(__file__),self.backup_key)

    def test_worker_leases_and_active_runtimes_are_rejected(self):
        with sqlite3.connect(self.path) as con:
            con.execute("""INSERT INTO tenant_worker_leases
                (account_id,user_id,worker_id,expires_at) VALUES(?,?,?,?)""",
                (self.aa,self.a,"TEST-LEASE",9999999999))
        with self.assertRaises(tenant_backup_rehearsal.OfflineBackupDenied):
            tenant_backup_rehearsal.sealed_snapshot(self.path,self.backup_key)
        with sqlite3.connect(self.path) as con:
            con.execute("DELETE FROM tenant_worker_leases")
            con.execute("""INSERT INTO tenant_runtime_status
                (account_id,user_id,requested_mode,worker_enabled,paper_enabled,live_enabled)
                VALUES(?,?,'observe',0,0,0)""",(self.aa,self.a))
            con.execute("PRAGMA ignore_check_constraints=ON")
            con.execute("UPDATE tenant_runtime_status SET worker_enabled=1 WHERE account_id=?",
                        (self.aa,))
            con.execute("PRAGMA ignore_check_constraints=OFF")
        with self.assertRaises(tenant_backup_rehearsal.OfflineBackupDenied):
            tenant_backup_rehearsal.sealed_snapshot(self.path,self.backup_key)

    def test_has_no_live_runtime_integration(self):
        root=Path(__file__).resolve().parents[2]
        app=(root/"backend/app.py").read_text()
        worker=(root/"backend/engine/automation_worker.py").read_text()
        self.assertNotIn("tenant_backup_rehearsal",app)
        self.assertNotIn("tenant_backup_rehearsal",worker)
        self.assertNotIn("resume_real_worker(",tenant_backup_rehearsal.__doc__ or "")
        with self.assertRaises(tenant_backup_rehearsal.OfflineBackupDenied):
            tenant_backup_rehearsal.sealed_snapshot(self.path,b"wrong-backup-key")

if __name__=="__main__":
    unittest.main()
