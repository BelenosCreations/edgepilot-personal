"""Encrypted recovery of marked synthetic tenant scopes and immutable policies."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
import fcntl
import os
import sqlite3
from threading import Barrier
import unittest
from unittest.mock import patch
from uuid import uuid4

from cryptography.fernet import Fernet

from engine import account_scope
from engine import tenant_backup_rehearsal as backup
from engine import tenant_paper_authenticated_preflight as preflight
from engine import tenant_paper_ledger as ledger
from engine.tenant_paper_loss_stop import _replay_realized
from engine.tenant_paper_recovery_audit import PaperRestorePolicy
import test_tenant_paper_authenticated_preflight_v02107 as fixtures


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
