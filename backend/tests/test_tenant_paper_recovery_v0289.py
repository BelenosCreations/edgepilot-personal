"""v0.2.89: encrypted synthetic paper-ledger restore, quarantine and tamper gates."""
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from engine import (
    account_scope, identity_auth, tenant_backup_rehearsal,
    tenant_foundation, tenant_paper_ledger as paper,
    tenant_paper_recovery_audit as audit, tenant_passkeys,
    tenant_registration,
)

NOW = "2026-11-12T20:00:00Z"


def quote():
    return {
        "assetClass": "stock", "symbol": "RESTORE-TEST",
        "rights": {"provider": "SYNTHETIC-NO-NETWORK", "analysis": True,
                   "cache": True, "redistribute": False,
                   "coverageVerified": True},
        "observedAt": "2026-11-12T19:59:55Z",
        "receivedAt": "2026-11-12T19:59:58Z",
        "bid": "1.99", "ask": "2.00", "last": "2.00",
        "volume": "100", "state": "open",
    }


class PaperRecoveryRehearsal(unittest.TestCase):
    def setUp(self):
        # Existing isolated archive contract requires verified Linux tmpfs.
        self.tmp = tempfile.TemporaryDirectory(
            prefix="edgepilot-paper-v0289-", dir="/dev/shm")
        self.path = Path(self.tmp.name) / "source.db"
        self.key = Fernet.generate_key()
        self.vault = Fernet.generate_key()
        tenant_foundation.setup(self.path)
        identity_auth.setup(self.path)
        account_scope.setup(self.path)
        tenant_passkeys.setup(self.path)
        tenant_registration.setup(self.path)
        store = tenant_foundation.TenantStore(
            self.path, credential_key=self.vault)
        self.owner = store.provision_user("Synthetic owner", "owner")
        self.member = store.provision_user("Synthetic family", "member")
        owner_link = store.add_connection(
            self.owner, "SYNTHETIC-NOT-PUBLIC-OWNER-123456789")
        family_link = store.add_connection(
            self.member, "SYNTHETIC-NOT-PUBLIC-FAMILY-123456789")
        self.primary = store.link_account(
            self.owner, owner_link, "FAKE-O1", "Primary")
        self.secondary = store.link_account(
            self.owner, owner_link, "FAKE-O2", "Secondary")
        self.foreign = store.link_account(
            self.member, family_link, "FAKE-F1", "Family")
        paper.prepare(self.path)
        for who, account, seed in (
            (self.owner, self.primary, "100.00"),
            (self.owner, self.secondary, "25.00"),
            (self.member, self.foreign, "40.00"),
        ):
            paper.open_wallet(
                self.path, principal_user_id=who, account_id=account,
                initial_paper_cash=seed)
        self.fill(self.owner, self.primary, "BUY", "2")
        self.fill(self.owner, self.primary, "SELL", "1")
        self.fill(self.member, self.foreign, "BUY", "1")

    def tearDown(self):
        self.tmp.cleanup()

    def fill(self, user, account, side, qty):
        return paper.record_paper_fill(
            self.path, principal_user_id=user, account_id=account,
            request_id=str(uuid.uuid4()), side=side, observation=quote(),
            now=NOW, quantity=qty, fee_per_unit="0.02",
            slippage_per_unit="0.01", protected_pct="80",
            spend_cap="100", per_trade_cap="20",
        )

    def check(self):
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA foreign_keys=ON")
            return audit.audit_tenant_paper_ledger(db)

    def test_encrypted_roundtrip_retains_synthetic_paper_history_but_quarantines(self):
        self.assertEqual(self.check(), {
            "paperSchemaPresent": True, "verifiedWallets": 3,
            "verifiedAssumedFills": 3})
        token = tenant_backup_rehearsal.sealed_snapshot(self.path, self.key)
        self.assertNotIn(b"SQLite format 3", token)
        self.assertNotIn(b"SYNTHETIC-NOT-PUBLIC", token)
        restored = tenant_backup_rehearsal.restore_sealed_fixture(
            token, self.key, Path(self.tmp.name) / "restored.db")
        self.assertEqual(restored.stat().st_mode & 0o777, 0o600)
        with sqlite3.connect(restored) as db:
            db.execute("PRAGMA foreign_keys=ON")
            result = audit.audit_tenant_paper_ledger(db)
            self.assertEqual(result["verifiedAssumedFills"], 3)
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0],
                             "ok")
            self.assertIsNone(db.execute("PRAGMA foreign_key_check").fetchone())
            states = db.execute("""SELECT a.account_id,a.disabled_at,
                c.revoked_at FROM tenant_accounts a
                JOIN tenant_connections c ON a.connection_id=c.connection_id
                ORDER BY a.account_id""").fetchall()
            self.assertEqual(len(states), 3)
            self.assertTrue(all(disabled and revoked
                                for _, disabled, revoked in states))
            wallets = db.execute("""SELECT user_id,account_id,cash_cents
                FROM tenant_paper_wallets""").fetchall()
            self.assertEqual({(u, a): cents for u, a, cents in wallets}, {
                (self.owner, self.primary): 9790,
                (self.owner, self.secondary): 2500,
                (self.member, self.foreign): 3797,
            })
        # No restored paper data becomes readable or writable while the
        # original brokerage-account binding remains quarantined.
        for user, account in (
            (self.owner, self.primary), (self.owner, self.secondary),
            (self.member, self.foreign), (self.member, self.primary),
            (self.owner, self.foreign),
        ):
            with self.subTest(user=user, account=account):
                with self.assertRaises(paper.PaperLedgerDenied):
                    paper.snapshot(restored, principal_user_id=user,
                                   account_id=account)
                with self.assertRaises(paper.PaperLedgerDenied):
                    paper.open_wallet(restored, principal_user_id=user,
                                      account_id=account,
                                      initial_paper_cash="100.00")

    def test_modified_cash_or_position_denied_before_sealing(self):
        with sqlite3.connect(self.path) as db:
            db.execute("""UPDATE tenant_paper_events
                SET cash_after_cents=cash_after_cents+1
                WHERE rowid=(SELECT MIN(rowid) FROM tenant_paper_events)""")
        with self.assertRaises(audit.PaperRecoveryDenied):
            self.check()
        with self.assertRaises(tenant_backup_rehearsal.OfflineBackupDenied):
            tenant_backup_rehearsal.sealed_snapshot(self.path, self.key)
        # Repair only the synthetic fixture, then prove position tampering
        # is also rejected even when all SQLite foreign keys still pass.
        with sqlite3.connect(self.path) as db:
            db.execute("""UPDATE tenant_paper_events
                SET cash_after_cents=cash_after_cents-1
                WHERE rowid=(SELECT MIN(rowid) FROM tenant_paper_events)""")
            db.execute("""UPDATE tenant_paper_positions
                SET cost_basis_cents=cost_basis_cents+1
                WHERE user_id=? AND account_id=?""",
                       (self.owner, self.primary))
        with self.assertRaises(audit.PaperRecoveryDenied):
            self.check()
        with self.assertRaises(tenant_backup_rehearsal.OfflineBackupDenied):
            tenant_backup_rehearsal.sealed_snapshot(self.path, self.key)

    def test_partial_paper_schema_denied_without_touching_other_tables(self):
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TABLE tenant_paper_positions")
        with self.assertRaises(audit.PaperRecoveryDenied):
            self.check()
        with self.assertRaises(tenant_backup_rehearsal.OfflineBackupDenied):
            tenant_backup_rehearsal.sealed_snapshot(self.path, self.key)

    def test_full_length_valid_instrument_identifier_survives_recovery(self):
        unusual = quote()
        unusual["symbol"] = "LONG-SOURCE-IDENTIFIER.WITH-SAFE-CHARACTERS-123456789"
        paper.record_paper_fill(
            self.path, principal_user_id=self.owner, account_id=self.primary,
            request_id=str(uuid.uuid4()), side="BUY", observation=unusual,
            now=NOW, quantity="1", fee_per_unit="0.02",
            slippage_per_unit="0.01", protected_pct="80",
            spend_cap="100", per_trade_cap="20")
        self.assertEqual(self.check()["verifiedAssumedFills"], 4)
        token = tenant_backup_rehearsal.sealed_snapshot(self.path, self.key)
        self.assertTrue(token)

    def test_atomic_restore_never_overwrites_existing_destination(self):
        token = tenant_backup_rehearsal.sealed_snapshot(self.path, self.key)
        existing = Path(self.tmp.name) / "important-existing.db"
        existing.write_bytes(b"EXISTING-DESTINATION-UNTOUCHED")
        with self.assertRaises(tenant_backup_rehearsal.OfflineBackupDenied):
            tenant_backup_rehearsal.restore_sealed_fixture(
                token, self.key, existing)
        self.assertEqual(existing.read_bytes(), b"EXISTING-DESTINATION-UNTOUCHED")
        self.assertEqual(list(Path(self.tmp.name).glob(
            ".edgepilot-synthetic-restore-*")), [])

    def test_atomic_restore_rolls_back_before_publication(self):
        token = tenant_backup_rehearsal.sealed_snapshot(self.path, self.key)
        # Source decrypts but the SQLite payload is an invalid authenticated
        # synthetic archive. The final path must not exist even briefly.
        malformed = Fernet(self.key).encrypt(
            tenant_backup_rehearsal._MAGIC +
            b"SQLite format 3\\x00" + b"invalid-synthetic-database")
        for label, blob in (("bad-sqlite", malformed),
                            ("wrong-key", token)):
            dest = Path(self.tmp.name) / (label + ".db")
            key = Fernet.generate_key() if label == "wrong-key" else self.key
            with self.assertRaises(tenant_backup_rehearsal.OfflineBackupDenied):
                tenant_backup_rehearsal.restore_sealed_fixture(blob, key, dest)
            self.assertFalse(dest.exists())
        self.assertEqual(list(Path(self.tmp.name).glob(
            ".edgepilot-synthetic-restore-*")), [])

    def test_atomic_restore_refuses_publication_race_or_fsync_failure(self):
        token = tenant_backup_rehearsal.sealed_snapshot(self.path, self.key)
        for label, target_method, failure in (
            ("link-race", "link", FileExistsError("synthetic collision")),
            ("fsync", "fsync", OSError("synthetic disk failure")),
        ):
            dest = Path(self.tmp.name) / (label + ".db")
            with self.subTest(label=label):
                with patch.object(tenant_backup_rehearsal.os, target_method,
                                  side_effect=failure):
                    with self.assertRaises(tenant_backup_rehearsal.OfflineBackupDenied):
                        tenant_backup_rehearsal.restore_sealed_fixture(
                            token, self.key, dest)
                self.assertFalse(dest.exists())
                self.assertEqual(list(Path(self.tmp.name).glob(
                    ".edgepilot-synthetic-restore-*")), [])

    def test_failed_quarantine_before_publication_leaves_no_final_file(self):
        token = tenant_backup_rehearsal.sealed_snapshot(self.path, self.key)
        dest = Path(self.tmp.name) / "failed-quarantine.db"
        original = tenant_backup_rehearsal._check_contents
        def force_rollback(db, *, require_quiescent):
            if require_quiescent:
                raise tenant_backup_rehearsal.OfflineBackupDenied(
                    "Synthetic injected quarantine interruption")
            return original(db, require_quiescent=require_quiescent)
        with patch.object(tenant_backup_rehearsal, "_check_contents",
                          side_effect=force_rollback):
            with self.assertRaises(tenant_backup_rehearsal.OfflineBackupDenied):
                tenant_backup_rehearsal.restore_sealed_fixture(
                    token, self.key, dest)
        self.assertFalse(dest.exists())
        self.assertEqual(list(Path(self.tmp.name).glob(
            ".edgepilot-synthetic-restore-*")), [])

    def test_paper_restore_never_adds_http_or_production_migration(self):
        app = (Path(__file__).resolve().parents[1] / "app.py").read_text()
        self.assertNotIn("tenant_paper_recovery_audit", app)
        self.assertNotIn("tenant_paper_ledger", app)
        self.assertNotIn("/api/identity/paper/fill", app)


if __name__ == "__main__":
    unittest.main()
