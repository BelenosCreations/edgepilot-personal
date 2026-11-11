"""v0.2.64: independent Fernet recovery checked against owner ciphertext."""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet
from engine import permanent_owner_key_recovery as audit


class OwnerCredentialRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.owner = self.root / "edgepilot.db"
        self.key = Fernet.generate_key().decode()
        self.other_key = Fernet.generate_key().decode()
        self.secret = "Public-Test-Secret-Example-1234567890"
        ciphertext = Fernet(self.key.encode()).encrypt(self.secret.encode())
        with sqlite3.connect(self.owner) as db:
            db.execute("CREATE TABLE settings(k TEXT PRIMARY KEY, v TEXT)")
            db.execute("INSERT INTO settings VALUES ('account_id','PRIVATE-OWNER-ID')")
            db.execute("CREATE TABLE orders(id TEXT)")
            db.execute("CREATE TABLE activity(id INTEGER)")
            db.execute("CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY, ciphertext BLOB)")
            db.execute("INSERT INTO broker_credentials VALUES('public',?)", (ciphertext,))
        os.chmod(self.owner, 0o600)
        self.env = {
            "EDGE_OWNER_VAULT_RECOVERY_AUDIT_ALLOWED": "true",
            "EDGE_CREDENTIAL_KEY": self.key,
            "EDGE_AUTOMATION_WORKER_ENABLED": "false",
            "ENABLE_LIVE_ORDERS": "false",
        }

    def check(self, env=None, key=None, approval=audit.APPROVAL):
        return audit.verify_private_owner_key(
            self.env if env is None else env, self.owner,
            recovery_key=self.key if key is None else key,
            approval=approval, persistent_root=self.root)

    def test_independent_key_decrypts_without_mutation_or_leak(self):
        before = self.owner.read_bytes()
        report = self.check()
        self.assertEqual(report["inspection"], "passed")
        self.assertTrue(report["entered_key_matches_running_server_key"])
        self.assertTrue(report["encrypted_public_credential_present"])
        self.assertTrue(report["saved_credential_decryption_verified"])
        self.assertFalse(report["independent_offsite_custody_verified"])
        self.assertFalse(report["authorized_to_activate"])
        for value in (self.key, self.secret, "PRIVATE-OWNER-ID"):
            self.assertNotIn(value, json.dumps(report))
        self.assertEqual(before, self.owner.read_bytes())

    def test_wrong_or_missing_key_fails_without_mutation(self):
        before = self.owner.read_bytes()
        for key, env in [
            (self.other_key, self.env),
            ("bad-key", self.env),
            ("", self.env),
            (self.key, {**self.env, "EDGE_CREDENTIAL_KEY": ""}),
            (self.key, {**self.env, "EDGE_CREDENTIAL_KEY": self.other_key}),
        ]:
            with self.subTest(case="mismatched material"):
                with self.assertRaises(audit.OwnerKeyRecoveryDenied):
                    self.check(env=env, key=key)
        self.assertEqual(before, self.owner.read_bytes())

    def test_null_tombstone_cannot_prove_encrypted_record(self):
        with sqlite3.connect(self.owner) as db:
            db.execute("UPDATE broker_credentials SET ciphertext=NULL")
        report = self.check()
        self.assertFalse(report["encrypted_public_credential_present"])
        self.assertFalse(report["saved_credential_decryption_verified"])

    def test_corrupt_ciphertext_denied_without_changes(self):
        with sqlite3.connect(self.owner) as db:
            db.execute("UPDATE broker_credentials SET ciphertext=?", (b"x" * 120,))
        before = self.owner.read_bytes()
        with self.assertRaises(audit.OwnerKeyRecoveryDenied):
            self.check()
        self.assertEqual(before, self.owner.read_bytes())

    def test_unsafe_flags_approval_permissions_and_symlink_denied(self):
        for flag in audit.DORMANT_FLAGS:
            with self.subTest(flag=flag):
                with self.assertRaises(audit.OwnerKeyRecoveryDenied):
                    self.check(env={**self.env, flag: "true"})
        with self.assertRaises(audit.OwnerKeyRecoveryDenied):
            self.check(approval="YES")
        with self.assertRaises(audit.OwnerKeyRecoveryDenied):
            self.check(env={**self.env, "EDGE_OWNER_VAULT_RECOVERY_AUDIT_ALLOWED": "false"})
        os.chmod(self.owner, 0o644)
        with self.assertRaises(audit.OwnerKeyRecoveryDenied):
            self.check()
        os.chmod(self.owner, 0o600)
        other = self.root / "real.sqlite3"
        self.owner.rename(other)
        self.owner.symlink_to(other)
        with self.assertRaises(audit.OwnerKeyRecoveryDenied):
            self.check()
        self.assertFalse((self.root / "edgepilot-tenants.db").exists())


if __name__ == "__main__":
    unittest.main()
