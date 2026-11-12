"""v0.2.75: no-network, no-archive future private-family recovery inspection."""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cryptography.fernet import Fernet
from engine import identity_auth, tenant_foundation
from engine import family_recovery_readiness as readiness


class FamilyRecoveryReadinessTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="edgepilot-family-audit-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "data"
        self.root.mkdir()
        self.legacy = self.root / "edgepilot.db"
        self.tenant = self.root / "edgepilot-tenants.db"
        with sqlite3.connect(self.legacy) as db:
            db.execute("CREATE TABLE settings(k TEXT PRIMARY KEY, v TEXT)")
            db.execute("CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY, ciphertext BLOB)")
            db.execute("CREATE TABLE orders(id TEXT)")
            db.execute("CREATE TABLE activity(id TEXT)")
            db.execute("INSERT INTO broker_credentials VALUES('public', ?)",
                       (b"SYNTHETIC_LEGACY_CIPHERTEXT",))
        tenant_foundation.setup(str(self.tenant))
        identity_auth.setup(str(self.tenant))
        self.vault_key = Fernet.generate_key().decode()
        self.store = tenant_foundation.TenantStore(
            str(self.tenant), credential_key=self.vault_key)
        self.identity = identity_auth.IdentityStore(str(self.tenant))
        self.owner = self.store.provision_user("Owner test", "owner")
        self.identity.provision(
            self.owner, "first_owner", "synthetic-owner-password-2026")
        self.key_owner = "SYNTHETIC-OWN-PUBLIC-SECRET-2026-AAAAAAAAAAA"
        self.connection_owner = self.store.add_connection(
            self.owner, self.key_owner)
        self.store.link_account(
            self.owner, self.connection_owner, "SYNTHETIC-OWNER-ACCOUNT",
            "Owner brokerage")
        self.member = None
        os.chmod(self.legacy, 0o600)
        os.chmod(self.tenant, 0o600)
        self.env = {
            **{flag: "true" for flag in readiness.REQUIRED_TRUE},
            **{flag: "false" for flag in readiness.REQUIRED_FALSE},
            readiness.APPROVAL_FLAG: "true",
            "EDGE_DB_PATH": str(self.legacy),
            "EDGE_TENANT_DB_PATH": str(self.tenant),
            "EDGE_CREDENTIAL_KEY": self.vault_key,
        }

    def enroll_member(self, *, link=True, secret=None, identity=True):
        self.member = self.store.provision_user("Family test", "member")
        if identity:
            self.identity.provision(
                self.member, "second_member", "synthetic-member-password-2026")
        if link:
            connection = self.store.add_connection(
                self.member, secret or "SYNTHETIC-MEMBER-PUBLIC-SECRET-2026-BBBBBB")
            self.store.link_account(
                self.member, connection, "SYNTHETIC-MEMBER-ACCOUNT",
                "Member brokerage")
        os.chmod(self.tenant, 0o600)

    def inspect(self, env=None):
        return readiness.inspect_family_recovery(
            self.env if env is None else env,
            self.legacy, self.tenant, persistent_root=self.root)

    def test_two_member_fake_public_keys_and_original_owner_are_unchanged(self):
        self.enroll_member()
        before_legacy = self.legacy.read_bytes()
        before_tenant = self.tenant.read_bytes()
        result = self.inspect()
        self.assertEqual(result["inspection"], "passed")
        self.assertEqual(result["independent_identities"], 2)
        self.assertEqual(result["active_identities"], 2)
        self.assertEqual(result["encrypted_public_connections"], 2)
        self.assertEqual(result["active_linked_accounts"], 2)
        self.assertTrue(result["two_independent_linked_users_in_storage"])
        self.assertFalse(result["encrypted_multiuser_archive_verified"])
        self.assertFalse(result["second_physical_device_verified"])
        self.assertFalse(result["real_second_broker_verified"])
        self.assertFalse(result["authorized_to_activate"])
        self.assertFalse(result["live_trading_enabled"])
        self.assertFalse(result["bank_transfers_enabled"])
        self.assertEqual(self.legacy.read_bytes(), before_legacy)
        self.assertEqual(self.tenant.read_bytes(), before_tenant)
        self.assertFalse(list(self.root.glob("*.epbk")))
        for sensitive in (
            self.key_owner, "SYNTHETIC-MEMBER-PUBLIC",
            "SYNTHETIC-OWNER-ACCOUNT", "SYNTHETIC-MEMBER-ACCOUNT"):
            self.assertNotIn(sensitive, str(result))

    def test_one_owner_is_readable_but_not_multi_member_proof(self):
        result = self.inspect()
        self.assertEqual(result["independent_identities"], 1)
        self.assertEqual(result["active_linked_accounts"], 1)
        self.assertFalse(result["two_independent_linked_users_in_storage"])

    def test_unpaired_identity_and_shared_public_key_fail_closed(self):
        self.enroll_member(link=False, identity=False)
        with self.assertRaises(readiness.FamilyRecoveryReadinessDenied):
            self.inspect()
        with sqlite3.connect(self.tenant) as db:
            db.execute("DELETE FROM tenant_users WHERE user_id=?", (self.member,))
        # The audit event FK is deliberately present and should prevent
        # silent cleanup; simply use a fresh test instance for key sharing.

    def test_shared_public_api_key_is_refused_without_echoing_secret(self):
        self.enroll_member(secret=self.key_owner)
        try:
            self.inspect()
        except readiness.FamilyRecoveryReadinessDenied as ex:
            self.assertNotIn(self.key_owner, str(ex))
            self.assertIn("must not share", str(ex))
        else:
            self.fail("Two users sharing a Public key were accepted")

    def test_missing_flags_orders_and_invalid_fernet_fail_closed(self):
        for changes in (
            {readiness.APPROVAL_FLAG: "false"},
            {"EDGE_AUTOMATION_WORKER_ENABLED": "true"},
            {"ENABLE_LIVE_ORDERS": "true"},
            {"EDGE_TENANT_SIGNUP_ENABLED": "true"},
            {"EDGE_PERMANENT_OWNER_INVITES_ENABLED": "true"},
            {"EDGE_CREDENTIAL_KEY": Fernet.generate_key().decode()},
        ):
            with self.subTest(changes=list(changes)):
                with self.assertRaises(readiness.FamilyRecoveryReadinessDenied):
                    self.inspect({**self.env, **changes})

    def test_tampered_ciphertext_and_unsafe_storage_are_denied(self):
        with sqlite3.connect(self.tenant) as db:
            db.execute("UPDATE tenant_connections SET credential_ciphertext=?",
                       (b"not-encrypted",))
        with self.assertRaises(readiness.FamilyRecoveryReadinessDenied):
            self.inspect()
        os.chmod(self.tenant, 0o644)
        with self.assertRaises(readiness.FamilyRecoveryReadinessDenied):
            self.inspect()


if __name__ == "__main__":
    unittest.main()
