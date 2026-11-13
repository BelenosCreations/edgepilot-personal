"""Exercise independently retained promotion evidence under synthetic rollback."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engine import tenant_paper_decimal_receipts as receipts
from engine import tenant_paper_decimal_recovery as recovery
import test_tenant_paper_decimal_receipts_v02111 as fixtures


class PromotionCheckpointTests(unittest.TestCase):
    setUp = fixtures.IndependentReceiptTests.setUp
    prepare = fixtures.IndependentReceiptTests.prepare
    rotate = fixtures.IndependentReceiptTests.rotate
    approve_prepared = fixtures.IndependentReceiptTests.approve_prepared

    def prepare_checkpoint(self):
        # Retain a copy of the reservation, complete one rotation, then
        # simulate loss of its local receipt-store update for operator review.
        retain = self.pins._retain_claim
        frozen = []

        def capture_reservation(expected, claim):
            frozen.append(self.pin_path.read_bytes())
            return retain(expected, claim)

        with patch.object(self.pins, "_retain_claim", side_effect=capture_reservation):
            self.claim = self.rotate()
        self.pin_path.write_bytes(frozen[0])
        self.promotion = self.approve_prepared(self.path, self.pending, self.replacement)
        folder = tempfile.TemporaryDirectory(prefix="decimal-promotion-checkpoint-")
        self.addCleanup(folder.cleanup)
        self.checkpoint_path = Path(folder.name) / "checkpoint.db"
        self.checkpoint_key = os.urandom(32)
        self.checkpoint = receipts.DecimalPromotionCheckpoint.create(
            self.checkpoint_path, checkpoint_key=self.checkpoint_key, receipts=self.pins,
            witness=self.store, reserved_receipt=self.prepared, prepared_receipt=self.claim)

    def promote(self):
        return self.pins.promote_frozen(
            self.store, self.path, reserved_receipt=self.prepared, prepared_receipt=self.claim,
            operator_record=self.promotion, journal_key=self.replacement, anchor_key=self.anchor,
            checkpoint=self.checkpoint)

    def test_external_checkpoint_refuses_rollback_of_witness_or_ledger(self):
        self.prepare_checkpoint()
        paths = (self.pin_path, self.store_path, self.path)
        old = [path.read_bytes() for path in paths]
        old[2] = self.before
        tip = self.promote()
        current = [path.read_bytes() for path in paths]
        self.assertEqual(self.checkpoint.latest(), tip)
        for mask in range(8):
            with self.subTest(receipt=bool(mask & 1), witness=bool(mask & 2), ledger=bool(mask & 4)):
                for index, path in enumerate(paths):
                    path.write_bytes(old[index] if mask & (1 << index) else current[index])
                if mask in (0, 1):
                    self.assertEqual(self.promote(), tip)
                    self.assertEqual(self.pins.latest(), tip)
                else:
                    with self.assertRaises(recovery.DecimalRecoveryDenied):
                        self.promote()
                self.assertEqual(self.checkpoint.latest(), tip)
                self.assertEqual(self.path.read_bytes(), old[2] if mask & 4 else current[2])

    def test_checkpoint_rollback_refused_with_current_local_receipt(self):
        self.prepare_checkpoint()
        old_checkpoint = self.checkpoint_path.read_bytes()
        tip = self.promote()
        self.checkpoint_path.write_bytes(old_checkpoint)
        self.assertEqual(self.checkpoint.latest(), self.claim)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.promote()
        self.assertEqual(self.pins.latest(), tip)

    def test_combined_evidence_rollback_is_indistinguishable_from_first_promotion(self):
        self.prepare_checkpoint()
        paths = (self.pin_path, self.store_path, self.checkpoint_path)
        previous = [path.read_bytes() for path in paths]
        prepared_ledger = self.path.read_bytes()
        tip = self.promote()
        for path, content in zip(paths, previous):
            path.write_bytes(content)
        self.assertEqual(self.promote(), tip)
        self.assertEqual(self.path.read_bytes(), prepared_ledger)

    def test_process_exit_at_each_promotion_publication_boundary(self):
        self.prepare_checkpoint()
        resources = (self.pin_path, self.store_path, self.checkpoint_path)
        initial = [path.read_bytes() for path in resources]
        ledger = self.path.read_bytes()
        boundaries = (
            (self.store, "_append", 0),
            (self.checkpoint._store, "_save", 1),
            (self.pins, "_save", 2),
            (None, None, 3),
        )
        for resource, method, committed in boundaries:
            with self.subTest(committed=committed):
                for path, content in zip(resources, initial):
                    path.write_bytes(content)
                pid = os.fork()
                if pid == 0:
                    try:
                        if resource is None:
                            self.promote()
                            os._exit(90)
                        with patch.object(resource, method, side_effect=lambda *a, **k: os._exit(90)):
                            self.promote()
                    finally:
                        os._exit(91)
                _, status = os.waitpid(pid, 0)
                self.assertEqual(os.waitstatus_to_exitcode(status), 90)
                record, tip, _ = self.store.read(trusted_receipt=self.claim)
                self.assertEqual(record, self.promotion if committed >= 1 else self.pending)
                self.assertEqual(self.checkpoint.latest(), tip if committed >= 2 else self.claim)
                if committed == 3:
                    self.assertEqual(self.pins.latest(), tip)
                else:
                    with self.assertRaises(recovery.DecimalRecoveryDenied):
                        self.pins.latest()
                resolved = self.promote()
                self.assertEqual(self.pins.latest(), resolved)
                self.assertEqual(self.checkpoint.latest(), resolved)
                self.assertEqual(resolved["number"], self.claim["number"] + 1)
                self.assertEqual(self.path.read_bytes(), ledger)
