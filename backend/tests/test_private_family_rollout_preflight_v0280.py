"""v0.2.80 synthetic read-only first family invitation rollout audit.

No real brokerage, credential, phone, cloud backup or Render file is accessed.
"""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cryptography.fernet import Fernet
from engine import identity_auth, tenant_foundation, tenant_registration
from engine import private_family_rollout_preflight as preflight


class FirstFamilyInvitationReadinessTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="edgepilot-invite-preflight-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.legacy = self.root / "edgepilot.db"
        self.tenant = self.root / "edgepilot-tenants.db"
        with sqlite3.connect(self.legacy) as db:
            db.execute("CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT)")
            db.execute("CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY,ciphertext BLOB)")
            db.execute("CREATE TABLE orders(id TEXT)")
            db.execute("CREATE TABLE activity(id INTEGER)")
            db.execute("INSERT INTO broker_credentials VALUES('public',?)",
                       (b"SYNTHETIC-LEGACY-PRIVATE-BROKER-DATA",))
        tenant_foundation.setup(str(self.tenant))
        identity_auth.setup(str(self.tenant))
        self.key = Fernet.generate_key().decode()
        self.store = tenant_foundation.TenantStore(
            str(self.tenant), credential_key=self.key)
        self.owner = self.store.provision_user("Owner test", "owner")
        self.auth = identity_auth.IdentityStore(str(self.tenant))
        self.auth.provision(
            self.owner, "synthetic_owner", "synthetic-password-for-tests-2026")
        self.public_secret = "SYNTHETIC-PUBLIC-KEY-FOR-ONE-OWNER-2026-AAAAA"
        self.connection = self.store.add_connection(self.owner, self.public_secret)
        self.account = self.store.link_account(
            self.owner, self.connection, "SYNTHETIC-BROKERAGE-ONE",
            "Verified synthetic brokerage")
        os.chmod(self.legacy, 0o600)
        os.chmod(self.tenant, 0o600)
        self.env = {
            **{flag: "true" for flag in preflight.REQUIRED_TRUE},
            **{flag: "false" for flag in preflight.REQUIRED_FALSE},
            preflight.AUDIT_FLAG: "true",
            "EDGE_DB_PATH": str(self.legacy),
            "EDGE_TENANT_DB_PATH": str(self.tenant),
            "EDGE_CREDENTIAL_KEY": self.key,
        }

    def inspect(self, env=None):
        return preflight.inspect_first_invitation_readiness(
            self.env if env is None else env,
            self.legacy, self.tenant, persistent_root=self.root,
            now=1800000010)

    def test_one_verified_owner_is_read_only_but_not_activation_proof(self):
        session = self.auth.authenticate(
            "synthetic_owner", "synthetic-password-for-tests-2026",
            source="synthetic-test")
        self.assertIsNotNone(session)
        legacy_before = self.legacy.read_bytes()
        tenant_before = self.tenant.read_bytes()
        report = self.inspect()
        self.assertEqual(report["inspection"], "passed")
        self.assertTrue(report["legacy_database_present_and_separate"])
        self.assertFalse(report["legacy_login_end_to_end_verified"])
        self.assertFalse(report["public_network_verification_performed"])
        self.assertEqual(report["existing_tenant_members"], 0)
        self.assertEqual(report["active_owner_public_connections"], 1)
        self.assertEqual(report["verified_owner_public_links"], 1)
        self.assertEqual(report["active_identity_sessions"], 1)
        for flag in ("external_backup_custody_independently_proven",
                     "second_physical_device_verified",
                     "second_independent_public_account_verified",
                     "member_registration_authorized",
                     "live_trading_enabled", "autonomous_orders_enabled",
                     "bank_transfers_enabled"):
            self.assertFalse(report[flag])
        self.assertEqual(legacy_before, self.legacy.read_bytes())
        self.assertEqual(tenant_before, self.tenant.read_bytes())
        self.assertFalse(list(self.root.glob("*.epbk")))
        for value in (self.owner, self.account, self.connection,
                      self.public_secret):
            self.assertNotIn(value, str(report))

    def test_all_unsafe_rollout_flag_combinations_are_denied(self):
        for flag in preflight.REQUIRED_TRUE:
            with self.subTest(missing=flag):
                with self.assertRaises(preflight.FamilyRolloutReadinessDenied):
                    self.inspect({**self.env, flag:"false"})
        for flag in preflight.REQUIRED_FALSE:
            with self.subTest(unsafe=flag):
                with self.assertRaises(preflight.FamilyRolloutReadinessDenied):
                    self.inspect({**self.env, flag:"true"})
        for altered in (
            {"EDGE_CREDENTIAL_KEY":""},
            {"EDGE_CREDENTIAL_KEY":Fernet.generate_key().decode()},
            {"EDGE_DB_PATH":str(self.tenant)},
            {"EDGE_TENANT_DB_PATH":str(self.legacy)},
            {preflight.AUDIT_FLAG:"false"},
        ):
            with self.subTest(changes=list(altered)):
                with self.assertRaises(preflight.FamilyRolloutReadinessDenied):
                    self.inspect({**self.env, **altered})

    def test_unlinked_owner_and_second_member_fail_closed(self):
        with sqlite3.connect(self.tenant) as db:
            db.execute("UPDATE tenant_accounts SET disabled_at='2026-11-12'")
        with self.assertRaises(preflight.FamilyRolloutReadinessDenied):
            self.inspect()
        with sqlite3.connect(self.tenant) as db:
            db.execute("UPDATE tenant_accounts SET disabled_at=NULL")
        member = self.store.provision_user("Second user", "member")
        self.auth.provision(member, "synthetic_member",
                            "synthetic-member-password-2026")
        os.chmod(self.tenant, 0o600)
        with self.assertRaises(preflight.FamilyRolloutReadinessDenied):
            self.inspect()

    def test_pending_unused_invitation_and_unreadable_ciphertext_denied(self):
        tenant_registration.setup(str(self.tenant))
        registration = tenant_registration.TenantRegistration(str(self.tenant),max_users=10)
        token = registration.issue_invitation(now=1800000000)["invitation"]
        with self.assertRaises(preflight.FamilyRolloutReadinessDenied):
            self.inspect()
        with sqlite3.connect(self.tenant) as db:
            db.execute("DELETE FROM tenant_signup_invites")
            db.execute("""UPDATE tenant_connections SET credential_ciphertext=?
                WHERE connection_id=?""", (b"CORRUPT-CIPHERTEXT", self.connection))
        with self.assertRaises(preflight.FamilyRolloutReadinessDenied):
            self.inspect()
        self.assertNotIn(token, str(self.env))

    def test_private_mode_and_symlink_are_required(self):
        os.chmod(self.tenant, 0o644)
        with self.assertRaises(preflight.FamilyRolloutReadinessDenied):
            self.inspect()
        os.chmod(self.tenant, 0o600)
        self.assertEqual(self.inspect()["inspection"], "passed")
        other = self.root / "other.db"
        self.tenant.rename(other)
        self.tenant.symlink_to(other)
        with self.assertRaises(preflight.FamilyRolloutReadinessDenied):
            self.inspect()


if __name__ == "__main__":
    unittest.main()
