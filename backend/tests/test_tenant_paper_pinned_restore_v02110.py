"""Encrypted recovery of marked synthetic tenant scopes and immutable policies."""
from contextlib import closing
from datetime import datetime, timezone
import sqlite3
import unittest
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
