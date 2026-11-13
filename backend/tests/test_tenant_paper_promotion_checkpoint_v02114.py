"""Exercise independently retained promotion evidence under synthetic rollback."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch
from uuid import uuid4

from engine import tenant_paper_decimal_atomic_rehearsal as ledger
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

    def recover_checkpoint(self, exported, tip):
        return receipts.DecimalPromotionCheckpoint.recover(
            self.checkpoint_path, exported, trusted_receipt=tip,
            checkpoint_key=self.checkpoint_key, **self.recovery_evidence())

    def recovery_evidence(self):
        return dict(receipts=self.pins, witness=self.store, ledger_path=self.path,
                    reserved_receipt=self.prepared, prepared_receipt=self.claim,
                    operator_record=self.promotion, journal_key=self.replacement,
                    anchor_key=self.anchor)

    def test_lost_checkpoint_recovers_at_exact_signed_export_only(self):
        self.prepare_checkpoint()
        stale = self.checkpoint.export(expected_receipt=self.claim)
        tip = self.promote()
        exported = self.checkpoint.export(expected_receipt=tip)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.recover_checkpoint(exported, tip)
        self.checkpoint_path.unlink()
        for rejected, receipt in ((stale, tip), (stale, self.claim),
                                  ({**exported, "mac": "0" * 64}, tip)):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                self.recover_checkpoint(rejected, receipt)
            self.assertFalse(self.checkpoint_path.exists())
        rebuilt = self.recover_checkpoint(exported, tip)
        self.assertEqual(rebuilt.latest(), tip)
        self.assertEqual(rebuilt.export(expected_receipt=tip), exported)

    def test_checkpoint_recovery_preserves_unacknowledged_local_reservation(self):
        self.prepare_checkpoint()
        reserved = self.pin_path.read_bytes()
        tip = self.promote()
        exported = self.checkpoint.export(expected_receipt=tip)
        self.pin_path.write_bytes(reserved)
        self.checkpoint_path.unlink()
        self.checkpoint = self.recover_checkpoint(exported, tip)
        self.assertEqual(self.pin_path.read_bytes(), reserved)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.pins.latest()
        self.assertEqual(self.promote(), tip)
        self.assertEqual(self.pins.latest(), tip)

    def test_advanced_witness_refuses_previous_export_after_interrupted_next_promotion(self):
        self.prepare_checkpoint()
        previous_tip = self.promote()
        previous_export = self.checkpoint.export(expected_receipt=previous_tip)
        previous_receipts = self.pin_path.read_bytes()
        previous_evidence = self.recovery_evidence()
        self.checkpoint_path.unlink()

        candidate = self.path.with_name("next.db")
        shutil.copy2(self.path, candidate)
        ledger.register_decimal_account(
            candidate, hmac_key=self.replacement, initial_cash_cents=10000,
            protected_pct=90, spend_cap_cents=2000, per_trade_cap_cents=800,
            max_loss_cents=14, principal_user_id=self.scope["principal_user_id"],
            account_id=str(uuid4()))
        pending = recovery.prepare_decimal_advance(
            self.path, candidate, record=self.promotion,
            trusted_tip=recovery.evidence_tip(self.promotion),
            **(self.keys | {"journal_key": self.replacement}))
        publish = self.store.publish
        with patch.object(self.store, "publish", side_effect=lambda record, **options:
                          publish(record, _interrupt="after_commit", **options)):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                self.pins.publish(self.store, pending)
        _, prepared, _ = self.store.read(trusted_receipt=previous_tip)
        approval = self.approve_prepared(candidate, pending, self.replacement)
        evidence = previous_evidence | dict(
            ledger_path=candidate, reserved_receipt=previous_tip,
            prepared_receipt=prepared, operator_record=approval)
        checkpoint = receipts.DecimalPromotionCheckpoint.create(
            self.checkpoint_path, checkpoint_key=self.checkpoint_key, receipts=self.pins,
            witness=self.store, reserved_receipt=previous_tip, prepared_receipt=prepared)

        def promote():
            return self.pins.promote_frozen(
                self.store, candidate, reserved_receipt=previous_tip, prepared_receipt=prepared,
                operator_record=approval, journal_key=self.replacement, anchor_key=self.anchor,
                checkpoint=checkpoint)

        pid = os.fork()
        if pid == 0:
            try:
                with patch.object(self.pins, "_save", side_effect=lambda *a, **k: os._exit(90)):
                    promote()
            finally:
                os._exit(91)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 90)
        latest = checkpoint.latest()
        self.assertEqual(self.store.read(trusted_receipt=latest), (approval, latest, False))
        latest_export = checkpoint.export(expected_receipt=latest)
        reserved = self.pin_path.read_bytes()
        candidate_bytes = candidate.read_bytes()
        previous_ledger = self.path.read_bytes()
        self.checkpoint_path.unlink()

        # The old local receipt and ledger both agree with the earlier export.
        # The independently advanced witness alone must still refuse it.
        self.pin_path.write_bytes(previous_receipts)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            receipts.DecimalPromotionCheckpoint.recover(
                self.checkpoint_path, previous_export, trusted_receipt=previous_tip,
                checkpoint_key=self.checkpoint_key, **previous_evidence)
        self.assertFalse(self.checkpoint_path.exists())
        self.assertEqual(self.pin_path.read_bytes(), previous_receipts)

        self.pin_path.write_bytes(reserved)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            receipts.DecimalPromotionCheckpoint.recover(
                self.checkpoint_path, latest_export, trusted_receipt=latest,
                checkpoint_key=self.checkpoint_key, **(evidence | {"ledger_path": self.path}))
        self.assertFalse(self.checkpoint_path.exists())
        checkpoint = receipts.DecimalPromotionCheckpoint.recover(
            self.checkpoint_path, latest_export, trusted_receipt=latest,
            checkpoint_key=self.checkpoint_key, **evidence)
        self.assertEqual(checkpoint.inspect_recovered(
            latest_export, trusted_receipt=latest, **evidence),
            {"receipt": latest, "additionalLinkPresent": False})
        self.assertEqual(self.pin_path.read_bytes(), reserved)
        self.assertEqual(promote(), latest)
        self.assertEqual(self.pins.latest(), latest)
        self.assertEqual(candidate.read_bytes(), candidate_bytes)
        self.assertEqual(self.path.read_bytes(), previous_ledger)

    def test_lost_checkpoint_refuses_missing_stale_or_foreign_resources(self):
        self.prepare_checkpoint()
        old_witness = self.store_path.read_bytes()
        tip = self.promote()
        exported = self.checkpoint.export(expected_receipt=tip)
        self.checkpoint_path.unlink()
        for path, stale in ((self.store_path, old_witness), (self.path, self.before),
                            (self.pin_path, None)):
            original = path.read_bytes()
            path.unlink()
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                self.recover_checkpoint(exported, tip)
            if stale is not None:
                path.write_bytes(stale)
                path.chmod(0o600)
                with self.assertRaises(recovery.DecimalRecoveryDenied):
                    self.recover_checkpoint(exported, tip)
            path.write_bytes(original)
            path.chmod(0o600)
        fixtures.IndependentReceiptTests.setUp(self)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.recover_checkpoint(exported, tip)
        self.assertFalse(self.checkpoint_path.exists())

    def test_missing_checkpoint_allows_explicit_terminal_quarantine(self):
        self.prepare_checkpoint()
        prepared_export = self.checkpoint.export(expected_receipt=self.claim)
        self.checkpoint_path.unlink()
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.promote()
        quarantine = recovery.quarantine_decimal_recovery(
            record=self.pending, trusted_tip=recovery.evidence_tip(self.pending),
            operator_key=self.operator, reason="AMBIGUOUS_OLD_STATE")
        before = self.path.read_bytes()
        tip = self.pins.quarantine_frozen(
            self.store, reserved_receipt=self.prepared, observed_receipt=self.claim,
            operator_record=quarantine)
        self.assertEqual(self.store.read(trusted_receipt=tip)[0], quarantine)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.recover_checkpoint(prepared_export, self.claim)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.checkpoint_path.exists())

    def test_process_exit_before_and_after_checkpoint_publication(self):
        self.prepare_checkpoint()
        tip = self.promote()
        exported = self.checkpoint.export(expected_receipt=tip)
        self.checkpoint_path.unlink()
        link = os.link
        for publish in (False, True):
            def stop_at_link(*args, **kwargs):
                if publish:
                    link(*args, **kwargs)
                os._exit(95)

            pid = os.fork()
            if pid == 0:
                try:
                    with patch.object(receipts.os, "link", side_effect=stop_at_link):
                        self.recover_checkpoint(exported, tip)
                finally:
                    os._exit(96)
            _, status = os.waitpid(pid, 0)
            self.assertEqual(os.waitstatus_to_exitcode(status), 95)
            self.assertEqual(self.checkpoint_path.exists(), publish)
        before = self.checkpoint_path.read_bytes()
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.recover_checkpoint(exported, tip)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.checkpoint.latest()  # The extra staging link still needs operator review.
        self.assertEqual(self.checkpoint.inspect_recovered(
            exported, trusted_receipt=tip, **self.recovery_evidence()),
            {"receipt": tip, "additionalLinkPresent": True})
        stages = self.checkpoint_path.parent.glob(".edgepilot-checkpoint-*/checkpoint.db")
        linked, = [path for path in stages if path.samefile(self.checkpoint_path)]
        self.cleanup_stage(linked, exported, tip)
        self.assertEqual(self.checkpoint.latest(), tip)
        self.assertEqual(self.checkpoint_path.read_bytes(), before)
        self.assertEqual(self.checkpoint.inspect_recovered(
            exported, trusted_receipt=tip, **self.recovery_evidence()),
            {"receipt": tip, "additionalLinkPresent": False})

    def test_partial_checkpoint_and_sidecar_require_explicit_resolution(self):
        self.prepare_checkpoint()
        tip = self.promote()
        exported = self.checkpoint.export(expected_receipt=tip)
        self.checkpoint_path.write_bytes(b"interrupted legacy checkpoint")
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.checkpoint.inspect_recovered(
                exported, trusted_receipt=tip, **self.recovery_evidence())
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.recover_checkpoint(exported, tip)
        self.assertEqual(self.checkpoint_path.read_bytes(), b"interrupted legacy checkpoint")
        fresh = self.checkpoint_path.with_name("reviewed-recovery.db")
        sidecar = fresh.with_name(fresh.name + "-journal")
        sidecar.write_bytes(b"prior evidence")
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            receipts.DecimalPromotionCheckpoint.recover(
                fresh, exported, trusted_receipt=tip, checkpoint_key=self.checkpoint_key,
                **self.recovery_evidence())
        self.assertFalse(fresh.exists())
        self.assertEqual(sidecar.read_bytes(), b"prior evidence")
        sidecar.unlink()
        rebuilt = receipts.DecimalPromotionCheckpoint.recover(
            fresh, exported, trusted_receipt=tip, checkpoint_key=self.checkpoint_key,
            **self.recovery_evidence())
        self.assertEqual(rebuilt.latest(), tip)

    def test_process_exit_during_staging_keeps_partial_file_off_destination(self):
        self.prepare_checkpoint()
        tip = self.promote()
        exported = self.checkpoint.export(expected_receipt=tip)
        self.checkpoint_path.unlink()
        pid = os.fork()
        if pid == 0:
            try:
                with patch.object(receipts.DecimalReceiptStore, "_save",
                                  side_effect=lambda *a, **k: os._exit(95)):
                    self.recover_checkpoint(exported, tip)
            finally:
                os._exit(96)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 95)
        self.assertFalse(self.checkpoint_path.exists())
        stage, = self.checkpoint_path.parent.glob(".edgepilot-checkpoint-*/checkpoint.db")
        before = stage.read_bytes()
        self.assertEqual(self.recover_checkpoint(exported, tip).latest(), tip)
        self.assertEqual(stage.read_bytes(), before)

    def cleanup_stage(self, stage, exported, tip):
        self.checkpoint.cleanup_recovered_stage(
            stage, exported, trusted_receipt=tip, **self.recovery_evidence())

    def reviewed_staging_link(self):
        self.prepare_checkpoint()
        tip = self.promote()
        exported = self.checkpoint.export(expected_receipt=tip)
        folder = tempfile.TemporaryDirectory(prefix=".edgepilot-checkpoint-",
                                             dir=self.checkpoint_path.parent)
        self.addCleanup(folder.cleanup)
        stage = Path(folder.name) / "checkpoint.db"
        os.link(self.checkpoint_path, stage)
        return stage, exported, tip

    def assert_checkpoint_readback(self, stage, exported, tip, original, content, *, linked):
        self.assertEqual(stage.exists(), linked)
        self.assertTrue(os.path.samestat(original, self.checkpoint_path.stat()))
        self.assertEqual(self.checkpoint_path.read_bytes(), content)
        self.assertEqual(self.checkpoint.inspect_recovered(
            exported, trusted_receipt=tip, **self.recovery_evidence()),
            {"receipt": tip, "additionalLinkPresent": linked})

    def test_process_exit_immediately_before_and_after_checkpoint_cleanup_unlink(self):
        stage, exported, tip = self.reviewed_staging_link()
        original, content = self.checkpoint_path.stat(), self.checkpoint_path.read_bytes()
        unlink = os.unlink
        for remove in (False, True):
            with self.subTest(unlink_committed=remove):
                def exit_at_unlink(*args, **kwargs):
                    if remove:
                        unlink(*args, **kwargs)
                    os._exit(95)

                pid = os.fork()
                if pid == 0:
                    try:
                        with patch.object(receipts.os, "unlink", side_effect=exit_at_unlink):
                            self.cleanup_stage(stage, exported, tip)
                    finally:
                        os._exit(96)
                _, status = os.waitpid(pid, 0)
                self.assertEqual(os.waitstatus_to_exitcode(status), 95)
                self.assert_checkpoint_readback(stage, exported, tip, original, content,
                                                linked=not remove)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.cleanup_stage(stage, exported, tip)
        self.assertEqual(self.checkpoint.latest(), tip)

    def test_concurrent_checkpoint_cleanup_has_one_winner(self):
        stage, exported, tip = self.reviewed_staging_link()
        original, content = self.checkpoint_path.stat(), self.checkpoint_path.read_bytes()
        start = Barrier(2, timeout=5)

        def cleanup():
            start.wait()
            self.cleanup_stage(stage, exported, tip)

        with ThreadPoolExecutor(max_workers=2) as pool:
            attempts = [pool.submit(cleanup) for _ in range(2)]
        self.assertEqual(sum(job.exception() is None for job in attempts), 1)
        self.assertEqual(sum(isinstance(job.exception(), recovery.DecimalRecoveryDenied)
                             for job in attempts), 1)
        self.assert_checkpoint_readback(stage, exported, tip, original, content, linked=False)

    def test_terminal_quarantine_prevents_old_checkpoint_readback_and_cleanup(self):
        stage, exported, tip = self.reviewed_staging_link()
        original, content = self.checkpoint_path.stat(), self.checkpoint_path.read_bytes()
        quarantine = recovery.quarantine_decimal_recovery(
            record=self.promotion, trusted_tip=recovery.evidence_tip(self.promotion),
            operator_key=self.operator, reason="AMBIGUOUS_OLD_STATE")
        terminal = self.pins.publish(self.store, quarantine)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.checkpoint.inspect_recovered(exported, trusted_receipt=tip,
                                              **self.recovery_evidence())
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.cleanup_stage(stage, exported, tip)
        self.assertTrue(stage.samefile(self.checkpoint_path))
        self.assertTrue(os.path.samestat(original, self.checkpoint_path.stat()))
        self.assertEqual(self.checkpoint_path.read_bytes(), content)
        self.assertEqual(self.pins.latest(), terminal)
        self.assertEqual(self.store.read(trusted_receipt=terminal)[0], quarantine)

    def test_concurrent_checkpoint_recovery_has_one_exclusive_winner(self):
        self.prepare_checkpoint()
        tip = self.promote()
        exported = self.checkpoint.export(expected_receipt=tip)
        self.checkpoint_path.unlink()
        start = Barrier(2, timeout=5)

        def recover():
            start.wait()
            return self.recover_checkpoint(exported, tip)

        with ThreadPoolExecutor(max_workers=2) as pool:
            attempts = [pool.submit(recover) for _ in range(2)]
        winners = [job.result() for job in attempts if job.exception() is None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0].latest(), tip)
        self.assertEqual(sum(isinstance(job.exception(), recovery.DecimalRecoveryDenied)
                             for job in attempts), 1)
        self.assertEqual(list(self.checkpoint_path.parent.glob(".edgepilot-checkpoint-*")), [])

    def test_cleanup_refuses_active_publisher_even_at_exact_link(self):
        self.prepare_checkpoint()
        tip = self.promote()
        exported = self.checkpoint.export(expected_receipt=tip)
        self.checkpoint_path.unlink()
        link = os.link

        def while_publishing(stage, target, **options):
            link(stage, target, **options)
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                self.cleanup_stage(stage, exported, tip)
            self.assertTrue(stage.samefile(target))

        with patch.object(receipts.os, "link", side_effect=while_publishing):
            self.assertEqual(self.recover_checkpoint(exported, tip).latest(), tip)

    def test_cleanup_requires_reviewed_inode_and_exact_export(self):
        self.prepare_checkpoint()
        tip = self.promote()
        exported = self.checkpoint.export(expected_receipt=tip)
        original = self.checkpoint_path.stat()
        with tempfile.TemporaryDirectory(prefix=".edgepilot-checkpoint-",
                                         dir=self.checkpoint_path.parent) as folder:
            stage = Path(folder) / "checkpoint.db"
            stage.write_bytes(self.checkpoint_path.read_bytes())
            stage.chmod(0o600)
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                self.cleanup_stage(stage, exported, tip)
            self.assertTrue(stage.exists())
            stage.unlink()
            stage.symlink_to(self.checkpoint_path)
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                self.cleanup_stage(stage, exported, tip)
            self.assertTrue(stage.is_symlink())
            stage.unlink()
            os.link(self.checkpoint_path, stage)
            before = self.checkpoint_path.read_bytes()
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                self.cleanup_stage(stage, {**exported, "mac": "0" * 64}, tip)
            self.assertTrue(stage.samefile(self.checkpoint_path))
            extra = stage.with_name("another.db")
            os.link(stage, extra)
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                self.cleanup_stage(stage, exported, tip)
            self.assertTrue(extra.samefile(self.checkpoint_path))
            extra.unlink()
            self.cleanup_stage(stage, exported, tip)
            self.assertFalse(stage.exists())
            self.assertTrue(os.path.samestat(original, self.checkpoint_path.stat()))
            self.assertEqual(self.checkpoint_path.read_bytes(), before)
            self.assertEqual(self.checkpoint.latest(), tip)
