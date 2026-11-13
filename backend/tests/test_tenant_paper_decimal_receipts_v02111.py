"""Exercise independent offline receipt retention and process-loss boundaries."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet

from engine import tenant_paper_decimal_archive as archive
from engine import tenant_paper_decimal_receipts as receipts
from engine import tenant_paper_decimal_recovery as recovery
import test_tenant_paper_decimal_custody_v02109 as fixtures


class IndependentReceiptTests(unittest.TestCase):
    prepare = fixtures.DecimalCustodyTests.prepare
    inspect = fixtures.DecimalCustodyTests.inspect

    def setUp(self):
        fixtures.DecimalCustodyTests.setUp(self)
        receipt_folder = tempfile.TemporaryDirectory(prefix="decimal-independent-receipts-")
        self.addCleanup(receipt_folder.cleanup)
        self.pin_path = Path(receipt_folder.name) / "receipt.db"
        self.pin_key = os.urandom(32)
        self.pins = receipts.DecimalReceiptStore.create(
            self.pin_path, receipt_key=self.pin_key, witness=self.store, genesis=self.genesis)
        self.pending = self.prepare()
        self.prepared = self.pins.publish(self.store, self.pending)
        self.before = self.path.read_bytes()

    def rotate(self):
        return self.pins.rotate(
            self.store, self.path, journal_key=self.journal,
            replacement_key=self.replacement, anchor_key=self.anchor)

    def recover(self, snapshot, key=None):
        return self.pins.recover_witness(
            self.store, snapshot, ledger_path=self.path,
            journal_key=self.journal if key is None else key, anchor_key=self.anchor)

    def assert_no_retry(self):
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.rotate()
        self.assertEqual(self.path.read_bytes(), self.before)
        self.assertEqual(self.inspect(self.pending, self.journal), "AMBIGUOUS_OLD_STATE")

    def test_independent_pin_survives_reopen_and_allows_one_concurrent_claim(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            attempts = [pool.submit(self.rotate) for _ in range(2)]
        results = [future.result() for future in attempts if future.exception() is None]
        self.assertEqual(len(results), 1)
        self.assertEqual(sum(isinstance(future.exception(), recovery.DecimalRecoveryDenied)
                             for future in attempts), 1)
        claim = results[0]
        reopened = receipts.DecimalReceiptStore(self.pin_path, receipt_key=self.pin_key)
        self.assertEqual(reopened.latest(), claim)
        self.assertEqual(claim["number"], self.prepared["number"] + 1)
        self.assertEqual(self.inspect(self.pending, self.replacement),
                         "PREPARED_TARGET_REQUIRES_APPROVAL")
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            reopened.publish(self.store, self.pending)
        snapshot = self.store.backup(expected_receipt=claim)
        self.store_path.unlink()
        self.store = self.recover(snapshot, self.replacement)
        promotion = recovery.approve_decimal_promotion(
            self.path, record=self.pending, trusted_tip=recovery.evidence_tip(self.pending),
            **(self.keys | {"journal_key": self.replacement}))
        tip = reopened.publish(self.store, promotion)
        self.assertEqual(reopened.latest(), tip)
        self.assertEqual(self.inspect(promotion, self.replacement), "PINNED_ACTIVE")

    def test_process_exit_before_receipt_ack_leaves_persistent_reservation(self):
        snapshot = self.store.backup(expected_receipt=self.prepared)
        pid = os.fork()
        if pid == 0:
            try:
                with patch.object(self.pins, "_retain_claim", side_effect=lambda *_: os._exit(81)):
                    self.rotate()
            finally:
                os._exit(82)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 81)
        _, claim, claimed = self.store.read(trusted_receipt=self.prepared)
        self.assertTrue(claimed)
        self.assertEqual(claim["number"], self.prepared["number"] + 1)
        reopened = receipts.DecimalReceiptStore(self.pin_path, receipt_key=self.pin_key)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            reopened.latest()
        self.assert_no_retry()
        self.store_path.unlink()
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.recover(snapshot)
        self.assertFalse(self.store_path.exists())

    def test_lost_ack_after_retention_never_writes_or_accepts_older_resources(self):
        old_snapshot = self.store.backup(expected_receipt=self.prepared)
        shutil.copy2(self.store_path, self.store_copy)
        retain = self.pins._retain_claim

        def lose_reply(expected, claim):
            retain(expected, claim)
            raise ConnectionError

        with patch.object(self.pins, "_retain_claim", side_effect=lose_reply):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                self.rotate()
        claim = self.pins.latest()
        snapshot = self.store.backup(expected_receipt=claim)
        shutil.copy2(self.store_copy, self.store_path)
        self.assert_no_retry()
        self.store_path.unlink()
        for candidate in (old_snapshot, snapshot):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                self.recover(candidate)
            self.assertFalse(self.store_path.exists())

    def test_loss_of_receipt_or_witness_after_claim_ack_blocks_ledger_write(self):
        for resource in (self.pin_path, self.store_path):
            with self.subTest(resource=resource.name):
                witness_copy = self.store_path.read_bytes()
                pin_copy = self.pin_path.read_bytes()
                retain = self.pins._retain_claim

                def remove_after_retain(expected, claim):
                    result = retain(expected, claim)
                    resource.unlink()
                    return result

                with patch.object(self.pins, "_retain_claim", side_effect=remove_after_retain):
                    with self.assertRaises(recovery.DecimalRecoveryDenied):
                        self.rotate()
                self.assert_no_retry()
                # Reset both private synthetic files for the other loss scenario.
                self.store_path.touch(mode=0o600, exist_ok=True)
                self.store_path.write_bytes(witness_copy)
                self.pin_path.touch(mode=0o600, exist_ok=True)
                self.pin_path.write_bytes(pin_copy)

    def test_lost_ledger_during_handoff_cannot_restore_old_ciphertext(self):
        key = Fernet.generate_key()
        destination = self.path.with_name("recovered.db")
        token = archive.seal_decimal_archive(
            self.path, record=self.active, trusted_tip=recovery.evidence_tip(self.active),
            archive_key=key, **self.keys)
        approval = archive.approve_decimal_restore(
            token, destination, record=self.active, trusted_tip=recovery.evidence_tip(self.active),
            operator_key=self.operator)
        retain = self.pins._retain_claim

        def remove_ledger(expected, claim):
            self.path.unlink()
            return retain(expected, claim)

        with patch.object(self.pins, "_retain_claim", side_effect=remove_ledger):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                self.rotate()
        claim = self.pins.latest()
        self.assertTrue(self.store.read(trusted_receipt=claim)[2])
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.pins.restore_ledger(
                self.store, token, destination, approval=approval, archive_key=key,
                journal_key=self.journal, anchor_key=self.anchor)
        self.assertFalse(self.path.exists())
        self.assertFalse(destination.exists())

    def test_ambiguous_record_publication_freezes_pin_without_retry(self):
        quarantine = recovery.quarantine_decimal_recovery(
            record=self.pending, trusted_tip=recovery.evidence_tip(self.pending),
            operator_key=self.operator, reason="INTEGRITY_FAILURE")
        publish = self.store.publish
        with patch.object(self.store, "publish", side_effect=lambda proposed, **kwargs:
                          publish(proposed, _interrupt="after_commit", **kwargs)):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                self.pins.publish(self.store, quarantine)
        self.assertEqual(self.store.read(trusted_receipt=self.prepared)[0], quarantine)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.pins.latest()
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.pins.publish(self.store, quarantine)
        self.assert_no_retry()

    def test_reservation_survives_failure_before_witness_write(self):
        with patch.object(self.store, "rotate", side_effect=recovery.DecimalRecoveryDenied):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                self.rotate()
        self.assertEqual(self.store.read(trusted_receipt=self.prepared),
                         (self.pending, self.prepared, False))
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.pins.latest()
        self.assert_no_retry()

    def test_tampered_or_wrong_key_pin_cannot_authorize_witness_or_ledger(self):
        wrong = receipts.DecimalReceiptStore(self.pin_path, receipt_key=self.operator)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            wrong.latest()
        with closing(sqlite3.connect(self.pin_path)) as db, db:
            db.execute("UPDATE retained_receipt SET number=number+1")
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.pins.latest()
        self.assert_no_retry()

    def freeze_after_claim(self):
        with patch.object(self.pins, "_retain_claim", side_effect=ConnectionError):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                self.rotate()
        record, claim, consumed = self.store.read(trusted_receipt=self.prepared)
        self.assertTrue(consumed)
        hold = recovery.quarantine_decimal_recovery(
            record=record, trusted_tip=recovery.evidence_tip(record),
            operator_key=self.operator, reason="AMBIGUOUS_OLD_STATE")
        return claim, hold

    def resolve(self, observed, record, *, reserved=None):
        return self.pins.quarantine_frozen(
            self.store, reserved_receipt=self.prepared if reserved is None else reserved,
            observed_receipt=observed, operator_record=record)

    def test_frozen_handoff_needs_exact_receipts_and_signed_quarantine(self):
        claim, hold = self.freeze_after_claim()
        for observed, record, reserved in (
                (self.prepared, hold, self.prepared),
                (claim, hold, self.genesis),
                (claim, self.pending, self.prepared),
                (claim, {**hold, "quarantineReason": "INTEGRITY_FAILURE"}, self.prepared)):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                self.resolve(observed, record, reserved=reserved)
        tip = self.resolve(claim, hold)
        self.assertEqual(self.pins.latest(), tip)
        self.assertEqual(self.store.read(trusted_receipt=tip)[0], hold)
        self.assertEqual(self.path.read_bytes(), self.before)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.resolve(tip, hold)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.rotate()

    def test_quarantine_lost_reply_can_only_retain_exact_terminal_record(self):
        claim, hold = self.freeze_after_claim()
        with patch.object(self.pins, "_save", side_effect=OSError):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                self.resolve(claim, hold)
        terminal, tip, _ = self.store.read(trusted_receipt=claim)
        self.assertEqual(terminal, hold)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.pins.latest()
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.resolve(claim, hold)
        self.assertEqual(self.resolve(tip, hold), tip)
        self.assertEqual(self.pins.latest(), tip)
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_recreated_ledger_during_receipt_handoff_cannot_be_rotated(self):
        old_path = self.path.with_suffix(".saved")
        retain = self.pins._retain_claim

        def replace_ledger(expected, claim):
            result = retain(expected, claim)
            self.path.rename(old_path)
            shutil.copy2(old_path, self.path)
            return result

        with patch.object(self.pins, "_retain_claim", side_effect=replace_ledger):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                self.rotate()
        self.assert_no_retry()
