"""Exercise independently retained promotion evidence under synthetic rollback."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
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

    def test_independent_receipt_retains_terminal_quarantine_across_checkpoint_loss(self):
        self.prepare_checkpoint()
        active_tip = self.promote()
        active_snapshot = self.store.backup(expected_receipt=active_tip)
        active_receipts = self.pin_path.read_bytes()
        active_export = self.checkpoint.export(expected_receipt=active_tip)
        folder = tempfile.TemporaryDirectory(prefix="decimal-independent-recovery-")
        self.addCleanup(folder.cleanup)
        retained = receipts.DecimalRecoveryReceipt.create(
            Path(folder.name) / "recovery.db", receipt_key=os.urandom(32),
            receipts=self.pins, witness=self.store, reviewed_receipt=active_tip)
        quarantine = recovery.quarantine_decimal_recovery(
            record=self.promotion, trusted_tip=recovery.evidence_tip(self.promotion),
            operator_key=self.operator, reason="COMPROMISED_KEY")
        terminal_tip = self.pins.publish(self.store, quarantine)
        terminal_snapshot = self.store.backup(expected_receipt=terminal_tip)
        terminal_receipts = self.pin_path.read_bytes()
        self.assertEqual(retained.retain(
            self.pins, self.store, expected_receipt=active_tip, reviewed_receipt=terminal_tip),
            terminal_tip)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            retained.retain(self.pins, self.store, expected_receipt=active_tip,
                            reviewed_receipt=terminal_tip)
        self.checkpoint_path.unlink()

        # Roll both local resources back to the same authentic active receipt.
        self.pin_path.write_bytes(active_receipts)
        self.store_path.write_bytes(active_snapshot)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            retained.retain(self.pins, self.store, expected_receipt=terminal_tip,
                            reviewed_receipt=active_tip)
        self.store_path.unlink()

        def rebuild(snapshot):
            return self.pins.recover_witness(
                self.store, snapshot, ledger_path=self.path, journal_key=self.replacement,
                anchor_key=self.anchor, recovery_receipt=retained)

        for snapshot in (active_snapshot, terminal_snapshot):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                rebuild(snapshot)
            self.assertFalse(self.store_path.exists())
            self.assertEqual(self.pin_path.read_bytes(), active_receipts)

        self.pin_path.write_bytes(terminal_receipts)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            rebuild(active_snapshot)
        self.assertFalse(self.store_path.exists())
        self.path.unlink()
        rebuilt = rebuild(terminal_snapshot)
        self.assertEqual(rebuilt.read(trusted_receipt=terminal_tip),
                         (quarantine, terminal_tip, False))
        self.assertFalse(self.path.exists())
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.recover_checkpoint(active_export, active_tip)
        self.assertFalse(self.checkpoint_path.exists())
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            rebuilt.publish(self.promotion, expected_receipt=terminal_tip)

    def test_independent_receipt_requires_exact_prepared_ledger(self):
        self.prepare_checkpoint()
        tip = self.promote()
        snapshot = self.store.backup(expected_receipt=tip)
        folder = tempfile.TemporaryDirectory(prefix="decimal-independent-recovery-")
        self.addCleanup(folder.cleanup)
        retained = receipts.DecimalRecoveryReceipt.create(
            Path(folder.name) / "recovery.db", receipt_key=os.urandom(32),
            receipts=self.pins, witness=self.store, reviewed_receipt=tip)
        self.old.write_bytes(self.before)
        self.old.chmod(0o600)
        self.store_path.unlink()
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.pins.recover_witness(
                self.store, snapshot, ledger_path=self.old, journal_key=self.journal,
                anchor_key=self.anchor, recovery_receipt=retained)
        self.assertFalse(self.store_path.exists())
        rebuilt = self.pins.recover_witness(
            self.store, snapshot, ledger_path=self.path, journal_key=self.replacement,
            anchor_key=self.anchor, recovery_receipt=retained)
        self.assertEqual(rebuilt.read(trusted_receipt=tip), (self.promotion, tip, False))

    def terminal_recovery_evidence(self):
        self.prepare_checkpoint()
        active = self.promote()
        old_witness = self.store.backup(expected_receipt=active)
        folder = tempfile.TemporaryDirectory(prefix="decimal-terminal-review-")
        self.addCleanup(folder.cleanup)
        retained = receipts.DecimalRecoveryReceipt.create(
            Path(folder.name) / "recovery.db", receipt_key=os.urandom(32),
            receipts=self.pins, witness=self.store, reviewed_receipt=active)
        quarantine = recovery.quarantine_decimal_recovery(
            record=self.promotion, trusted_tip=recovery.evidence_tip(self.promotion),
            operator_key=self.operator, reason="INTEGRITY_FAILURE")
        terminal = self.pins.publish(self.store, quarantine)
        terminal_witness = self.store.backup(expected_receipt=terminal)
        retained.retain_terminal(self.pins, self.store, expected_receipt=active,
                                 reviewed_receipt=terminal, operator_record=quarantine)
        self.pin_path.unlink()
        evidence = dict(reviewed_receipt=terminal, operator_record=quarantine)
        return retained, evidence, old_witness, terminal_witness

    def test_terminal_receipt_publication_refuses_unsafe_retry_and_allows_readback(self):
        retained, evidence, old_witness, terminal_witness = self.terminal_recovery_evidence()
        terminal, quarantine = evidence["reviewed_receipt"], evidence["operator_record"]

        def repair():
            return retained.repair_local_terminal(self.pins, self.store, **evidence)

        def inspect():
            return retained.inspect_local_terminal(self.pins, self.store, **evidence)

        def exit_during_initialize(stage, tip):
            stage.path.touch(mode=0o600)
            os._exit(90)

        pid = os.fork()
        if pid == 0:
            try:
                with patch.object(receipts.DecimalReceiptStore, "_initialize", exit_during_initialize):
                    repair()
            finally:
                os._exit(91)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 90)
        self.assertFalse(self.pin_path.exists())
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            inspect()
        partial, = self.pin_path.parent.glob(".decimal-terminal-receipt-*/receipt.db")
        unrelated = partial.with_name("unrelated.db")
        unrelated.write_bytes(b"unrelated fixture")

        self.store_path.write_bytes(old_witness)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            repair()
        self.assertFalse(self.pin_path.exists())
        self.store_path.write_bytes(terminal_witness)
        link = os.link

        def exit_after_link(source, target, **options):
            link(source, target, **options)
            os._exit(92)

        pid = os.fork()
        if pid == 0:
            try:
                with patch.object(receipts.os, "link", exit_after_link):
                    repair()
            finally:
                os._exit(93)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 92)
        published = self.pin_path.read_bytes()
        inode = self.pin_path.stat()
        self.assertEqual(inspect(), {"receipt": terminal, "additionalLinkPresent": True})
        self.store_path.write_bytes(old_witness)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            inspect()
        self.store_path.write_bytes(terminal_witness)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            repair()
        self.assertTrue(os.path.samestat(self.pin_path.stat(), inode))
        self.assertEqual(self.pin_path.read_bytes(), published)
        self.assertEqual(partial.read_bytes(), b"")
        self.assertEqual(unrelated.read_bytes(), b"unrelated fixture")
        self.assertEqual(self.store.read(trusted_receipt=terminal), (quarantine, terminal, False))
        linked, = (path for path in self.pin_path.parent.glob(".decimal-terminal-receipt-*/receipt.db")
                   if path.samefile(self.pin_path))
        sibling = linked.with_name("operator-notes.txt")
        sibling.write_bytes(b"operator fixture")
        retained.cleanup_local_terminal_stage(linked, self.pins, self.store, **evidence)
        self.assertFalse(linked.exists())
        self.assertEqual(sibling.read_bytes(), b"operator fixture")
        self.assertEqual(partial.read_bytes(), b"")
        self.assertEqual(unrelated.read_bytes(), b"unrelated fixture")
        self.assertEqual(inspect(), {"receipt": terminal, "additionalLinkPresent": False})
        self.assertEqual(self.pins.latest(), terminal)

    def test_terminal_stage_cleanup_refuses_active_publisher_and_inexact_evidence(self):
        retained, evidence, old_witness, terminal_witness = self.terminal_recovery_evidence()

        def cleanup(path, **overrides):
            retained.cleanup_local_terminal_stage(path, self.pins, self.store,
                                                  **(evidence | overrides))

        def fail_sync(_):
            stage, = self.pin_path.parent.glob(".decimal-terminal-receipt-*/receipt.db")
            self.assertTrue(stage.samefile(self.pin_path))
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                cleanup(stage)
            self.assertTrue(stage.samefile(self.pin_path))
            raise OSError("synthetic lost publication acknowledgment")

        with patch.object(receipts, "_sync_directory", side_effect=fail_sync):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                retained.repair_local_terminal(self.pins, self.store, **evidence)
        stage, = self.pin_path.parent.glob(".decimal-terminal-receipt-*/receipt.db")
        folder = tempfile.TemporaryDirectory(prefix=".decimal-terminal-receipt-",
                                             dir=self.pin_path.parent)
        self.addCleanup(folder.cleanup)
        unrelated = Path(folder.name) / stage.name
        content = self.pin_path.read_bytes()
        unrelated.write_bytes(content)
        unrelated.chmod(0o600)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            cleanup(unrelated)
        self.assertEqual(unrelated.read_bytes(), content)
        unrelated.unlink()
        unrelated.symlink_to(self.pin_path)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            cleanup(unrelated)
        self.assertTrue(unrelated.is_symlink())
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            cleanup(stage, operator_record=self.promotion)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            cleanup(stage, reviewed_receipt={"number": 1, "mac": "0" * 64})
        self.store_path.write_bytes(old_witness)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            cleanup(stage)
        self.store_path.write_bytes(terminal_witness)
        independent = retained._store.path
        offline = independent.with_suffix(".offline")
        independent.rename(offline)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            cleanup(stage)
        offline.rename(independent)
        sidecar = stage.with_name(stage.name + "-journal")
        sidecar.write_bytes(b"unreviewed fixture")
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            cleanup(stage)
        self.assertEqual(sidecar.read_bytes(), b"unreviewed fixture")
        self.assertTrue(stage.samefile(self.pin_path))
        sidecar.unlink()
        cleanup(stage)
        self.assertFalse(stage.exists())
        self.assertEqual(self.pin_path.read_bytes(), content)

    def terminal_cleanup_fixture(self):
        retained, evidence, old_witness, _ = self.terminal_recovery_evidence()
        retained.repair_local_terminal(self.pins, self.store, **evidence)
        folder = tempfile.TemporaryDirectory(prefix=".decimal-terminal-receipt-",
                                             dir=self.pin_path.parent)
        self.addCleanup(folder.cleanup)
        stage = Path(folder.name) / "receipt.db"
        os.link(self.pin_path, stage)
        return retained, evidence, stage, old_witness

    def test_terminal_stage_cleanup_survives_process_exit_at_unlink(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        unrelated = stage.with_name("unrelated.db")
        unrelated.write_bytes(b"unrelated")
        original, content = self.pin_path.stat(), self.pin_path.read_bytes()
        unlink = os.unlink
        for removed in (False, True):
            with self.subTest(removed=removed):
                def exit_at_unlink(*args, **kwargs):
                    if removed:
                        unlink(*args, **kwargs)
                    os._exit(90)

                pid = os.fork()
                if pid == 0:
                    try:
                        with patch.object(receipts.os, "unlink", side_effect=exit_at_unlink):
                            retained.cleanup_local_terminal_stage(
                                stage, self.pins, self.store, **evidence)
                    finally:
                        os._exit(91)
                _, status = os.waitpid(pid, 0)
                self.assertEqual(os.waitstatus_to_exitcode(status), 90)
                self.assertEqual(retained.inspect_local_terminal(self.pins, self.store, **evidence),
                                 {"receipt": evidence["reviewed_receipt"],
                                  "additionalLinkPresent": not removed})
                with self.assertRaises(recovery.DecimalRecoveryDenied):
                    retained.inspect_local_terminal(
                        self.pins, self.store, **(evidence | {"operator_record": self.promotion}))
                self.assertEqual(stage.exists(), not removed)
                self.assertTrue(os.path.samestat(self.pin_path.stat(), original))
                self.assertEqual(self.pin_path.read_bytes(), content)
                self.assertEqual(unrelated.read_bytes(), b"unrelated")

    def test_concurrent_terminal_stage_cleanup_has_one_winner(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        unrelated = stage.with_name("unrelated.db")
        unrelated.write_bytes(b"unrelated")
        original, content = self.pin_path.stat(), self.pin_path.read_bytes()
        start = Barrier(2, timeout=5)

        def cleanup():
            start.wait()
            retained.cleanup_local_terminal_stage(stage, self.pins, self.store, **evidence)

        with ThreadPoolExecutor(max_workers=2) as pool:
            attempts = [pool.submit(cleanup) for _ in range(2)]
        self.assertEqual(sum(attempt.exception() is None for attempt in attempts), 1)
        self.assertEqual(sum(isinstance(attempt.exception(), recovery.DecimalRecoveryDenied)
                             for attempt in attempts), 1)
        self.assertFalse(stage.exists())
        self.assertEqual(retained.inspect_local_terminal(self.pins, self.store, **evidence),
                         {"receipt": evidence["reviewed_receipt"], "additionalLinkPresent": False})
        self.assertTrue(os.path.samestat(self.pin_path.stat(), original))
        self.assertEqual(self.pin_path.read_bytes(), content)
        self.assertEqual(unrelated.read_bytes(), b"unrelated")

    def test_terminal_stage_cleanup_refuses_evidence_loss_or_replacement_after_review(self):
        retained, evidence, stage, old_witness = self.terminal_cleanup_fixture()
        original, content = self.pin_path.stat(), self.pin_path.read_bytes()
        sync = receipts._sync_directory
        for path, replace in ((retained._store.path, False), (self.store_path, True)):
            with self.subTest(resource=path.name, replace=replace):
                held = path.with_suffix(".held")

                def move_evidence(directory):
                    sync(directory)
                    path.rename(held)
                    if replace:
                        path.write_bytes(old_witness)
                        path.chmod(0o600)

                with patch.object(receipts, "_sync_directory", side_effect=move_evidence):
                    with self.assertRaises(recovery.DecimalRecoveryDenied):
                        retained.cleanup_local_terminal_stage(stage, self.pins, self.store, **evidence)
                self.assertTrue(stage.samefile(self.pin_path))
                self.assertTrue(os.path.samestat(self.pin_path.stat(), original))
                self.assertEqual(self.pin_path.read_bytes(), content)
                with self.assertRaises(recovery.DecimalRecoveryDenied):
                    retained.inspect_local_terminal(self.pins, self.store, **evidence)
                held.replace(path)
        retained.cleanup_local_terminal_stage(stage, self.pins, self.store, **evidence)
        self.assertFalse(stage.exists())

    def test_terminal_stage_cleanup_sync_failures_require_exact_readback(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        terminal = evidence["reviewed_receipt"]
        original, content = self.pin_path.stat(), self.pin_path.read_bytes()
        fsync = os.fsync
        for failed_sync in (1, 2):
            calls = []

            def fail_directory_sync(fd):
                directory = self.pin_path.parent if not calls else stage.parent
                self.assertTrue(os.path.samestat(os.fstat(fd), directory.stat()))
                calls.append(stage.exists())
                if len(calls) == failed_sync:
                    raise OSError("synthetic cleanup sync failure")
                fsync(fd)

            with self.subTest(failed_sync=failed_sync):
                with patch.object(receipts.os, "fsync", side_effect=fail_directory_sync):
                    with self.assertRaises(recovery.DecimalRecoveryDenied):
                        retained.cleanup_local_terminal_stage(stage, self.pins, self.store, **evidence)
                self.assertEqual(calls, [True] if failed_sync == 1 else [True, False])
                expected = {"receipt": terminal, "additionalLinkPresent": failed_sync == 1}
                for _ in range(2):
                    self.assertEqual(retained.inspect_local_terminal(self.pins, self.store, **evidence),
                                     expected)
                self.assertTrue(os.path.samestat(self.pin_path.stat(), original))
                self.assertEqual(self.pin_path.read_bytes(), content)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            retained.cleanup_local_terminal_stage(stage, self.pins, self.store, **evidence)
        self.assertEqual(self.pins.latest(), terminal)

    def test_terminal_publication_requires_evidence_before_link_and_after_sync(self):
        retained, evidence, _, _ = self.terminal_recovery_evidence()
        sync = receipts._sync_directory
        initialize = receipts.DecimalReceiptStore._initialize
        for path in (retained._store.path, self.store_path):
            for after_link in (False, True):
                with self.subTest(resource=path.name, after_link=after_link):
                    saved = path.with_suffix(".saved")
                    exact = path.read_bytes()

                    def interrupt_initialization(stage, tip):
                        initialize(stage, tip)
                        path.rename(saved)

                    def interrupt_sync(directory):
                        sync(directory)
                        path.rename(saved)
                        path.write_bytes(exact)
                        path.chmod(0o600)

                    interruption = (patch.object(receipts, "_sync_directory", interrupt_sync)
                                    if after_link else patch.object(receipts.DecimalReceiptStore,
                                                                    "_initialize", interrupt_initialization))
                    with interruption:
                        with self.assertRaises(recovery.DecimalRecoveryDenied):
                            retained.repair_local_terminal(self.pins, self.store, **evidence)
                    self.assertEqual(self.pin_path.exists(), after_link)
                    saved.replace(path)
                    if after_link:
                        self.assertEqual(retained.inspect_local_terminal(self.pins, self.store, **evidence),
                                         {"receipt": evidence["reviewed_receipt"],
                                          "additionalLinkPresent": True})
                        stage, = (candidate for candidate in self.pin_path.parent.glob(
                            ".decimal-terminal-receipt-*/receipt.db") if candidate.samefile(self.pin_path))
                        retained.cleanup_local_terminal_stage(stage, self.pins, self.store, **evidence)
                        self.pin_path.unlink()

    def test_terminal_readback_after_witness_commit_and_concurrent_review(self):
        self.prepare_checkpoint()
        active_tip = self.promote()
        active_local = self.pin_path.read_bytes()
        folder = tempfile.TemporaryDirectory(prefix="decimal-terminal-receipt-")
        self.addCleanup(folder.cleanup)
        retained = receipts.DecimalRecoveryReceipt.create(
            Path(folder.name) / "recovery.db", receipt_key=os.urandom(32),
            receipts=self.pins, witness=self.store, reviewed_receipt=active_tip)
        quarantine = recovery.quarantine_decimal_recovery(
            record=self.promotion, trusted_tip=recovery.evidence_tip(self.promotion),
            operator_key=self.operator, reason="AMBIGUOUS_OLD_STATE")
        different_quarantine = recovery.quarantine_decimal_recovery(
            record=self.promotion, trusted_tip=recovery.evidence_tip(self.promotion),
            operator_key=self.operator, reason="INTEGRITY_FAILURE")
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            retained.repair_local_terminal(self.pins, self.store, reviewed_receipt=active_tip,
                                           operator_record=self.promotion)

        save = self.pins._save

        def interrupt(db, receipt, *, pending):
            if not pending:
                os._exit(90)
            save(db, receipt, pending=pending)

        pid = os.fork()
        if pid == 0:
            try:
                with patch.object(self.pins, "_save", side_effect=interrupt):
                    self.pins.publish(self.store, quarantine)
            finally:
                os._exit(91)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 90)
        record, terminal, _ = self.store.read(trusted_receipt=active_tip)
        self.assertEqual(record, quarantine)
        frozen_local = self.pin_path.read_bytes()
        self.assertEqual(retained._store.latest(), active_tip)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.pins.latest()
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            retained.retain_terminal(self.pins, self.store, expected_receipt=active_tip,
                                     reviewed_receipt=terminal, operator_record=different_quarantine)
        start = Barrier(2, timeout=5)

        def retain():
            start.wait()
            return retained.retain_terminal(
                self.pins, self.store, expected_receipt=active_tip,
                reviewed_receipt=terminal, operator_record=quarantine)

        with ThreadPoolExecutor(max_workers=2) as pool:
            attempts = [pool.submit(retain) for _ in range(2)]
        self.assertEqual([attempt.result() for attempt in attempts if attempt.exception() is None],
                         [terminal])
        self.assertEqual(sum(isinstance(attempt.exception(), recovery.DecimalRecoveryDenied)
                             for attempt in attempts), 1)
        self.assertEqual(self.pin_path.read_bytes(), frozen_local)
        self.checkpoint_path.unlink()
        self.path.write_bytes(self.before)

        def repair(record=quarantine):
            return retained.repair_local_terminal(
                self.pins, self.store, reviewed_receipt=terminal, operator_record=record)

        for original in (frozen_local, active_local, None):
            with self.subTest(local="missing" if original is None else "existing"):
                if original is None:
                    self.pin_path.unlink()
                else:
                    self.pin_path.write_bytes(original)
                with self.assertRaises(recovery.DecimalRecoveryDenied):
                    repair(different_quarantine)
                if original is None:
                    self.assertFalse(self.pin_path.exists())
                else:
                    self.assertEqual(self.pin_path.read_bytes(), original)
                self.assertEqual(repair(), terminal)
                self.assertEqual(repair(), terminal)
                self.assertEqual(self.pins.latest(), terminal)
                self.assertEqual(self.path.read_bytes(), self.before)
        self.assertEqual(self.store.read(trusted_receipt=terminal), (quarantine, terminal, False))
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.pins.publish(self.store, self.promotion)

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

    def test_checkpoint_publication_rechecks_evidence_on_both_sides_of_link(self):
        self.prepare_checkpoint()
        tip = self.promote()
        exported = self.checkpoint.export(expected_receipt=tip)
        self.checkpoint_path.unlink()
        initialize = receipts.DecimalReceiptStore._initialize
        sync = receipts._sync_directory

        def inspect():
            return self.checkpoint.inspect_recovered(
                exported, trusted_receipt=tip, **self.recovery_evidence())

        for evidence_path in (self.pin_path, self.store_path, self.path):
            for after_link in (False, True):
                with self.subTest(evidence=evidence_path.name, after_link=after_link):
                    saved = evidence_path.with_suffix(".saved")
                    exact = evidence_path.read_bytes()

                    def lose_evidence(stage, receipt):
                        initialize(stage, receipt)
                        evidence_path.rename(saved)

                    def replace_evidence(directory):
                        sync(directory)
                        stages = directory.glob(".edgepilot-checkpoint-*/checkpoint.db")
                        active, = (candidate for candidate in stages
                                   if candidate.samefile(self.checkpoint_path))
                        with self.assertRaises(recovery.DecimalRecoveryDenied):
                            self.cleanup_stage(active, exported, tip)
                        evidence_path.rename(saved)
                        evidence_path.write_bytes(exact)
                        evidence_path.chmod(0o600)

                    interruption = (patch.object(receipts, "_sync_directory", replace_evidence)
                                    if after_link else patch.object(receipts.DecimalReceiptStore,
                                                                    "_initialize", lose_evidence))
                    with interruption, self.assertRaises(recovery.DecimalRecoveryDenied):
                        self.recover_checkpoint(exported, tip)
                    self.assertEqual(self.checkpoint_path.exists(), after_link)
                    saved.replace(evidence_path)
                    if after_link:
                        published = self.checkpoint_path.stat()
                        content = self.checkpoint_path.read_bytes()
                        stages = self.checkpoint_path.parent.glob(".edgepilot-checkpoint-*/checkpoint.db")
                        stage, = (candidate for candidate in stages if candidate.samefile(self.checkpoint_path))
                        with self.assertRaises(recovery.DecimalRecoveryDenied):
                            self.checkpoint.latest()
                        with self.assertRaises(recovery.DecimalRecoveryDenied):
                            self.recover_checkpoint(exported, tip)
                        self.assertEqual(inspect(), {"receipt": tip, "additionalLinkPresent": True})
                        self.cleanup_stage(stage, exported, tip)
                        self.assert_checkpoint_readback(stage, exported, tip, published, content, linked=False)
                        self.checkpoint_path.unlink()

    def test_checkpoint_cleanup_preserves_both_names_if_destination_sync_fails(self):
        stage, exported, tip = self.reviewed_staging_link()
        original, content = self.checkpoint_path.stat(), self.checkpoint_path.read_bytes()
        with patch.object(receipts, "_sync_directory", side_effect=OSError("synthetic sync failure")):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                self.cleanup_stage(stage, exported, tip)
        self.assert_checkpoint_readback(stage, exported, tip, original, content, linked=True)
        self.cleanup_stage(stage, exported, tip)
        self.assert_checkpoint_readback(stage, exported, tip, original, content, linked=False)

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

    def test_checkpoint_readback_refuses_lost_or_replaced_evidence_during_audit(self):
        stage, exported, tip = self.reviewed_staging_link()
        original, content = self.checkpoint_path.stat(), self.checkpoint_path.read_bytes()
        read = self.checkpoint._store._read_published

        for path in (self.pin_path, self.store_path):
            exact = path.read_bytes()
            for replace in (False, True):
                with self.subTest(resource=path.name, replace=replace):
                    saved = path.with_suffix(".saved")

                    @contextmanager
                    def interrupt(receipt):
                        with read(receipt) as info:
                            path.rename(saved)
                            if replace:
                                path.write_bytes(exact)
                                path.chmod(0o600)
                            yield info

                    with patch.object(self.checkpoint._store, "_read_published", interrupt):
                        with self.assertRaises(recovery.DecimalRecoveryDenied):
                            self.checkpoint.inspect_recovered(
                                exported, trusted_receipt=tip, **self.recovery_evidence())
                    saved.replace(path)
                    self.assert_checkpoint_readback(stage, exported, tip, original, content, linked=True)

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
