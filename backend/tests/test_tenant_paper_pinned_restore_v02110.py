"""Encrypted recovery of marked synthetic tenant scopes and immutable policies."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
import fcntl
import os
import sqlite3
from threading import Barrier
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from cryptography.fernet import Fernet

from engine import (account_scope, identity_auth, tenant_foundation, tenant_passkeys,
                    tenant_public_vault, tenant_registration)
from engine import tenant_backup_rehearsal as backup
from engine import tenant_paper_authenticated_preflight as preflight
from engine import tenant_paper_ledger as ledger
from engine.tenant_paper_loss_stop import _replay_realized
from engine.tenant_paper_recovery_audit import PaperRestorePolicy
import test_tenant_paper_authenticated_preflight_v02107 as fixtures
from test_tenant_passkeys_v0225 import b64url


class PinnedPaperRestoreTests(unittest.TestCase):
    setUp = fixtures.AuthenticatedPaperPreflightTest.setUp
    provision = fixtures.AuthenticatedPaperPreflightTest.provision
    seed = fixtures.AuthenticatedPaperPreflightTest.seed
    params = fixtures.AuthenticatedPaperPreflightTest.params
    append = fixtures.AuthenticatedPaperPreflightTest.append

    def prepare(self):
        account_scope.setup(self.path)
        self.archive_key = Fernet.generate_key()
        self.destination = self.path.with_name("restored.db")
        self.policies = dict.fromkeys(
            [(self.owner, self.account), (self.owner, self.alternate),
             (self.member, self.other)], PaperRestorePolicy(90, 1000, 300, 54))
        self.request = self.params(quantity="1", protected_pct="90", per_trade_cap="3")
        self.assertEqual(self.append(self.request)["paperCash"], "97.97")
        retry = self.append(self.request)
        self.assertTrue(retry["duplicate"])
        self.assertEqual(retry["originalPaperCashAfter"], "97.97")
        self.append(self.params(side="SELL", observation=fixtures.evidence("0.99", "1.00")))
        self.append(self.params(side="SELL", observation=fixtures.evidence("9.00", "9.01"),
                                quantity="0.25"))

    def seal(self, policies=None):
        return backup.seal_pinned_paper_fixture(
            self.path, self.archive_key, policies=self.policies if policies is None else policies)

    def restore(self, token, pin, policies=None):
        return backup.restore_pinned_paper_fixture(
            token, self.archive_key, self.destination, trusted_pin=pin,
            policies=self.policies if policies is None else policies)

    def test_existing_request_fractional_basis_and_revoked_scope_survive(self):
        self.prepare()
        revoked_at = datetime.now(timezone.utc).isoformat()
        member_request = {**self.request, "account_id": self.other}
        member_fill = ledger.record_paper_fill(
            self.path, principal_user_id=self.member, now=revoked_at, **member_request)
        self.assertFalse(member_fill["duplicate"])
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE tenant_connections SET revoked_at=? WHERE connection_id=?",
                       (revoked_at, self.member_conn))
            db.execute("UPDATE tenant_accounts SET disabled_at=? WHERE account_id=?",
                       (revoked_at, self.alternate))
            original_digest = db.execute(
                "SELECT user_id,account_id,request_sha256 FROM tenant_paper_events "
                "WHERE request_id=? ORDER BY user_id,account_id",
                (self.request["request_id"],)).fetchall()
            self.assertEqual(len(original_digest), 2)
        token, pin = self.seal()
        restored = self.restore(token, pin)
        with closing(sqlite3.connect(restored)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tenant_identity_sessions")
                             .fetchone(), (0,))
            self.assertEqual(db.execute(
                "SELECT user_id,account_id,request_sha256 FROM tenant_paper_events "
                "WHERE request_id=? ORDER BY user_id,account_id",
                (self.request["request_id"],)).fetchall(), original_digest)
            self.assertEqual(db.execute("SELECT quantity,cost_basis_cents,realized_cents "
                                       "FROM tenant_paper_positions WHERE user_id=?",
                                       (self.owner,)).fetchall(), [("0.25", 50, 119)])
            self.assertEqual(_replay_realized(db.execute(
                "SELECT side,asset_class,symbol,quantity,signed_cash_change_cents "
                "FROM tenant_paper_events WHERE user_id=? ORDER BY rowid",
                (self.owner,))), (119, -54, 2))
            self.assertEqual(db.execute("SELECT cash_cents FROM tenant_paper_wallets "
                                        "WHERE user_id=? AND account_id=?",
                                        (self.member, self.other)).fetchone(), (9797,))
            self.assertEqual(db.execute("SELECT revoked_at FROM tenant_connections "
                                        "WHERE connection_id=?", (self.member_conn,))
                             .fetchone(), (revoked_at,))
            self.assertEqual(db.execute("SELECT disabled_at FROM tenant_accounts "
                                        "WHERE account_id=?", (self.alternate,))
                             .fetchone(), (revoked_at,))
        for user, account in self.policies:
            with self.assertRaises(ledger.PaperLedgerDenied):
                ledger.snapshot(restored, principal_user_id=user, account_id=account)
        with self.assertRaises(preflight.PaperPreflightDenied):
            preflight.inspect_fill(restored, session_token=self.session["token"],
                                   csrf=self.session["csrf"], max_realized_loss="0.54",
                                   **self.request)

    def test_rejects_rewritten_digest_changed_policy_and_old_ciphertext(self):
        self.prepare()
        old_token, old_pin = self.seal()
        self.append(self.params(side="SELL", observation=fixtures.evidence("9.00", "9.01"),
                                quantity="0.25"))
        current_token, current_pin = self.seal()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE tenant_paper_events SET request_sha256=? WHERE request_id=?",
                       ("a" * 64, self.request["request_id"]))
        replaced_token, _ = self.seal()
        altered = self.policies | {(self.owner, self.account): PaperRestorePolicy(90, 1000, 300, 55)}
        for token, pin, policies in (
                (old_token, current_pin, self.policies),
                (current_token, old_pin, self.policies),
                (replaced_token, current_pin, self.policies),
                (current_token, current_pin, altered)):
            with self.subTest(pin=pin), self.assertRaises(backup.OfflineBackupDenied):
                self.restore(token, pin, policies)
            self.assertFalse(self.destination.exists())
        with self.assertRaises(backup.OfflineBackupDenied):
            backup.restore_sealed_fixture(current_token, self.archive_key, self.destination)
        self.assertEqual(self.restore(current_token, current_pin), self.destination)

    def test_rejects_missing_policy_and_purchase_after_historical_stop(self):
        self.prepare()
        incomplete = self.policies.copy()
        del incomplete[(self.member, self.other)]
        with self.assertRaises(backup.OfflineBackupDenied):
            self.seal(incomplete)
        self.append(self.params(request_id=str(uuid4()), protected_pct="90", per_trade_cap="3"))
        with self.assertRaises(backup.OfflineBackupDenied):
            self.seal()

    def test_concurrent_publishers_have_one_winner_and_preserve_exact_evidence(self):
        self.prepare()
        token, pin = self.seal()
        link = backup.os.link
        with closing(sqlite3.connect(self.path)) as db:
            digest = backup._paper_data_digest(db)
        rendezvous = Barrier(2, timeout=5)

        def publish(source, target):
            rendezvous.wait()
            return link(source, target)

        with patch.object(backup.os, "link", side_effect=publish):
            with ThreadPoolExecutor(max_workers=2) as pool:
                attempts = [pool.submit(self.restore, token, pin) for _ in range(2)]
        self.assertEqual([attempt.result() for attempt in attempts if attempt.exception() is None],
                         [self.destination])
        self.assertEqual(sum(isinstance(attempt.exception(), backup.OfflineBackupDenied)
                             for attempt in attempts), 1)
        with closing(sqlite3.connect(self.destination)) as db:
            self.assertEqual(backup._paper_data_digest(db), digest)
            self.assertTrue(all(row[-2] and row[-1] for row in backup._paper_scope(db)))
        self.assertFalse(list(self.destination.parent.glob(".edgepilot-synthetic-restore-*")))

    def test_interrupted_publication_does_not_reuse_or_overwrite_destination(self):
        self.prepare()
        token, pin = self.seal()
        link = backup.os.link

        def link_then_lose_reply(source, target):
            link(source, target)
            raise OSError

        with patch.object(backup.os, "link", side_effect=OSError):
            with self.assertRaises(backup.OfflineBackupDenied):
                self.restore(token, pin)
        self.assertFalse(self.destination.exists())
        with patch.object(backup.os, "link", side_effect=link_then_lose_reply):
            with self.assertRaises(backup.OfflineBackupDenied):
                self.restore(token, pin)
        published = self.destination.read_bytes()
        with self.assertRaises(backup.OfflineBackupDenied):
            self.restore(token, pin)
        self.assertEqual(self.destination.read_bytes(), published)
        self.assertFalse(list(self.destination.parent.glob(".edgepilot-synthetic-restore-*")))

    def test_pinned_publication_rejects_existing_sqlite_sidecars(self):
        self.prepare()
        token, pin = self.seal()
        for suffix in backup._SIDECARS:
            with self.subTest(suffix=suffix):
                sidecar = self.destination.with_name(self.destination.name + suffix)
                sidecar.write_bytes(b"prior file")
                with self.assertRaises(backup.OfflineBackupDenied):
                    self.restore(token, pin)
                self.assertEqual(sidecar.read_bytes(), b"prior file")
                self.assertFalse(self.destination.exists())
                sidecar.unlink()

    def orphan_stage(self, token, pin):
        link = os.link

        def link_then_exit(source, destination):
            link(source, destination)
            os._exit(81)

        pid = os.fork()
        if pid == 0:
            try:
                with patch.object(backup.os, "link", side_effect=link_then_exit):
                    self.restore(token, pin)
            finally:
                os._exit(82)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 81)
        self.assertEqual(self.destination.stat().st_nlink, 2)
        stages = list(self.destination.parent.glob(".edgepilot-synthetic-restore-*"))
        self.assertEqual(len(stages), 1)
        self.assertTrue(self.destination.samefile(stages[0]))
        return stages[0]

    def test_process_exit_after_link_requires_exact_read_only_inspection(self):
        self.prepare()
        token, pin = self.seal()
        stage = self.orphan_stage(token, pin)
        before = self.destination.read_bytes()

        def inspect():
            return backup.inspect_pinned_paper_publication(
                token, self.archive_key, self.destination, policies=self.policies,
                trusted_pin=pin)

        self.assertEqual(inspect(), {"quarantineVerified": True, "additionalLinkPresent": True})
        self.assertEqual(self.destination.read_bytes(), before)
        with self.assertRaises(backup.OfflineBackupDenied):
            self.restore(token, pin)
        self.assertTrue(stage.exists())
        with closing(sqlite3.connect(self.destination)) as db, db:
            db.execute("UPDATE tenant_paper_events SET request_sha256=?", ("a" * 64,))
        with self.assertRaises(backup.OfflineBackupDenied):
            inspect()

    def cleanup(self, token, pin, stage):
        backup.cleanup_pinned_paper_staging_link(
            token, self.archive_key, self.destination, stage, policies=self.policies,
            trusted_pin=pin)

    def test_manual_cleanup_preserves_exact_quarantined_destination(self):
        self.prepare()
        token, pin = self.seal()
        stage = self.orphan_stage(token, pin)
        before = self.destination.read_bytes()
        identity = self.destination.stat()
        self.cleanup(token, pin, stage)
        self.assertFalse(stage.exists())
        self.assertTrue(os.path.samestat(identity, self.destination.stat()))
        self.assertEqual(self.destination.read_bytes(), before)
        self.assertEqual(backup.inspect_pinned_paper_publication(
            token, self.archive_key, self.destination, policies=self.policies, trusted_pin=pin),
            {"quarantineVerified": True, "additionalLinkPresent": False})
        with self.assertRaises(backup.OfflineBackupDenied):
            self.cleanup(token, pin, stage)
        for user, account in self.policies:
            with self.assertRaises(ledger.PaperLedgerDenied):
                ledger.snapshot(self.destination, principal_user_id=user, account_id=account)

    def test_cleanup_refuses_unrelated_symlink_or_unexpected_third_link(self):
        self.prepare()
        token, pin = self.seal()
        stage = self.orphan_stage(token, pin)
        unrelated = stage.with_name(".edgepilot-synthetic-restore-unrelated.db")
        unrelated.write_bytes(b"unrelated data")
        unrelated.chmod(0o600)
        symlink = stage.with_name(".edgepilot-synthetic-restore-symlink.db")
        symlink.symlink_to(self.destination)
        for candidate in (unrelated, symlink, self.destination):
            with self.assertRaises(backup.OfflineBackupDenied):
                self.cleanup(token, pin, candidate)
        self.assertEqual(unrelated.read_bytes(), b"unrelated data")
        self.assertTrue(symlink.is_symlink())
        third = stage.with_name("unrelated-link.db")
        os.link(stage, third)
        with self.assertRaises(backup.OfflineBackupDenied):
            self.cleanup(token, pin, stage)
        self.assertTrue(stage.samefile(third))
        self.assertTrue(stage.samefile(self.destination))

    def test_cleanup_refuses_active_publication_sqlite_and_sidecars(self):
        self.prepare()
        token, pin = self.seal()
        link = os.link

        def while_publishing(source, target):
            link(source, target)
            with self.assertRaises(backup.OfflineBackupDenied):
                self.cleanup(token, pin, source)
            self.assertTrue(source.samefile(target))

        with patch.object(backup.os, "link", side_effect=while_publishing):
            self.restore(token, pin)
        self.assertEqual(self.destination.stat().st_nlink, 1)
        self.destination.unlink()
        stage = self.orphan_stage(token, pin)
        with closing(sqlite3.connect(self.destination)) as db:
            db.execute("BEGIN")
            db.execute("SELECT COUNT(*) FROM tenant_accounts").fetchone()
            with self.assertRaises(backup.OfflineBackupDenied):
                self.cleanup(token, pin, stage)
        sidecar = stage.with_name(stage.name + "-journal")
        sidecar.touch()
        with self.assertRaises(backup.OfflineBackupDenied):
            self.cleanup(token, pin, stage)
        self.assertTrue(sidecar.exists())
        self.assertTrue(stage.samefile(self.destination))

    def test_cleanup_refuses_changed_destination_after_review(self):
        self.prepare()
        token, pin = self.seal()
        stage = self.orphan_stage(token, pin)
        audit = backup._audit_publication
        preserved = self.destination.with_name("reviewed.db")

        def replace_destination(*args):
            audit(*args)
            self.destination.rename(preserved)
            self.destination.write_bytes(b"replacement")
            self.destination.chmod(0o600)

        with patch.object(backup, "_audit_publication", side_effect=replace_destination):
            with self.assertRaises(backup.OfflineBackupDenied):
                self.cleanup(token, pin, stage)
        self.assertTrue(stage.samefile(preserved))
        self.assertEqual(self.destination.read_bytes(), b"replacement")

    def assert_cleaned_publication(self, token, pin, stage, identity, before):
        self.assertFalse(stage.exists())
        self.assertTrue(os.path.samestat(identity, self.destination.stat()))
        self.assertEqual(self.destination.read_bytes(), before)
        self.assertEqual(backup.inspect_pinned_paper_publication(
            token, self.archive_key, self.destination, policies=self.policies, trusted_pin=pin),
            {"quarantineVerified": True, "additionalLinkPresent": False})

    def test_concurrent_cleanup_allows_one_unlink(self):
        self.prepare()
        token, pin = self.seal()
        stage = self.orphan_stage(token, pin)
        identity, before = self.destination.stat(), self.destination.read_bytes()
        start = Barrier(2, timeout=5)

        def cleanup():
            start.wait()
            self.cleanup(token, pin, stage)

        with ThreadPoolExecutor(max_workers=2) as pool:
            attempts = [pool.submit(cleanup) for _ in range(2)]
        self.assertEqual(sum(attempt.exception() is None for attempt in attempts), 1)
        self.assertEqual(sum(isinstance(attempt.exception(), backup.OfflineBackupDenied)
                             for attempt in attempts), 1)
        self.assert_cleaned_publication(token, pin, stage, identity, before)

    def test_cleanup_process_exit_before_and_after_unlink(self):
        self.prepare()
        token, pin = self.seal()
        stage = self.orphan_stage(token, pin)
        identity, before = self.destination.stat(), self.destination.read_bytes()
        unlink = os.unlink
        for remove in (False, True):
            def exit_at_unlink(*args, **kwargs):
                if remove:
                    unlink(*args, **kwargs)
                os._exit(92)

            pid = os.fork()
            if pid == 0:
                try:
                    with patch.object(backup.os, "unlink", side_effect=exit_at_unlink):
                        self.cleanup(token, pin, stage)
                finally:
                    os._exit(93)
            _, status = os.waitpid(pid, 0)
            self.assertEqual(os.waitstatus_to_exitcode(status), 92)
            self.assertEqual(stage.exists(), not remove)
            self.assertEqual(self.destination.read_bytes(), before)
            self.assertEqual(backup.inspect_pinned_paper_publication(
                token, self.archive_key, self.destination, policies=self.policies,
                trusted_pin=pin)["additionalLinkPresent"], not remove)
        self.assert_cleaned_publication(token, pin, stage, identity, before)

    def test_quarantine_preserves_passkeys_and_unlinked_connection_history(self):
        self.prepare()
        tenant_passkeys.setup(self.path)
        tenant_registration.setup(self.path)
        tenant_registration.TenantRegistration(self.path).issue_invitation()
        revoked = "2026-10-01T12:00:00+00:00"
        orphan = str(uuid4())
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executemany("INSERT INTO tenant_passkey_credentials VALUES (?,?,?,?,?,?,?,?)", (
                (b"active", self.owner, b"synthetic-key-a", 4, "single_device", 0, 100, None),
                (b"revoked", self.member, b"synthetic-key-b", 7, "single_device", 0, 100, 200),
            ))
            db.execute("INSERT INTO tenant_passkey_challenges VALUES (?,?,?,?,?,?,?)",
                       ("synthetic", "register", self.owner, b"challenge", 123, "example.test",
                        "https://example.test"))
            db.execute("INSERT INTO tenant_connections VALUES (?,?,?,?,?,?)",
                       (orphan, self.member, "public", b"synthetic-ciphertext", revoked, revoked))
        token, pin = self.seal()
        stage = self.orphan_stage(token, pin)
        self.cleanup(token, pin, stage)
        with closing(sqlite3.connect(self.destination)) as db:
            self.assertEqual(db.execute("SELECT revoked_at FROM tenant_connections "
                                        "WHERE connection_id=?", (orphan,)).fetchone(), (revoked,))
            self.assertEqual(db.execute("SELECT public_key,sign_count,revoked_at "
                                        "FROM tenant_passkey_credentials WHERE credential_id=?",
                                        (b"revoked",)).fetchone(), (b"synthetic-key-b", 7, 200))
            self.assertGreater(db.execute("SELECT revoked_at FROM tenant_passkey_credentials "
                                          "WHERE credential_id=?", (b"active",)).fetchone()[0], 100)
            for table in ("tenant_identity_sessions", "tenant_passkey_challenges",
                          "tenant_signup_invites", "tenant_worker_leases"):
                self.assertEqual(db.execute("SELECT COUNT(*) FROM " + table).fetchone(), (0,))

    def test_inspection_and_cleanup_refuse_rewritten_security_history(self):
        self.prepare()
        tenant_passkeys.setup(self.path)
        orphan = str(uuid4())
        revoked = "2026-10-01T12:00:00+00:00"
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO tenant_passkey_credentials VALUES (?,?,?,?,?,?,?,?)",
                       (b"revoked", self.member, b"synthetic-key", 7, "single_device", 0, 100, 200))
            db.execute("INSERT INTO tenant_connections VALUES (?,?,?,?,?,?)",
                       (orphan, self.member, "public", b"synthetic-ciphertext", revoked, revoked))
        token, pin = self.seal()
        stage = self.orphan_stage(token, pin)
        before = self.destination.read_bytes()
        for change, values in (
                ("UPDATE tenant_passkey_credentials SET revoked_at=201", ()),
                ("UPDATE tenant_connections SET revoked_at=NULL WHERE connection_id=?", (orphan,)),
                ("UPDATE tenant_identities SET credential_version=credential_version+1", ()),
                ("UPDATE tenant_connections SET credential_ciphertext=? WHERE connection_id=?",
                 (b"changed", orphan))):
            with self.subTest(change=change):
                with closing(sqlite3.connect(self.destination)) as db, db:
                    db.execute(change, values)
                with self.assertRaises(backup.OfflineBackupDenied):
                    backup.inspect_pinned_paper_publication(
                        token, self.archive_key, self.destination, policies=self.policies,
                        trusted_pin=pin)
                with self.assertRaises(backup.OfflineBackupDenied):
                    self.cleanup(token, pin, stage)
                self.assertTrue(stage.samefile(self.destination))
                self.destination.write_bytes(before)
        self.cleanup(token, pin, stage)

    def test_quarantined_restore_refuses_saved_access_and_credentials(self):
        self.prepare()
        tenant_passkeys.setup(self.path)
        tenant_registration.setup(self.path)
        rp = "edgepilot.example.test"
        passkeys = tenant_passkeys.TenantPasskeyStore(
            self.path, self.auth, rp_id=rp, expected_origin="https://" + rp)
        challenge = passkeys.begin_authentication()["requestId"]
        invite = tenant_registration.TenantRegistration(self.path).issue_invitation()["invitation"]
        original_vault = tenant_public_vault.TenantPublicVault(
            self.path, self.auth, credential_key=self.fixture_vault_key)
        self.assertEqual(original_vault._credential_for_provider_only(
            self.session["token"], self.owner_conn), "fixture-broker-placeholder-for-owner")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO tenant_passkey_credentials VALUES (?,?,?,?,?,?,?,?)",
                       (b"synthetic-key-id", self.owner, b"synthetic-key", 1,
                        "single_device", 0, 100, None))
        token, pin = self.seal()
        stage = self.orphan_stage(token, pin)
        self.cleanup(token, pin, stage)
        auth = identity_auth.IdentityStore(self.destination)
        scopes = account_scope.AccountScopeStore(self.destination, auth)
        restored_passkeys = tenant_passkeys.TenantPasskeyStore(
            self.destination, auth, rp_id=rp, expected_origin="https://" + rp)
        vault = tenant_public_vault.TenantPublicVault(
            self.destination, auth, credential_key=self.fixture_vault_key)
        self.assertIsNone(auth.principal(self.session["token"], self.session["csrf"]))
        with self.assertRaises(tenant_passkeys.PasskeyDenied):
            restored_passkeys.begin_registration(self.session["token"], self.session["csrf"])
        with patch.object(tenant_passkeys, "_credential_json") as parse:
            with self.assertRaises(tenant_passkeys.PasskeyDenied):
                restored_passkeys.finish_authentication(challenge, {})
            parse.assert_not_called()
        fresh_challenge = restored_passkeys.begin_authentication()["requestId"]
        credential_id = "c3ludGhldGljLWtleS1pZA"
        with patch.object(tenant_passkeys, "verify_authentication_response") as verify:
            with self.assertRaises(tenant_passkeys.PasskeyDenied):
                restored_passkeys.finish_authentication(
                    fresh_challenge, {"id": credential_id, "rawId": credential_id})
            verify.assert_not_called()
        signup = tenant_registration.TenantRegistration(self.destination)
        with self.assertRaises(tenant_registration.RegistrationDenied):
            signup.register(invite, "new_member", "synthetic-new-password", "New member",
                            source="synthetic-restore")
        with self.assertRaises(tenant_public_vault.TenantVaultDenied):
            vault.list_connections(self.session["token"])
        fresh = auth.authenticate("owner", "fixture-password-for-owner", "synthetic-restore")
        self.assertIsNotNone(auth.principal(fresh["token"]))
        self.assertEqual(scopes.list_accounts(fresh["token"]), [])
        for account in (self.account, self.other):
            with self.assertRaises(tenant_foundation.TenantAccessError):
                scopes.account_summary(fresh["token"], account)
        self.assertEqual([row["status"] for row in vault.list_connections(fresh["token"])["connections"]],
                         ["revoked"])
        for connection in (self.owner_conn, self.member_conn):
            with self.assertRaises(tenant_public_vault.TenantVaultDenied):
                vault._credential_for_provider_only(fresh["token"], connection)

        member = auth.authenticate("member", "fixture-password-for-member", "synthetic-member")
        tenants = tenant_foundation.TenantStore(self.destination, self.fixture_vault_key)
        owner_secret = "synthetic-reenrolled-owner-placeholder"
        member_secret = "synthetic-reenrolled-member-placeholder"
        owner_conn = vault.save(fresh["token"], fresh["csrf"], owner_secret)["connectionId"]
        member_conn = vault.save(member["token"], member["csrf"], member_secret)["connectionId"]
        owner_account = tenants.link_account(self.owner, owner_conn, "restored-new-owner", "New owner")
        member_account = tenants.link_account(self.member, member_conn, "restored-new-member", "New member")

        for session, account, other, connection, other_conn, old_conn, secret in (
                (fresh, owner_account, member_account, owner_conn, member_conn,
                 self.owner_conn, owner_secret),
                (member, member_account, owner_account, member_conn, owner_conn,
                 self.member_conn, member_secret)):
            self.assertEqual([row["account_id"] for row in scopes.list_accounts(session["token"])],
                             [account])
            with self.assertRaises(tenant_foundation.TenantAccessError):
                scopes.account_summary(session["token"], other)
            self.assertEqual(vault._credential_for_provider_only(session["token"], connection), secret)
            with self.assertRaises(tenant_public_vault.TenantVaultDenied):
                vault._credential_for_provider_only(session["token"], other_conn)
            with self.assertRaises(tenant_public_vault.TenantVaultDenied):
                vault.rotate(session["token"], session["csrf"], old_conn, secret)

        def enroll(session, credential):
            request = restored_passkeys.begin_registration(session["token"], session["csrf"])
            verified = SimpleNamespace(credential_id=credential, credential_public_key=b"new-test-key",
                                       sign_count=0, credential_device_type="single_device",
                                       credential_backed_up=False)
            with patch.object(tenant_passkeys, "verify_registration_response", return_value=verified):
                return restored_passkeys.finish_registration(
                    session["token"], session["csrf"], request["requestId"], {})

        with self.assertRaises(tenant_passkeys.PasskeyDenied):
            enroll(fresh, b"synthetic-key-id")
        passkey_sessions = []
        for session, user, credential in ((fresh, self.owner, b"new-owner-passkey"),
                                          (member, self.member, b"new-member-passkey")):
            self.assertTrue(enroll(session, credential)["registered"])
            request_id = restored_passkeys.begin_authentication()["requestId"]
            identifier = b64url(credential)
            with patch.object(tenant_passkeys, "verify_authentication_response",
                              return_value=SimpleNamespace(new_sign_count=1, credential_backed_up=False)):
                issued = restored_passkeys.finish_authentication(
                    request_id, {"id": identifier, "rawId": identifier})
            self.assertEqual(auth.principal(issued["token"], issued["csrf"])["user_id"], user)
            passkey_sessions.append(issued)

        new_invite = signup.issue_invitation()["invitation"]
        self.assertTrue(signup.register(new_invite, "new_member", "synthetic-new-password",
                                        "New member", source="synthetic-new-invitation")["registered"])
        with self.assertRaises(tenant_registration.RegistrationDenied):
            signup.register(invite, "another_member", "synthetic-new-password", "Another member",
                            source="synthetic-restore")

        self.rehearse_second_restore(
            (token, pin), auth, restored_passkeys, signup, (fresh, member, *passkey_sessions),
            (invite, new_invite), (owner_account, member_account), (owner_conn, member_conn))

    def rehearse_second_restore(self, first_archive, auth, passkeys, signup, restored_sessions,
                                earlier_invites, accounts, connections):
        unused_invite = signup.issue_invitation()["invitation"]
        challenge = passkeys.begin_authentication()["requestId"]
        owner_account, member_account = accounts
        for user, account in ((self.owner, owner_account), (self.member, member_account)):
            ledger.open_wallet(self.destination, principal_user_id=user, account_id=account,
                               initial_paper_cash="100.00")
        shared_id = self.request["request_id"]
        for user, account, params in (
                (self.owner, owner_account, dict(request_id=shared_id, quantity="0.75")),
                (self.owner, owner_account,
                 dict(side="SELL", observation=fixtures.evidence("0.99", "1.00"))),
                (self.owner, owner_account,
                 dict(side="SELL", quantity="0.25", observation=fixtures.evidence("9.00", "9.01"))),
                (self.member, member_account, dict(request_id=shared_id))):
            result = ledger.record_paper_fill(
                self.destination, principal_user_id=user, now=datetime.now(timezone.utc),
                **self.params(account_id=account, protected_pct="90", per_trade_cap="3", **params))
            self.assertFalse(result["duplicate"])
        second_policies = self.policies | dict.fromkeys(
            [(self.owner, owner_account), (self.member, member_account)],
            PaperRestorePolicy(90, 1000, 300, 54))
        first_restore = self.destination
        request_query = (
            "SELECT user_id,account_id,request_sha256 FROM tenant_paper_events "
            "WHERE request_id=? ORDER BY user_id,account_id")
        with closing(sqlite3.connect(first_restore)) as db:
            prior_digest = backup._paper_data_digest(db)
            request_rows = db.execute(request_query, (shared_id,)).fetchall()
            self.assertEqual({(u, a) for u, a, _ in request_rows}, {
                (self.owner, self.account), (self.owner, owner_account),
                (self.member, member_account)})
            self.assertEqual(len({digest for _, _, digest in request_rows}), 3)
            prior_scope = backup._paper_scope(db)
            prior_passkeys = dict(db.execute("SELECT credential_id,revoked_at FROM tenant_passkey_credentials"))
            prior_connections = dict(db.execute("SELECT connection_id,revoked_at FROM tenant_connections"))
        second_token, second_pin = backup.seal_pinned_paper_fixture(
            first_restore, self.archive_key, policies=second_policies)
        self.destination = first_restore.with_name("restored-again.db")
        first_token, first_pin = first_archive
        for token, pin, policies in ((second_token, first_pin, second_policies),
                                     (first_token, second_pin, self.policies),
                                     (first_token, second_pin, second_policies)):
            with self.assertRaises(backup.OfflineBackupDenied):
                self.restore(token, pin, policies)
            self.assertFalse(self.destination.exists())
        self.assertEqual(self.restore(second_token, second_pin, second_policies), self.destination)
        self.assertEqual(backup.inspect_pinned_paper_publication(
            second_token, self.archive_key, self.destination, policies=second_policies,
            trusted_pin=second_pin), {"quarantineVerified": True, "additionalLinkPresent": False})
        with closing(sqlite3.connect(self.destination)) as db:
            self.assertEqual(backup._paper_data_digest(db), prior_digest)
            self.assertEqual(db.execute(request_query, (shared_id,)).fetchall(), request_rows)
            for user, account, expected in (
                    (self.owner, self.account, (119, -54, 2)),
                    (self.owner, self.alternate, (0, 0, 0)),
                    (self.owner, owner_account, (119, -54, 2)),
                    (self.member, self.other, (0, 0, 0)),
                    (self.member, member_account, (0, 0, 0))):
                with self.subTest(user=user, account=account):
                    self.assertEqual(_replay_realized(db.execute(
                        "SELECT side,asset_class,symbol,quantity,signed_cash_change_cents "
                        "FROM tenant_paper_events WHERE user_id=? AND account_id=? ORDER BY rowid",
                        (user, account))), expected)
            for before, after in zip(prior_scope, backup._paper_scope(db), strict=True):
                self.assertEqual(before[:-2], after[:-2])
                for old, current in zip(before[-2:], after[-2:], strict=True):
                    self.assertTrue(current)
                    if old is not None:
                        self.assertEqual(current, old)
            for query, original in (
                    ("SELECT credential_id,revoked_at FROM tenant_passkey_credentials", prior_passkeys),
                    ("SELECT connection_id,revoked_at FROM tenant_connections", prior_connections)):
                current = dict(db.execute(query))
                self.assertEqual(current.keys(), original.keys())
                for key, value in original.items():
                    self.assertTrue(current[key])
                    if value is not None:
                        self.assertEqual(current[key], value)

        second_auth = identity_auth.IdentityStore(self.destination)
        for session in restored_sessions:
            self.assertIsNotNone(auth.principal(session["token"], session["csrf"]))
        for session in (self.session, self.other_session, *restored_sessions):
            self.assertIsNone(second_auth.principal(session["token"], session["csrf"]))
        second_passkeys = tenant_passkeys.TenantPasskeyStore(
            self.destination, second_auth, rp_id=passkeys.rp_id, expected_origin=passkeys.origin)
        with patch.object(tenant_passkeys, "_credential_json") as parse:
            with self.assertRaises(tenant_passkeys.PasskeyDenied):
                second_passkeys.finish_authentication(challenge, {})
            parse.assert_not_called()
        second_signup = tenant_registration.TenantRegistration(self.destination)
        for denied_invite in (*earlier_invites, unused_invite):
            with self.assertRaises(tenant_registration.RegistrationDenied):
                second_signup.register(denied_invite, "another_member", "synthetic-new-password",
                                       "Another member", source="synthetic-second-restore")
        second_vault = tenant_public_vault.TenantPublicVault(
            self.destination, second_auth, credential_key=self.fixture_vault_key)
        second_scopes = account_scope.AccountScopeStore(self.destination, second_auth)
        for login, connection in zip(("owner", "member"), connections, strict=True):
            session = second_auth.authenticate(login, "fixture-password-for-" + login,
                                               "synthetic-second-restore-" + login)
            self.assertEqual(second_scopes.list_accounts(session["token"]), [])
            with self.assertRaises(tenant_public_vault.TenantVaultDenied):
                second_vault._credential_for_provider_only(session["token"], connection)
