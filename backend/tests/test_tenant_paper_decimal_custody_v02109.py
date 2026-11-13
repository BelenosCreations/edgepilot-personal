"""Separate synthetic custody database and volatile ledger fixtures."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from engine import tenant_paper_decimal_atomic_rehearsal as ledger
from engine import tenant_paper_decimal_custody as custody
from engine import tenant_paper_decimal_recovery as recovery


class DecimalCustodyTests(unittest.TestCase):
    def setUp(self):
        fixture = tempfile.TemporaryDirectory(dir="/dev/shm", prefix="decimal-custody-fixture-")
        witness = tempfile.TemporaryDirectory(prefix="decimal-custody-witness-")
        self.addCleanup(fixture.cleanup)
        self.addCleanup(witness.cleanup)
        self.path = Path(fixture.name) / "fixture.db"
        self.old = Path(fixture.name) / "old.db"
        self.store_path = Path(witness.name) / "witness.db"
        self.store_copy = Path(witness.name) / "prior.db"
        self.journal, self.anchor, self.operator, self.replacement, self.custody = (
            os.urandom(32) for _ in range(5))
        self.keys = dict(journal_key=self.journal, anchor_key=self.anchor, operator_key=self.operator)
        ledger.create_decimal_fixture(self.path)
        self.scope = dict(principal_user_id=str(uuid4()), account_id=str(uuid4()))
        ledger.register_decimal_account(
            self.path, hmac_key=self.journal, initial_cash_cents=10000, protected_pct=90,
            spend_cap_cents=2000, per_trade_cap_cents=800, max_loss_cents=14, **self.scope)
        self.active = recovery.establish_decimal_recovery(self.path, **self.keys)
        self.store, self.genesis = custody.DecimalCustody.create(
            self.store_path, genesis=self.active, custody_key=self.custody,
            operator_key=self.operator)

    def prepare(self):
        return recovery.prepare_decimal_rotation(
            self.path, record=self.active, trusted_tip=recovery.evidence_tip(self.active),
            replacement_key=self.replacement, **self.keys)

    def rotate(self, receipt, **kwargs):
        return self.store.rotate(
            self.path, expected_receipt=receipt, journal_key=self.journal,
            replacement_key=self.replacement, anchor_key=self.anchor, **kwargs)

    def inspect(self, record, key):
        return recovery.inspect_decimal_recovery(
            self.path, record=record, trusted_tip=recovery.evidence_tip(record),
            **(self.keys | {"journal_key": key}))

    def test_compare_and_swap_allows_one_concurrent_publisher(self):
        pending = self.prepare()
        with ThreadPoolExecutor(max_workers=2) as pool:
            attempts = [pool.submit(self.store.publish, pending, expected_receipt=self.genesis)
                        for _ in range(2)]
        accepted = [future.result() for future in attempts if future.exception() is None]
        self.assertEqual(len(accepted), 1)
        self.assertEqual(self.store.read(trusted_receipt=self.genesis),
                         (pending, accepted[0], False))
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.store.publish(pending, expected_receipt=self.genesis)

    def test_interrupted_publication_readback_distinguishes_commit(self):
        pending = self.prepare()
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.store.publish(pending, expected_receipt=self.genesis, _interrupt="before_commit")
        self.assertEqual(self.store.read(trusted_receipt=self.genesis),
                         (self.active, self.genesis, False))
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.store.publish(pending, expected_receipt=self.genesis, _interrupt="after_commit")
        reopened = custody.DecimalCustody(
            self.store_path, custody_key=self.custody, operator_key=self.operator)
        record, receipt, claimed = reopened.read(trusted_receipt=self.genesis)
        self.assertEqual(record, pending)
        self.assertEqual(receipt["number"], 2)
        self.assertFalse(claimed)

    def test_claim_survives_interruption_and_old_fixture_cannot_be_replayed(self):
        pending = self.prepare()
        receipt = self.store.publish(pending, expected_receipt=self.genesis)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.rotate(receipt, _interrupt="after_claim")
        record, claim, claimed = self.store.read(trusted_receipt=receipt)
        self.assertTrue(claimed)
        self.assertEqual(self.inspect(record, self.journal), "AMBIGUOUS_OLD_STATE")
        for stale in (receipt, claim):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                self.rotate(stale)
        hold = recovery.quarantine_decimal_recovery(
            record=record, trusted_tip=recovery.evidence_tip(record),
            operator_key=self.operator, reason="AMBIGUOUS_OLD_STATE")
        end = self.store.publish(hold, expected_receipt=claim)
        self.assertEqual(self.store.read(trusted_receipt=end)[0]["status"], "QUARANTINED")

    def test_ledger_rollback_does_not_clear_rotation_claim(self):
        pending = self.prepare()
        receipt = self.store.publish(pending, expected_receipt=self.genesis)
        before = self.path.read_bytes()
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.rotate(receipt, _interrupt="before_ledger_commit")
        self.assertEqual(self.path.read_bytes(), before)
        record, claim, claimed = self.store.read(trusted_receipt=receipt)
        self.assertTrue(claimed)
        self.assertEqual(self.inspect(record, self.journal), "AMBIGUOUS_OLD_STATE")
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.rotate(claim)

    def test_committed_rotation_requires_exact_target_and_explicit_promotion(self):
        pending = self.prepare()
        receipt = self.store.publish(pending, expected_receipt=self.genesis)
        shutil.copy2(self.path, self.old)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.rotate(receipt, _interrupt="after_ledger_commit")
        record, claim, claimed = self.store.read(trusted_receipt=receipt)
        self.assertTrue(claimed)
        self.assertEqual(self.inspect(record, self.replacement), "PREPARED_TARGET_REQUIRES_APPROVAL")
        self.assertEqual(recovery.inspect_decimal_recovery(
            self.old, record=record, trusted_tip=recovery.evidence_tip(record), **self.keys),
            "AMBIGUOUS_OLD_STATE")
        promoted = recovery.approve_decimal_promotion(
            self.path, record=record, trusted_tip=recovery.evidence_tip(record),
            **(self.keys | {"journal_key": self.replacement}))
        end = self.store.publish(promoted, expected_receipt=claim)
        self.assertEqual(self.store.read(trusted_receipt=end), (promoted, end, False))
        self.assertEqual(self.inspect(promoted, self.replacement), "PINNED_ACTIVE")

    def test_refuses_wrong_lineage_invalid_transition_and_rolled_back_witness(self):
        shutil.copy2(self.store_path, self.store_copy)
        pending = self.prepare()
        wrong = recovery._record(
            self.operator, sequence=2, fixture_id=str(uuid4()), previous=self.active["mac"],
            status=pending["status"], current=pending["current"], target=pending["target"])
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.store.publish(wrong, expected_receipt=self.genesis)
        fake_promotion = recovery._next(self.operator, self.active, "ACTIVE")
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.store.publish(fake_promotion, expected_receipt=self.genesis)
        tip = self.store.publish(pending, expected_receipt=self.genesis)
        shutil.copy2(self.store_copy, self.store_path)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.store.read(trusted_receipt=tip)

    def test_tampered_publication_and_wrong_custody_key_fail(self):
        with sqlite3.connect(self.store_path) as db:
            db.execute("UPDATE custody_events SET payload='{}' WHERE number=1")
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.store.read(trusted_receipt=self.genesis)
        wrong = custody.DecimalCustody(
            self.store_path, custody_key=os.urandom(32), operator_key=self.operator)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            wrong.read(trusted_receipt=self.genesis)


    def test_process_exit_leaves_independently_readable_claim(self):
        pending = self.prepare()
        receipt = self.store.publish(pending, expected_receipt=self.genesis)
        pid = os.fork()
        if pid == 0:
            try:
                # Exit after claiming the rotation while the custody write
                # lock is held. The synthetic ledger has never been opened.
                with patch.object(recovery, "execute_prepared_decimal_rotation",
                                  side_effect=lambda *a, **k: os._exit(86)):
                    self.rotate(receipt)
            finally:
                os._exit(87)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 86)
        record, claim, claimed = self.store.read(trusted_receipt=receipt)
        self.assertTrue(claimed)
        self.assertEqual(self.inspect(record, self.journal), "AMBIGUOUS_OLD_STATE")
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.rotate(claim)

    def test_wrong_anchor_does_not_consume_rotation_claim(self):
        pending = self.prepare()
        receipt = self.store.publish(pending, expected_receipt=self.genesis)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.store.rotate(self.path, expected_receipt=receipt, journal_key=self.journal,
                              replacement_key=self.replacement, anchor_key=os.urandom(32))
        self.assertEqual(self.store.read(trusted_receipt=receipt), (pending, receipt, False))
