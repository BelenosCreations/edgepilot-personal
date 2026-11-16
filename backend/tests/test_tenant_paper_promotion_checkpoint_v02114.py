"""Exercise independently retained promotion evidence under synthetic rollback."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import ctypes
import errno
from functools import partial
import os
from pathlib import Path
import shutil
import signal
import socket
import sqlite3
import tempfile
from threading import Barrier, Event
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
        self.assertEqual(retained.inspect_terminal_handoff(self.pins, self.store, **evidence),
                         {"receipt": terminal, "localRepairRequired": True, "localReceiptMissing": True})

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
        self.assertEqual(retained.inspect_terminal_handoff(self.pins, self.store, **evidence),
                         {"receipt": terminal, "localRepairRequired": False})
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

    def test_handoff_distinguishes_a_missing_receipt_from_ambiguous_local_evidence(self):
        retained, evidence, old_witness, terminal_witness = self.terminal_recovery_evidence()
        terminal = evidence["reviewed_receipt"]

        def inspect(**overrides):
            return retained.inspect_terminal_handoff(self.pins, self.store, **(evidence | overrides))

        absent = {"receipt": terminal, "localRepairRequired": True, "localReceiptMissing": True}
        self.assertEqual(inspect(), absent)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            inspect(operator_record=self.promotion)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            inspect(reviewed_receipt=None)
        self.store_path.write_bytes(old_witness)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            inspect()
        self.store_path.write_bytes(terminal_witness)
        for suffix in ("-journal", "-wal", "-shm"):
            sidecar = self.pin_path.with_name(self.pin_path.name + suffix)
            sidecar.symlink_to(self.pin_path.with_suffix(".absent"))
            with self.subTest(sidecar=suffix):
                with self.assertRaises(recovery.DecimalRecoveryDenied):
                    inspect()
                with self.assertRaises(recovery.DecimalRecoveryDenied):
                    retained.repair_local_terminal(self.pins, self.store, **evidence)
                self.assertTrue(sidecar.is_symlink())
                self.assertFalse(self.pin_path.exists())
            sidecar.unlink()
        self.pin_path.symlink_to(self.pin_path.with_suffix(".absent"))
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            inspect()
        self.assertTrue(self.pin_path.is_symlink())
        self.pin_path.unlink()
        self.pin_path.touch(mode=0o600)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            inspect()
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            retained.repair_local_terminal(self.pins, self.store, **evidence)
        self.assertEqual(self.pin_path.read_bytes(), b"")
        self.pin_path.unlink()
        self.pins._initialize({"number": terminal["number"], "mac": "0" * 64})
        unrelated = self.pin_path.read_bytes()
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            inspect()
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            retained.repair_local_terminal(self.pins, self.store, **evidence)
        self.assertEqual(self.pin_path.read_bytes(), unrelated)
        self.pin_path.unlink()
        self.assertEqual(inspect(), absent)
        self.assertEqual(retained.repair_local_terminal(self.pins, self.store, **evidence), terminal)
        self.assertEqual(inspect(), {"receipt": terminal, "localRepairRequired": False})

    def test_terminal_handoff_waits_for_local_repair_commit_or_rollback(self):
        retained, evidence, _, _ = self.terminal_recovery_evidence()
        terminal = evidence["reviewed_receipt"]
        active = self.checkpoint.latest()
        self.pins._initialize(active)
        with self.pins._open() as db:
            self.pins._save(db, active, pending=True)
            db.commit()
        frozen = self.pin_path.read_bytes()
        saved_witness = self.store_path.read_bytes()
        saved_independent = retained._store.path.read_bytes()

        inspect = partial(retained.inspect_terminal_handoff, self.pins, self.store, **evidence)
        repair = partial(retained.repair_local_terminal, self.pins, self.store, **evidence)
        save = self.pins._save
        open_independent = retained._store._open

        for abort in (True, False):
            with self.subTest(abort=abort), ThreadPoolExecutor(max_workers=2) as pool:
                staged, attempting_inspection, finish = Event(), Event(), Event()

                def hold_update(db, tip, *, pending):
                    save(db, tip, pending=pending)
                    staged.set()
                    self.assertTrue(finish.wait(timeout=5))
                    if abort:
                        raise OSError("synthetic abort before local commit")

                def mark_reader(**options):
                    if staged.is_set():
                        attempting_inspection.set()
                    return open_independent(**options)

                with (patch.object(self.pins, "_save", hold_update),
                      patch.object(retained._store, "_open", mark_reader)):
                    pending_repair = pool.submit(repair)
                    try:
                        self.assertTrue(staged.wait(timeout=3))
                        pending_inspection = pool.submit(inspect)
                        self.assertTrue(attempting_inspection.wait(timeout=3))
                        with self.assertRaises(TimeoutError):
                            pending_inspection.result(timeout=0.05)
                    finally:
                        finish.set()

                    if abort:
                        with self.assertRaises(recovery.DecimalRecoveryDenied):
                            pending_repair.result(timeout=5)
                        self.assertEqual(self.pin_path.read_bytes(), frozen)
                    else:
                        self.assertEqual(pending_repair.result(timeout=5), terminal)
                    self.assertEqual(pending_inspection.result(timeout=5),
                                     {"receipt": terminal, "localRepairRequired": abort})
                self.assertEqual(self.store_path.read_bytes(), saved_witness)
                self.assertEqual(retained._store.path.read_bytes(), saved_independent)

    def test_missing_terminal_target_is_rechecked_after_independent_evidence(self):
        retained, evidence, _, _ = self.terminal_recovery_evidence()
        terminal = evidence["reviewed_receipt"]
        inspect = partial(retained.inspect_terminal_handoff, self.pins, self.store, **evidence)
        repair = partial(retained.repair_local_terminal, self.pins, self.store, **evidence)
        evidence_recheck = receipts._evidence_recheck
        foreign = b"unreviewed recovery evidence"

        for name, operation in (("inspect", inspect), ("repair", repair)):
            for suffix in ("", "-journal", "-wal", "-shm"):
                with self.subTest(operation=name, suffix=suffix):
                    intruder = self.pin_path.with_name(self.pin_path.name + suffix)
                    stages = set(self.pin_path.parent.glob(".decimal-terminal-receipt-*/receipt.db"))

                    def recheck_then_create(*paths):
                        recheck = evidence_recheck(*paths)

                        def create_intruder():
                            recheck()
                            intruder.write_bytes(foreign)
                            intruder.chmod(0o600)

                        return create_intruder

                    try:
                        with (patch.object(receipts, "_evidence_recheck", recheck_then_create),
                              self.assertRaises(recovery.DecimalRecoveryDenied)):
                            operation()
                        self.assertEqual(intruder.read_bytes(), foreign)
                        self.assertEqual(self.pin_path.exists(), suffix == "")
                        self.assertTrue(all(path.is_file() for path in stages))
                    finally:
                        intruder.unlink(missing_ok=True)

        self.assertEqual(inspect(),
                         {"receipt": terminal, "localRepairRequired": True, "localReceiptMissing": True})
        self.assertEqual(repair(), terminal)
        self.assertEqual(inspect(), {"receipt": terminal, "localRepairRequired": False})

    def test_cooperating_terminal_repairs_converge_on_one_publication(self):
        retained, evidence, _, _ = self.terminal_recovery_evidence()
        terminal = evidence["reviewed_receipt"]
        repair = partial(retained.repair_local_terminal, self.pins, self.store, **evidence)
        inspect = partial(retained.inspect_local_terminal, self.pins, self.store, **evidence)
        link = os.link
        original_evidence = {path: path.read_bytes() for path in
                             (self.store_path, retained._store.path)}

        for interrupted in (False, True):
            with self.subTest(interrupted=interrupted):
                parent, child = socket.socketpair()
                with parent, child:
                    parent.settimeout(5)
                    child.settimeout(5)
                    pid = os.fork()
                    if pid == 0:
                        parent.close()

                        def pause_after_link(*args, **kwargs):
                            link(*args, **kwargs)
                            child.sendall(b"R")
                            if child.recv(1) != b"X":
                                os._exit(93)
                            if interrupted:
                                os._exit(92)

                        try:
                            with patch.object(receipts.os, "link", pause_after_link):
                                repair()
                            os._exit(91)
                        finally:
                            os._exit(93)
                    child.close()
                    attempting = Event()
                    open_independent = retained._store._open

                    def mark_repair(**options):
                        attempting.set()
                        return open_independent(**options)

                    with ThreadPoolExecutor(max_workers=1) as pool:
                        released = False
                        try:
                            self.assertEqual(parent.recv(1), b"R")
                            stage, = self.pin_path.parent.glob(".decimal-terminal-receipt-*/receipt.db")
                            original = self.pin_path.stat()
                            content = self.pin_path.read_bytes()
                            self.assertTrue(stage.samefile(self.pin_path))
                            with patch.object(retained._store, "_open", mark_repair):
                                pending = pool.submit(repair)
                                self.assertTrue(attempting.wait(timeout=3))
                                with self.assertRaises(TimeoutError):
                                    pending.result(timeout=0.05)
                                parent.sendall(b"X")
                                released = True
                        finally:
                            if not released:
                                os.kill(pid, signal.SIGKILL)
                            _, status = os.waitpid(pid, 0)
                        self.assertEqual(os.waitstatus_to_exitcode(status), 92 if interrupted else 91)
                        if interrupted:
                            with self.assertRaises(recovery.DecimalRecoveryDenied):
                                pending.result(timeout=5)
                        else:
                            self.assertEqual(pending.result(timeout=5), terminal)

                self.assertEqual(inspect(), {"receipt": terminal, "additionalLinkPresent": interrupted})
                self.assertEqual(stage.exists(), interrupted)
                if interrupted:
                    self.assertTrue(stage.samefile(self.pin_path))
                    retained.cleanup_local_terminal_stage(stage, self.pins, self.store, **evidence)
                    self.assertEqual(repair(), terminal)
                self.assertTrue(os.path.samestat(self.pin_path.stat(), original))
                self.assertEqual(self.pin_path.read_bytes(), content)
                self.assertEqual(inspect(), {"receipt": terminal, "additionalLinkPresent": False})
                self.assertEqual({path: path.read_bytes() for path in original_evidence}, original_evidence)
                self.pin_path.unlink()

    def test_terminal_publication_refuses_sidecars_arriving_during_readback_or_cleanup(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        terminal = evidence["reviewed_receipt"]
        readback = partial(retained.inspect_local_terminal, self.pins, self.store, **evidence)
        handoff = partial(retained.inspect_terminal_handoff, self.pins, self.store, **evidence)
        cleanup = partial(retained.cleanup_local_terminal_stage, stage, self.pins, self.store, **evidence)
        original, published = self.pin_path.stat(), self.pin_path.read_bytes()
        evidence_recheck = receipts._evidence_recheck
        foreign = b"unreviewed SQLite sidecar"

        for operation in (readback, handoff, cleanup):
            for suffix in ("-journal", "-wal", "-shm"):
                with self.subTest(operation=operation.func.__name__, suffix=suffix):
                    sidecar = self.pin_path.with_name(self.pin_path.name + suffix)

                    def recheck_then_create(*paths):
                        recheck = evidence_recheck(*paths)

                        def create_sidecar():
                            recheck()
                            if retained._store.path in paths:
                                sidecar.write_bytes(foreign)

                        return create_sidecar

                    try:
                        with (patch.object(receipts, "_evidence_recheck", recheck_then_create),
                              self.assertRaises(recovery.DecimalRecoveryDenied)):
                            operation()
                        self.assertEqual(sidecar.read_bytes(), foreign)
                        self.assertTrue(stage.samefile(self.pin_path))
                        self.assertTrue(os.path.samestat(self.pin_path.stat(), original))
                        self.assertEqual(self.pin_path.read_bytes(), published)
                        for review in (readback, handoff, cleanup):
                            with self.assertRaises(recovery.DecimalRecoveryDenied):
                                review()
                        self.assertEqual(sidecar.read_bytes(), foreign)
                        self.assertTrue(stage.samefile(self.pin_path))
                    finally:
                        sidecar.unlink(missing_ok=True)
                    self.assertEqual(readback(), {"receipt": terminal, "additionalLinkPresent": True})

        cleanup()
        self.assertFalse(stage.exists())
        self.assertTrue(os.path.samestat(self.pin_path.stat(), original))
        self.assertEqual(self.pin_path.read_bytes(), published)
        self.assertEqual(readback(), {"receipt": terminal, "additionalLinkPresent": False})

    def test_terminal_readback_refuses_local_publication_changes_at_final_review(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        tip = evidence["reviewed_receipt"]
        readback = partial(retained.inspect_local_terminal, self.pins, self.store, **evidence)
        handoff = partial(retained.inspect_terminal_handoff, self.pins, self.store, **evidence)
        checked = {"receipt": tip, "additionalLinkPresent": True}
        for operation, expected in (
                (readback, checked), (handoff, {"receipt": tip, "localRepairRequired": False})):
            self.assert_changed_publication_refused(
                self.pin_path, stage, retained._store.path, operation, expected)

    def assert_changed_publication_refused(self, target, stage, independent, inspect, expected):
        original, content = target.stat(), target.read_bytes()
        evidence_recheck = receipts._evidence_recheck
        for change in ("unlink", "replace", "remove stage"):
            with self.subTest(operation=inspect.func.__name__, change=change):
                def recheck_then_change(*paths):
                    recheck = evidence_recheck(*paths)

                    def change_publication():
                        recheck()
                        if independent in paths:
                            if change == "remove stage":
                                stage.unlink()
                            else:
                                target.unlink()
                                if change == "replace":
                                    target.write_bytes(content)
                                    target.chmod(0o600)
                    return change_publication

                with (patch.object(receipts, "_evidence_recheck", recheck_then_change),
                      self.assertRaises(recovery.DecimalRecoveryDenied)):
                    inspect()
                if change == "remove stage":
                    self.assertFalse(stage.exists())
                    self.assertTrue(os.path.samestat(target.stat(), original))
                    os.link(target, stage)
                else:
                    self.assertTrue(os.path.samestat(stage.stat(), original))
                    if change == "replace":
                        self.assertEqual(target.read_bytes(), content)
                        self.assertFalse(target.samefile(stage))
                        target.unlink()
                    self.assertFalse(target.exists())
                    os.link(stage, target)
                self.assertTrue(target.samefile(stage))
                self.assertEqual(target.read_bytes(), content)
                self.assertEqual(inspect(), expected)

    def test_active_checkpoint_readback_rechecks_local_publication(self):
        stage, exported, tip = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(tip)
        inspect = partial(self.checkpoint.inspect_recovered, exported, trusted_receipt=tip,
                          **self.recovery_evidence(), recovery_receipt=independent)
        self.assert_changed_publication_refused(
            self.checkpoint_path, stage, independent._store.path, inspect,
            {"receipt": tip, "additionalLinkPresent": True})

    def test_terminal_publication_refuses_unreviewed_stage(self):
        retained, evidence, _, _ = self.terminal_recovery_evidence()
        self.assert_unreviewed_stage_refused(
            self.pin_path, ".decimal-terminal-receipt-*/receipt.db",
            partial(retained.repair_local_terminal, self.pins, self.store, **evidence),
            partial(retained.inspect_local_terminal, self.pins, self.store, **evidence),
            lambda stage: retained.cleanup_local_terminal_stage(
                stage, self.pins, self.store, **evidence),
            evidence["reviewed_receipt"],
            (self.store_path, retained._store.path))
        self.assertEqual(retained.inspect_terminal_handoff(self.pins, self.store, **evidence),
                         {"receipt": evidence["reviewed_receipt"], "localRepairRequired": False})

    def test_active_checkpoint_publication_refuses_unreviewed_stage(self):
        self.prepare_checkpoint()
        tip = self.promote()
        exported = self.checkpoint.export(expected_receipt=tip)
        independent = self.retain_independent_recovery_receipt(tip)
        self.checkpoint_path.unlink()
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.assert_unreviewed_stage_refused(
            self.checkpoint_path, ".edgepilot-checkpoint-*/checkpoint.db",
            partial(receipts.DecimalPromotionCheckpoint.recover,
                    self.checkpoint_path, exported, trusted_receipt=tip,
                    checkpoint_key=self.checkpoint_key, **evidence),
            partial(self.checkpoint.inspect_recovered, exported, trusted_receipt=tip, **evidence),
            lambda stage: self.checkpoint.cleanup_recovered_stage(
                stage, exported, trusted_receipt=tip, **evidence),
            tip, (self.pin_path, self.store_path, self.path, independent._store.path))
        self.assertEqual(self.checkpoint.latest(), tip)

    def assert_unreviewed_stage_refused(
            self, target, pattern, publish, inspect, cleanup, tip, evidence_paths):
        make_recheck = receipts._evidence_recheck
        link = os.link
        evidence = {path: path.read_bytes() for path in evidence_paths}
        preserved = {}

        for change in ("replace", "-journal", "-wal", "-shm", "replace at link"):
            with self.subTest(change=change):
                prior = set(target.parent.glob(pattern))
                changed = []

                def change_stage(stage):
                    original = stage.stat()
                    data = stage.read_bytes()
                    sibling = stage.with_name("operator-notes.txt")
                    preserved[sibling] = b"independent staging notes"
                    sibling.write_bytes(preserved[sibling])
                    if change.startswith("replace"):
                        copy = stage.with_suffix(".copy")
                        copy.write_bytes(data)
                        copy.chmod(0o600)
                        copy.replace(stage)
                        self.assertFalse(os.path.samestat(original, stage.stat()))
                    else:
                        sidecar = stage.with_name(stage.name + change)
                        preserved[sidecar] = b"unreviewed SQLite sidecar"
                        sidecar.write_bytes(preserved[sidecar])
                    preserved[stage] = data
                    changed.append(stage)

                def recheck_then_change(*paths):
                    recheck = make_recheck(*paths)

                    def recheck_stage():
                        recheck()
                        stages = set(target.parent.glob(pattern)) - prior
                        if stages and not changed:
                            stage, = stages
                            change_stage(stage)

                    return recheck_stage

                def replace_then_link(*args, **kwargs):
                    stage, = set(target.parent.glob(pattern)) - prior
                    change_stage(stage)
                    link(*args, **kwargs)

                interference = (patch.object(receipts.os, "link", replace_then_link)
                                if change == "replace at link" else
                                patch.object(receipts, "_evidence_recheck", recheck_then_change))
                with interference, self.assertRaises(recovery.DecimalRecoveryDenied):
                    publish()
                self.assertEqual(len(changed), 1)
                self.assertFalse(target.exists())
                with self.assertRaises(recovery.DecimalRecoveryDenied):
                    inspect()
                self.assertEqual({path: path.read_bytes() for path in preserved}, preserved)
                self.assertEqual({path: path.read_bytes() for path in evidence}, evidence)

        publish()
        self.assertEqual(inspect(), {"receipt": tip, "additionalLinkPresent": False})
        self.assertEqual({path: path.read_bytes() for path in preserved}, preserved)
        self.assertEqual({path: path.read_bytes() for path in evidence}, evidence)

        # Exercise a sidecar arriving inside the syscall window. The verified
        # inode may already have a destination name, but cleanup must refuse.
        target.unlink()
        stage_paths = set(target.parent.glob(pattern))

        def add_sidecar_then_link(*args, **kwargs):
            stage, = set(target.parent.glob(pattern)) - stage_paths
            stage.with_name(stage.name + "-wal").write_bytes(b"late sidecar")
            link(*args, **kwargs)

        with (patch.object(receipts.os, "link", add_sidecar_then_link),
              self.assertRaises(recovery.DecimalRecoveryDenied)):
            publish()
        stage, = set(target.parent.glob(pattern)) - stage_paths
        sidecar = stage.with_name(stage.name + "-wal")
        self.assertTrue(stage.samefile(target))
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            cleanup(stage)
        self.assertEqual(sidecar.read_bytes(), b"late sidecar")
        self.assertTrue(stage.samefile(target))
        sidecar.unlink()
        self.assertEqual(inspect(), {"receipt": tip, "additionalLinkPresent": True})
        cleanup(stage)
        self.assertFalse(stage.exists())
        self.assertEqual(inspect(), {"receipt": tip, "additionalLinkPresent": False})
        self.assertEqual({path: path.read_bytes() for path in preserved}, preserved)
        self.assertEqual({path: path.read_bytes() for path in evidence}, evidence)

    def test_terminal_publication_preserves_relocated_directories_and_changed_loser(self):
        retained, evidence, _, _ = self.terminal_recovery_evidence()
        self.assert_publication_directory_review(
            self.pin_path, ".decimal-terminal-receipt-*/receipt.db",
            partial(retained.repair_local_terminal, self.pins, self.store, **evidence),
            partial(retained.inspect_local_terminal, self.pins, self.store, **evidence),
            lambda stage: retained.cleanup_local_terminal_stage(
                stage, self.pins, self.store, **evidence),
            evidence["reviewed_receipt"], (self.store_path, retained._store.path))

    def test_checkpoint_publication_preserves_relocated_directories_and_changed_loser(self):
        self.prepare_checkpoint()
        tip = self.promote()
        exported = self.checkpoint.export(expected_receipt=tip)
        independent = self.retain_independent_recovery_receipt(tip)
        self.checkpoint_path.unlink()
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.assert_publication_directory_review(
            self.checkpoint_path, ".edgepilot-checkpoint-*/checkpoint.db",
            partial(receipts.DecimalPromotionCheckpoint.recover,
                    self.checkpoint_path, exported, trusted_receipt=tip,
                    checkpoint_key=self.checkpoint_key, **evidence),
            partial(self.checkpoint.inspect_recovered, exported, trusted_receipt=tip, **evidence),
            lambda stage: self.checkpoint.cleanup_recovered_stage(
                stage, exported, trusted_receipt=tip, **evidence),
            tip, (self.pin_path, self.store_path, self.path, independent._store.path))

    def assert_publication_directory_review(
            self, target, pattern, publish, inspect, cleanup, tip, evidence_paths):
        link = os.link
        expected = {"receipt": tip, "additionalLinkPresent": True}
        evidence = {path: path.read_bytes() for path in evidence_paths}
        for moved_directory in ("staging", "destination"):
            for move_before_link in (True, False):
                with self.subTest(directory=moved_directory, before_link=move_before_link):
                    prior = set(target.parent.glob(pattern))
                    moved = []

                    def relocate(*args, **kwargs):
                        stage, = set(target.parent.glob(pattern)) - prior
                        directory = stage.parent if moved_directory == "staging" else target.parent
                        held = directory.with_name(directory.name + ".relocated")
                        if not move_before_link:
                            link(*args, **kwargs)
                        directory.rename(held)
                        directory.mkdir(mode=0o700)
                        note = directory / "operator-note"
                        note.write_bytes(b"unrelated replacement")
                        moved.append((stage, directory, held, note))
                        if move_before_link:
                            link(*args, **kwargs)

                    with (patch.object(receipts.os, "link", relocate),
                          self.assertRaises(recovery.DecimalRecoveryDenied)):
                        publish()
                    (stage, directory, held, note), = moved
                    held_stage = held / stage.relative_to(directory)
                    published = target if moved_directory == "staging" else held / target.name
                    self.assertTrue(held_stage.samefile(published))
                    if moved_directory == "staging":
                        self.assertEqual(inspect(), expected)
                    else:
                        with self.assertRaises(recovery.DecimalRecoveryDenied):
                            inspect()
                    with self.assertRaises(recovery.DecimalRecoveryDenied):
                        cleanup(stage)
                    self.assertTrue(held_stage.samefile(published))
                    self.assertEqual(note.read_bytes(), b"unrelated replacement")
                    note.rename(held / note.name)
                    directory.rmdir()
                    held.rename(directory)
                    self.assertEqual(inspect(), expected)
                    cleanup(stage)
                    self.assertFalse(stage.exists())
                    self.assertEqual(inspect(), expected | {"additionalLinkPresent": False})
                    self.assertEqual((directory / note.name).read_bytes(), b"unrelated replacement")
                    (directory / note.name).unlink()
                    target.unlink()

        prior = set(target.parent.glob(pattern))
        losing_stages = []

        def arrive_then_replace(*args, **kwargs):
            stage, = set(target.parent.glob(pattern)) - prior
            replacement = stage.with_suffix(".copy")
            shutil.copyfile(stage, target)
            target.chmod(0o600)
            stage.rename(replacement)
            stage.write_bytes(b"unreviewed stage")
            stage.chmod(0o600)
            note = stage.with_name("operator-note")
            note.write_bytes(b"unrelated")
            losing_stages.append((stage, replacement, note))
            link(*args, **kwargs)

        with (patch.object(receipts.os, "link", arrive_then_replace),
              self.assertRaises(recovery.DecimalRecoveryDenied)):
            publish()
        (stage, original_stage, note), = losing_stages
        self.assertEqual(inspect(), expected | {"additionalLinkPresent": False})
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            cleanup(stage)
        self.assertEqual(original_stage.read_bytes(), target.read_bytes())
        self.assertEqual(stage.read_bytes(), b"unreviewed stage")
        self.assertEqual(note.read_bytes(), b"unrelated")
        self.assertEqual({path: path.read_bytes() for path in evidence}, evidence)
        target.unlink()
        prior = set(target.parent.glob(pattern))
        independent = evidence_paths[-1]
        held_evidence = independent.with_suffix(".held")

        def arrive_then_move_evidence(*args, **kwargs):
            candidate, = set(target.parent.glob(pattern)) - prior
            shutil.copyfile(candidate, target)
            target.chmod(0o600)
            independent.rename(held_evidence)
            link(*args, **kwargs)

        with (patch.object(receipts.os, "link", arrive_then_move_evidence),
              self.assertRaises(recovery.DecimalRecoveryDenied)):
            publish()
        candidate, = set(target.parent.glob(pattern)) - prior
        self.assertEqual(candidate.read_bytes(), target.read_bytes())
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            inspect()
        held_evidence.rename(independent)
        self.assertEqual(inspect(), expected | {"additionalLinkPresent": False})
        self.assertEqual({path: path.read_bytes() for path in evidence}, evidence)

    def test_terminal_readback_revalidates_destination_permissions(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        make_recheck = receipts._evidence_recheck
        parent = self.pin_path.parent

        def change_after_review(*paths):
            recheck = make_recheck(*paths)

            def change_directory():
                recheck()
                parent.chmod(0o750)

            return change_directory

        try:
            with (patch.object(receipts, "_evidence_recheck", change_after_review),
                  self.assertRaises(recovery.DecimalRecoveryDenied)):
                retained.inspect_local_terminal(self.pins, self.store, **evidence)
        finally:
            parent.chmod(0o700)
        self.assertTrue(stage.samefile(self.pin_path))
        self.assertEqual(retained.inspect_local_terminal(self.pins, self.store, **evidence),
                         {"receipt": evidence["reviewed_receipt"], "additionalLinkPresent": True})

    def test_terminal_cleanup_rechecks_exact_publication_and_evidence_after_unlink(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        self.assert_cleanup_final_review(
            self.pin_path, stage, retained._store.path,
            partial(retained.inspect_local_terminal, self.pins, self.store, **evidence),
            partial(retained.cleanup_local_terminal_stage, stage, self.pins, self.store, **evidence),
            evidence["reviewed_receipt"])

    def test_checkpoint_cleanup_rechecks_exact_publication_and_evidence_after_unlink(self):
        stage, exported, tip = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.assert_cleanup_final_review(
            self.checkpoint_path, stage, independent._store.path,
            partial(self.checkpoint.inspect_recovered, exported, trusted_receipt=tip, **evidence),
            partial(self.checkpoint.cleanup_recovered_stage, stage, exported,
                    trusted_receipt=tip, **evidence),
            tip)

    def assert_cleanup_final_review(self, target, stage, independent, inspect, cleanup, tip):
        sync, unlink = os.fsync, os.unlink
        expected = {"receipt": tip, "additionalLinkPresent": False}
        published = target.read_bytes()
        note = stage.with_name("operator-note")
        note.write_bytes(b"preserve")

        # A replacement directory can contain the exact link. Cleanup must
        # refuse it if the directory changed while opening the selection.
        folder = stage.parent
        held_folder = folder.with_name(folder.name + ".held")
        open_path = os.open

        def displace_on_open(path, *args, **kwargs):
            if path == folder:
                folder.rename(held_folder)
                folder.mkdir(mode=0o700)
                (held_folder / stage.name).rename(stage)
            return open_path(path, *args, **kwargs)

        with (patch.object(receipts.os, "open", displace_on_open),
              self.assertRaises(recovery.DecimalRecoveryDenied)):
            cleanup()
        self.assertTrue(stage.samefile(target))
        self.assertEqual((held_folder / note.name).read_bytes(), b"preserve")
        stage.rename(held_folder / stage.name)
        folder.rmdir()
        held_folder.rename(folder)

        self.assert_stage_replacement_survives_cleanup(target, stage, inspect, cleanup, tip)

        for event in ("destination at unlink", "destination at sync", "evidence at sync",
                      "sidecar at sync", "stage at sync", "process exit"):
            with self.subTest(event=event):
                saved_target = target.with_suffix(".held")
                saved_evidence = independent.with_suffix(".held")
                sidecar = target.with_name(target.name + "-wal")

                def replace_target():
                    target.rename(saved_target)
                    target.write_bytes(published)
                    target.chmod(0o600)

                def unlink_then_replace(*args, **kwargs):
                    unlink(*args, **kwargs)
                    replace_target()

                def interfere_at_sync(fd):
                    sync(fd)
                    if not os.path.samestat(os.fstat(fd), folder.stat()):
                        return
                    if event == "destination at sync":
                        replace_target()
                    elif event == "evidence at sync":
                        independent.rename(saved_evidence)
                    elif event == "sidecar at sync":
                        sidecar.write_bytes(b"ambiguous sidecar")
                    elif event == "stage at sync":
                        stage.write_bytes(b"unrelated candidate")
                    elif event == "process exit":
                        os._exit(95)

                def run_cleanup():
                    if event == "destination at unlink":
                        with patch.object(receipts.os, "unlink", unlink_then_replace):
                            cleanup()
                    else:
                        with patch.object(receipts.os, "fsync", interfere_at_sync):
                            cleanup()

                if event == "process exit":
                    pid = os.fork()
                    if pid == 0:
                        try:
                            run_cleanup()
                        finally:
                            os._exit(96)
                    _, status = os.waitpid(pid, 0)
                    self.assertEqual(os.waitstatus_to_exitcode(status), 95)
                else:
                    with self.assertRaises(recovery.DecimalRecoveryDenied):
                        run_cleanup()
                if saved_target.exists():
                    # Fresh readback can accept the authenticated identical
                    # replacement even though the interrupted operation refused it.
                    self.assertEqual(inspect(), expected)
                    self.assertFalse(saved_target.samefile(target))
                    saved_target.replace(target)
                if saved_evidence.exists():
                    with self.assertRaises(recovery.DecimalRecoveryDenied):
                        inspect()
                    saved_evidence.rename(independent)
                if sidecar.exists():
                    with self.assertRaises(recovery.DecimalRecoveryDenied):
                        inspect()
                    self.assertEqual(sidecar.read_bytes(), b"ambiguous sidecar")
                    sidecar.unlink()
                if stage.exists():
                    self.assertEqual(stage.read_bytes(), b"unrelated candidate")
                    with self.assertRaises(recovery.DecimalRecoveryDenied):
                        cleanup()
                    self.assertEqual(stage.read_bytes(), b"unrelated candidate")
                    stage.unlink()
                self.assertEqual(inspect(), expected)
                self.assertEqual(target.read_bytes(), published)
                self.assertEqual(note.read_bytes(), b"preserve")
                if event != "process exit":
                    os.link(target, stage)

    def assert_stage_replacement_survives_cleanup(self, target, stage, inspect, cleanup, tip):
        check_sidecars = receipts._require_no_sidecars
        held = stage.with_suffix(".held")
        start = Barrier(2, timeout=5)
        changed = Event()

        def replace_at_final_check(*paths):
            check_sidecars(*paths)
            if paths == (target, stage) and not changed.is_set():
                stage.rename(held)
                stage.write_bytes(b"unrelated replacement")
                changed.set()

        def compete():
            start.wait()
            cleanup()

        with (patch.object(receipts, "_require_no_sidecars", replace_at_final_check),
              ThreadPoolExecutor(max_workers=2) as pool):
            attempts = [pool.submit(compete) for _ in range(2)]
            for attempt in attempts:
                with self.assertRaises(recovery.DecimalRecoveryDenied):
                    attempt.result(timeout=5)
        self.assertTrue(changed.is_set())
        self.assertTrue(held.samefile(target))
        self.assertEqual(stage.read_bytes(), b"unrelated replacement")
        self.assertEqual(inspect(), {"receipt": tip, "additionalLinkPresent": True})
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            cleanup()
        stage.rename(stage.with_suffix(".unrelated"))
        held.rename(stage)

    def test_terminal_review_refuses_late_publication_and_stage_sidecars(self):
        retained, evidence, terminal_stage, _ = self.terminal_cleanup_fixture()
        self.assert_cleanup_preserves_late_sidecars(
            self.pin_path, terminal_stage,
            partial(retained.inspect_local_terminal, self.pins, self.store, **evidence),
            partial(retained.cleanup_local_terminal_stage, terminal_stage, self.pins, self.store,
                    **evidence), evidence["reviewed_receipt"])

    def test_checkpoint_review_refuses_late_publication_and_stage_sidecars(self):
        stage, exported, tip = self.reviewed_staging_link()
        inspect = partial(self.checkpoint.inspect_recovered, exported, trusted_receipt=tip,
                          **self.recovery_evidence())
        cleanup = partial(self.cleanup_stage, stage, exported, tip)
        self.assert_cleanup_preserves_late_sidecars(self.checkpoint_path, stage, inspect, cleanup, tip)

    def assert_cleanup_preserves_late_sidecars(self, target, stage, inspect, cleanup, tip):
        content = target.read_bytes()
        sync = receipts._sync_directory
        read_published = receipts.DecimalReceiptStore._read_published
        expected = {"receipt": tip, "additionalLinkPresent": True}
        foreign = b"unreviewed SQLite sidecar"

        for path in (stage, target):
            for suffix in ("-journal", "-wal", "-shm"):
                with self.subTest(path=path, suffix=suffix):
                    sidecar = path.with_name(path.name + suffix)

                    def sync_then_create(directory):
                        sync(directory)
                        sidecar.write_bytes(foreign)

                    try:
                        with (patch.object(receipts, "_sync_directory", sync_then_create),
                              self.assertRaises(recovery.DecimalRecoveryDenied)):
                            cleanup()
                        if path == stage:
                            self.assertEqual(inspect(), expected)
                        else:
                            with self.assertRaises(recovery.DecimalRecoveryDenied):
                                inspect()
                        self.assertEqual(sidecar.read_bytes(), foreign)
                        self.assertTrue(stage.samefile(target))
                        self.assertEqual(target.read_bytes(), content)
                    finally:
                        sidecar.unlink(missing_ok=True)

        sidecar = target.with_name(target.name + "-wal")
        @contextmanager
        def create_during_readback(store, receipt):
            with read_published(store, receipt) as verified:
                sidecar.write_bytes(foreign)
                yield verified

        try:
            with (patch.object(receipts.DecimalReceiptStore, "_read_published", create_during_readback),
                  self.assertRaises(recovery.DecimalRecoveryDenied)):
                inspect()
            self.assertEqual(sidecar.read_bytes(), foreign)
            self.assertTrue(stage.samefile(target))
        finally:
            sidecar.unlink(missing_ok=True)
        self.assertEqual(inspect(), expected)
        cleanup()
        self.assertFalse(stage.exists())
        self.assertEqual(target.read_bytes(), content)
        self.assertEqual(inspect(), {"receipt": tip, "additionalLinkPresent": False})

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

    def retain_independent_recovery_receipt(self, tip):
        folder = tempfile.TemporaryDirectory(prefix="decimal-independent-checkpoint-")
        self.addCleanup(folder.cleanup)
        return receipts.DecimalRecoveryReceipt.create(
            Path(folder.name) / "recovery.db", receipt_key=os.urandom(32),
            receipts=self.pins, witness=self.store, reviewed_receipt=tip)

    def test_independent_receipt_blocks_joint_active_checkpoint_rollback(self):
        stage, exported, active = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(active)
        old_files = {path: path.read_bytes() for path in (self.pin_path, self.store_path, self.path)}
        publication = self.checkpoint_path.read_bytes()
        quarantine = recovery.quarantine_decimal_recovery(
            record=self.promotion, trusted_tip=recovery.evidence_tip(self.promotion),
            operator_key=self.operator, reason="INTEGRITY_FAILURE")
        unrelated = stage.with_name("operator-note")
        unrelated.write_bytes(b"preserve")
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        save = self.pins._save

        def exit_before_local_acknowledgment(db, tip, *, pending):
            if not pending:
                os._exit(95)
            save(db, tip, pending=pending)

        pid = os.fork()
        if pid == 0:
            try:
                with patch.object(self.pins, "_save", exit_before_local_acknowledgment):
                    self.pins.publish(self.store, quarantine)
                    independent.retain_terminal(
                        self.pins, self.store, expected_receipt=active,
                        reviewed_receipt=self.pins.latest(), operator_record=quarantine)
            finally:
                os._exit(96)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 95)
        record, terminal, _ = self.store.read(trusted_receipt=active)
        self.assertEqual(record, quarantine)
        self.assertEqual(independent._store.latest(), active)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.pins.latest()

        def inspect(**options):
            return self.checkpoint.inspect_recovered(exported, trusted_receipt=active, **options)

        # The witness committed before either receipt acknowledged quarantine.
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            inspect(**evidence)
        frozen = self.pin_path.read_bytes()
        for reviewed, operator_record in ((active, quarantine), (terminal, self.promotion)):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                independent.retain_terminal(
                    self.pins, self.store, expected_receipt=active, reviewed_receipt=reviewed,
                    operator_record=operator_record)
            self.assertEqual(independent._store.latest(), active)
            self.assertEqual(self.pin_path.read_bytes(), frozen)

        original = self.store_path.with_suffix(".original")
        signed_bytes = self.store_path.read_bytes()
        save_independent = independent._store._save

        def replace_witness_during_retention(db, tip, *, pending):
            save_independent(db, tip, pending=pending)
            self.store_path.rename(original)
            self.store_path.write_bytes(signed_bytes)
            self.store_path.chmod(0o600)

        with patch.object(independent._store, "_save", replace_witness_during_retention):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                independent.retain_terminal(
                    self.pins, self.store, expected_receipt=active, reviewed_receipt=terminal,
                    operator_record=quarantine)
        self.assertFalse(self.store_path.samefile(original))
        original.replace(self.store_path)
        self.assertEqual(independent._store.latest(), active)
        pid = os.fork()
        if pid == 0:
            try:
                independent.retain_terminal(
                    self.pins, self.store, expected_receipt=active, reviewed_receipt=terminal,
                    operator_record=quarantine)
                os._exit(95)
            finally:
                os._exit(96)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 95)
        self.assertEqual(independent._store.latest(), terminal)
        reviewed_terminal = dict(reviewed_receipt=terminal, operator_record=quarantine)

        def read_handoff(**review):
            return independent.inspect_terminal_handoff(self.pins, self.store, **review)

        independently_retained = independent._store.path.read_bytes()
        for _ in range(2):
            self.assertEqual(read_handoff(**reviewed_terminal),
                             {"receipt": terminal, "localRepairRequired": True})
            self.assertEqual(self.pin_path.read_bytes(), frozen)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            read_handoff(**(reviewed_terminal | {"operator_record": self.promotion}))
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            read_handoff(**(reviewed_terminal | {"reviewed_receipt": None}))
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            independent.repair_local_terminal(
                self.pins, self.store, **(reviewed_terminal | {"reviewed_receipt": active}))
        self.assertEqual(self.pin_path.read_bytes(), frozen)

        held_local = self.pin_path.with_suffix(".held")
        save_local = self.pins._save

        def replace_local_during_repair(db, tip, *, pending):
            save_local(db, tip, pending=pending)
            self.pin_path.rename(held_local)
            self.pin_path.write_bytes(frozen)
            self.pin_path.chmod(0o600)

        with patch.object(self.pins, "_save", replace_local_during_repair):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                independent.repair_local_terminal(self.pins, self.store, **reviewed_terminal)
        self.assertEqual(self.pin_path.read_bytes(), frozen)
        held_local.replace(self.pin_path)
        self.assertEqual(read_handoff(**reviewed_terminal),
                         {"receipt": terminal, "localRepairRequired": True})

        class ExitAfterCommit(sqlite3.Connection):
            def commit(self):
                super().commit()
                os._exit(97)

        pid = os.fork()
        if pid == 0:
            try:
                connect = partial(sqlite3.connect, factory=ExitAfterCommit)
                with patch.object(receipts.sqlite3, "connect", connect):
                    independent.repair_local_terminal(self.pins, self.store, **reviewed_terminal)
            finally:
                os._exit(98)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 97)

        reopened = receipts.DecimalRecoveryReceipt(
            independent._store.path, receipt_key=independent._store.key)
        local = receipts.DecimalReceiptStore(self.pin_path, receipt_key=self.pins.key)
        witness = type(self.store)(self.store_path, custody_key=self.store.custody_key,
                                   operator_key=self.store.operator_key)
        self.assertEqual(local.latest(), terminal)
        repaired = self.pin_path.read_bytes()
        for _ in range(2):
            self.assertEqual(reopened.inspect_terminal_handoff(local, witness, **reviewed_terminal),
                             {"receipt": terminal, "localRepairRequired": False})
            self.assertEqual(reopened.repair_local_terminal(local, witness, **reviewed_terminal),
                             terminal)
            self.assertEqual(self.pin_path.read_bytes(), repaired)
            self.assertEqual(self.store_path.read_bytes(), signed_bytes)
            self.assertEqual(independent._store.path.read_bytes(), independently_retained)

        for path, content in old_files.items():
            path.write_bytes(content)
        self.assertEqual(inspect(**self.recovery_evidence()),
                         {"receipt": active, "additionalLinkPresent": True})
        missing = self.checkpoint_path.with_name("missing-checkpoint.db")
        for operation in (
                lambda: inspect(**evidence),
                lambda: self.checkpoint.cleanup_recovered_stage(
                    stage, exported, trusted_receipt=active, **evidence),
                lambda: receipts.DecimalPromotionCheckpoint.recover(
                    missing, exported, trusted_receipt=active, checkpoint_key=self.checkpoint_key,
                    **evidence)):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                operation()
            self.assertFalse(missing.exists())
            self.assertTrue(stage.samefile(self.checkpoint_path))
            self.assertEqual(self.checkpoint_path.read_bytes(), publication)
            self.assertEqual(unrelated.read_bytes(), b"preserve")
        self.assertEqual(independent._store.latest(), terminal)

    def test_independent_receipt_is_rechecked_at_checkpoint_publication(self):
        self.prepare_checkpoint()
        tip = self.promote()
        exported = self.checkpoint.export(expected_receipt=tip)
        independent = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.checkpoint_path.unlink()
        original = independent._store.path
        saved = original.with_suffix(".held")
        content = original.read_bytes()
        sync = receipts._sync_directory

        def replace_after_sync(path):
            sync(path)
            original.rename(saved)
            original.write_bytes(content)
            original.chmod(0o600)

        with patch.object(receipts, "_sync_directory", replace_after_sync):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                receipts.DecimalPromotionCheckpoint.recover(
                    self.checkpoint_path, exported, trusted_receipt=tip,
                    checkpoint_key=self.checkpoint_key, **evidence)
        saved.replace(original)
        stage, = self.checkpoint_path.parent.glob(".edgepilot-checkpoint-*/checkpoint.db")
        self.assertTrue(stage.samefile(self.checkpoint_path))
        for _ in range(2):
            self.assertEqual(self.checkpoint.inspect_recovered(
                exported, trusted_receipt=tip, **evidence),
                {"receipt": tip, "additionalLinkPresent": True})
        self.checkpoint.cleanup_recovered_stage(stage, exported, trusted_receipt=tip, **evidence)
        self.assertFalse(stage.exists())
        self.assertEqual(self.checkpoint.inspect_recovered(
            exported, trusted_receipt=tip, **evidence),
            {"receipt": tip, "additionalLinkPresent": False})

    def test_checkpoint_readback_and_cleanup_wait_for_independent_receipt_rollback(self):
        stage, exported, tip = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        unrelated = stage.with_name("operator-note")
        unrelated.write_bytes(b"preserve")
        receipt_file = independent._store.path.read_bytes()
        published_info, published_bytes = self.checkpoint_path.stat(), self.checkpoint_path.read_bytes()

        def inspect():
            return self.checkpoint.inspect_recovered(exported, trusted_receipt=tip, **evidence)

        def cleanup():
            self.checkpoint.cleanup_recovered_stage(stage, exported, trusted_receipt=tip, **evidence)

        pin = independent._store._pin
        with ThreadPoolExecutor(max_workers=1) as pool:
            for operation in (inspect, cleanup):
                with self.subTest(operation=operation.__name__):
                    attempting_pin = Event()

                    def mark_pin(*args, **kwargs):
                        attempting_pin.set()
                        return pin(*args, **kwargs)

                    with patch.object(independent._store, "_pin", mark_pin):
                        with independent._store._open() as db:
                            independent._store._save(db, tip, pending=True)
                            pending = pool.submit(operation)
                            self.assertTrue(attempting_pin.wait(timeout=3))
                            with self.assertRaises(TimeoutError):
                                pending.result(timeout=0.05)
                            self.assertTrue(stage.samefile(self.checkpoint_path))
                            db.rollback()
                        result = pending.result(timeout=5)
                    if operation is inspect:
                        self.assertEqual(result, {"receipt": tip, "additionalLinkPresent": True})
                    self.assertEqual(independent._store.path.read_bytes(), receipt_file)
                    self.assertTrue(os.path.samestat(self.checkpoint_path.stat(), published_info))
                    self.assertEqual(self.checkpoint_path.read_bytes(), published_bytes)
                    self.assertEqual(unrelated.read_bytes(), b"preserve")
        self.assertFalse(stage.exists())
        for _ in range(2):
            self.assertEqual(inspect(), {"receipt": tip, "additionalLinkPresent": False})

    def test_active_checkpoint_operations_refuse_an_independent_commit_while_waiting(self):
        stage, exported, active = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(active)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        unrelated = stage.with_name("operator-note")
        unrelated.write_bytes(b"preserve")
        published = self.checkpoint_path.read_bytes()
        record, terminal, _ = self.advance_signed_witness(active)
        store = independent._store
        pin, save = store._pin, store._save
        attempting_pin = Barrier(3, timeout=5)
        operations = []

        def mark_pin(*args, **kwargs):
            attempting_pin.wait()
            return pin(*args, **kwargs)

        def inspect():
            return self.checkpoint.inspect_recovered(exported, trusted_receipt=active, **evidence)

        def cleanup():
            self.checkpoint.cleanup_recovered_stage(stage, exported, trusted_receipt=active,
                                                    **evidence)

        with ThreadPoolExecutor(max_workers=2) as pool:
            def hold_commit(db, tip, *, pending):
                save(db, tip, pending=pending)
                waiting = [pool.submit(inspect), pool.submit(cleanup)]
                operations.extend(waiting)
                attempting_pin.wait()
                for operation in waiting:
                    with self.assertRaises(TimeoutError):
                        operation.result(timeout=0.05)
                self.assertTrue(stage.samefile(self.checkpoint_path))

            with (patch.object(store, "_save", hold_commit),
                  patch.object(store, "_pin", mark_pin),
                  patch.object(self.pins, "_open", wraps=self.pins._open) as open_local):
                self.assertEqual(independent.retain_terminal(
                    self.pins, self.store, expected_receipt=active, reviewed_receipt=terminal,
                    operator_record=record), terminal)
                self.assertEqual(len(operations), 2)
                for operation in operations:
                    with self.assertRaises(recovery.DecimalRecoveryDenied):
                        operation.result(timeout=5)
                open_local.assert_not_called()
        self.assertEqual(store.latest(), terminal)
        self.assertTrue(stage.samefile(self.checkpoint_path))
        self.assertEqual(self.checkpoint_path.read_bytes(), published)
        self.assertEqual(unrelated.read_bytes(), b"preserve")

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

    def assert_publication_cleanup_interruption(self, target, pattern, publish, inspect, tip):
        unrelated = target.parent / pattern.replace("*", "unrelated")
        unrelated.parent.mkdir(mode=0o700)
        unrelated.write_bytes(b"separate staging candidate")
        fsync = os.fsync

        for process_exit in (True, False):
            with self.subTest(process_exit=process_exit):
                def stop_after_stage_unlink(fd):
                    if not target.exists() or os.path.samestat(os.fstat(fd), target.parent.stat()):
                        fsync(fd)
                        return
                    self.assertEqual(target.stat().st_nlink, 1)
                    if process_exit:
                        os._exit(95)
                    raise OSError("synthetic staging sync failure after unlink")

                def interrupt_publication():
                    with patch.object(receipts.os, "fsync", side_effect=stop_after_stage_unlink):
                        publish()

                if process_exit:
                    pid = os.fork()
                    if pid == 0:
                        try:
                            interrupt_publication()
                        finally:
                            os._exit(96)
                    _, status = os.waitpid(pid, 0)
                    self.assertEqual(os.waitstatus_to_exitcode(status), 95)
                else:
                    with self.assertRaises(recovery.DecimalRecoveryDenied):
                        interrupt_publication()

                original, content = target.stat(), target.read_bytes()
                self.assertEqual(list(target.parent.glob(pattern)), [unrelated])
                for _ in range(2):
                    self.assertEqual(inspect(), {"receipt": tip, "additionalLinkPresent": False})
                self.assertTrue(os.path.samestat(target.stat(), original))
                self.assertEqual(target.read_bytes(), content)
                self.assertEqual(unrelated.read_bytes(), b"separate staging candidate")
                if process_exit:
                    target.unlink()

    def test_terminal_publication_cleanup_interruption_after_unlink(self):
        retained, evidence, _, _ = self.terminal_recovery_evidence()
        self.assert_publication_cleanup_interruption(
            self.pin_path, ".decimal-terminal-receipt-*/receipt.db",
            lambda: retained.repair_local_terminal(self.pins, self.store, **evidence),
            lambda: retained.inspect_local_terminal(self.pins, self.store, **evidence),
            evidence["reviewed_receipt"])
        self.assertEqual(self.pins.latest(), evidence["reviewed_receipt"])
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            retained.inspect_local_terminal(self.pins, self.store, **(
                evidence | {"operator_record": self.promotion}))

    def test_checkpoint_publication_cleanup_interruption_after_unlink(self):
        self.prepare_checkpoint()
        tip = self.promote()
        exported = self.checkpoint.export(expected_receipt=tip)
        self.checkpoint_path.unlink()
        self.assert_publication_cleanup_interruption(
            self.checkpoint_path, ".edgepilot-checkpoint-*/checkpoint.db",
            lambda: self.recover_checkpoint(exported, tip),
            lambda: self.checkpoint.inspect_recovered(
                exported, trusted_receipt=tip, **self.recovery_evidence()),
            tip)
        self.assertEqual(self.checkpoint.latest(), tip)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.checkpoint.inspect_recovered(
                exported | {"mac": "0" * 64}, trusted_receipt=tip, **self.recovery_evidence())

    def assert_preserved_staging_inventory(
            self, target, pattern, publish, inspect, tip, independent):
        fsync = os.fsync
        folder_pattern, filename = pattern.split("/")
        separate = target.parent / folder_pattern.replace("*", "separate")
        separate.mkdir(mode=0o700)
        (separate / "operator-note").write_bytes(b"separate candidate")
        symlink = target.parent / folder_pattern.replace("*", "symlink")
        symlink.symlink_to(separate, target_is_directory=True)
        unrelated = target.parent / "unrelated-directory"
        unrelated.mkdir(mode=0o700)

        for outcome in ("exit-before-sync", "exit-after-sync", "sync-error",
                        "empty-replacement", "replace-destination", "move-evidence",
                        "populate-stage", "populated"):
            with self.subTest(outcome=outcome):
                existing = set(target.parent.glob(folder_pattern))
                saved_target = target.with_suffix(".held")
                saved_evidence = independent.with_suffix(".held")

                def at_parent_sync(fd):
                    if (not target.exists() or target.stat().st_nlink != 1
                            or not os.path.samestat(os.fstat(fd), target.parent.stat())):
                        fsync(fd)
                        return
                    folder, = set(target.parent.glob(folder_pattern)) - existing
                    self.assertEqual(list(folder.iterdir()), [])
                    if outcome == "exit-before-sync":
                        os._exit(95)
                    if outcome == "sync-error":
                        (folder / filename).write_bytes(b"unreviewed replacement")
                        raise OSError(errno.EIO, "synthetic parent sync error")
                    if outcome == "empty-replacement":
                        moved = folder.with_name(folder.name + ".moved")
                        folder.rename(moved)
                        (moved / "original-note").write_bytes(b"original directory")
                        folder.mkdir(mode=0o700)
                    if outcome == "replace-destination":
                        target.rename(saved_target)
                        shutil.copyfile(saved_target, target)
                        target.chmod(0o600)
                    if outcome == "move-evidence":
                        independent.rename(saved_evidence)
                    if outcome == "populate-stage":
                        (folder / filename).write_bytes(b"unreviewed replacement")
                    if outcome == "populated":
                        (folder / "operator-note").write_bytes(b"keep this file")
                    fsync(fd)
                    if outcome == "exit-after-sync":
                        os._exit(95)

                def run_publication():
                    with (patch.object(receipts.os, "fsync", at_parent_sync),
                          patch.object(receipts.os, "rmdir",
                                       side_effect=AssertionError("Stage directory removal is unsafe"))):
                        publish()

                if outcome == "populated":
                    run_publication()
                elif outcome.startswith("exit-"):
                    pid = os.fork()
                    if pid == 0:
                        try:
                            run_publication()
                        finally:
                            os._exit(96)
                    _, status = os.waitpid(pid, 0)
                    self.assertEqual(os.waitstatus_to_exitcode(status), 95)
                else:
                    with self.assertRaises(recovery.DecimalRecoveryDenied):
                        run_publication()

                remaining = set(target.parent.glob(folder_pattern)) - existing
                if outcome == "empty-replacement":
                    original, = [folder for folder in remaining if folder.name.endswith(".moved")]
                    folder = target.parent / original.name.removesuffix(".moved")
                    self.assertEqual(remaining, {folder, original})
                    self.assertEqual(list(folder.iterdir()), [])
                    self.assertEqual((original / "original-note").read_bytes(), b"original directory")
                else:
                    folder, = remaining
                if saved_evidence.exists():
                    with self.assertRaises(recovery.DecimalRecoveryDenied):
                        inspect(include_stages=True)
                    saved_evidence.rename(independent)
                if outcome == "exit-before-sync":
                    target.rename(saved_target)
                    target.write_bytes(b"unverified publication")
                    target.chmod(0o600)
                    with self.assertRaises(recovery.DecimalRecoveryDenied):
                        inspect(include_stages=True)
                    saved_target.replace(target)
                if outcome == "exit-after-sync":
                    (folder / filename).write_bytes(b"unreviewed replacement")
                if outcome in ("sync-error", "populate-stage", "exit-after-sync"):
                    self.assertEqual((folder / filename).read_bytes(), b"unreviewed replacement")
                if saved_target.exists():
                    self.assertFalse(saved_target.samefile(target))
                    self.assertEqual(saved_target.read_bytes(), target.read_bytes())
                    saved_target.unlink()

                expected = {"receipt": tip, "additionalLinkPresent": False}
                self.assertEqual(inspect(), expected)
                result = inspect(include_stages=True)
                inventory = {entry["name"]: entry for entry in result.pop("stages")}
                self.assertEqual(result, expected)
                directories = set(target.parent.glob(folder_pattern))
                self.assertEqual(set(inventory), {path.name for path in directories})
                for path in directories - {symlink}:
                    info = path.stat()
                    entries = sorted(entry.name for entry in path.iterdir())
                    self.assertEqual(inventory[path.name], {
                        "name": path.name, "device": info.st_dev, "inode": info.st_ino,
                        "state": "populated" if entries else "empty", "entries": entries,
                        "publicationLink": False})
                self.assertEqual(inventory[symlink.name]["state"], "unreviewed")
                self.assertIsNone(inventory[symlink.name]["entries"])
                self.assertEqual((separate / "operator-note").read_bytes(), b"separate candidate")
                target.unlink()

        existing_names = {path.name for path in target.parent.glob(folder_pattern)}
        publish()
        empty, = [entry for entry in inspect(include_stages=True)["stages"]
                  if entry["name"] not in existing_names]
        stage = target.parent / empty["name"] / filename
        os.link(target, stage)
        linked = inspect(include_stages=True)
        self.assertTrue(linked["additionalLinkPresent"])
        self.assertTrue(next(entry for entry in linked["stages"]
                             if entry["name"] == empty["name"])["publicationLink"])

        listdir = os.listdir
        stage_identity = stage.parent.stat()
        late = stage.with_name("late-note")

        def change_inventory(fd):
            names = listdir(fd)
            if os.path.samestat(os.fstat(fd), stage_identity) and not late.exists():
                late.write_bytes(b"preserve")
            return names

        with (patch.object(receipts.os, "listdir", change_inventory),
              self.assertRaises(recovery.DecimalRecoveryDenied)):
            inspect(include_stages=True)
        self.assertEqual(late.read_bytes(), b"preserve")
        self.assertEqual(inspect(include_stages=True)["receipt"], tip)

    def test_terminal_publication_preserves_and_inventories_stage_directories(self):
        retained, evidence, _, _ = self.terminal_recovery_evidence()
        self.assert_preserved_staging_inventory(
            self.pin_path, ".decimal-terminal-receipt-*/receipt.db",
            partial(retained.repair_local_terminal, self.pins, self.store, **evidence),
            partial(retained.inspect_local_terminal, self.pins, self.store, **evidence),
            evidence["reviewed_receipt"], retained._store.path)

    def test_checkpoint_publication_preserves_and_inventories_stage_directories(self):
        self.prepare_checkpoint()
        tip = self.promote()
        exported = self.checkpoint.export(expected_receipt=tip)
        independent = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.checkpoint_path.unlink()
        self.assert_preserved_staging_inventory(
            self.checkpoint_path, ".edgepilot-checkpoint-*/checkpoint.db",
            partial(receipts.DecimalPromotionCheckpoint.recover,
                    self.checkpoint_path, exported, trusted_receipt=tip,
                    checkpoint_key=self.checkpoint_key, **evidence),
            partial(self.checkpoint.inspect_recovered, exported, trusted_receipt=tip, **evidence),
            tip, independent._store.path)

    def assert_missing_publication_inventory(
            self, target, prefix, filename, publish, inspect, cleanup, evidence_path, tip):
        empty = target.parent / (prefix + "empty")
        empty.mkdir(mode=0o700)
        symlink = target.parent / (prefix + "symlink")
        symlink.symlink_to(empty)

        pid = os.fork()
        if pid == 0:
            try:
                with patch.object(receipts.os, "link", side_effect=lambda *a, **kw: os._exit(95)):
                    publish()
            finally:
                os._exit(96)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 95)
        stage, = set(target.parent.glob(prefix + "*")) - {empty, symlink}
        candidate = stage / filename
        content = candidate.read_bytes()
        candidate_stat = candidate.stat()
        self.assertFalse(target.exists())
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            inspect()

        def describe(path, state, entries):
            info = path.lstat()
            return {"name": path.name, "device": info.st_dev, "inode": info.st_ino,
                    "state": state, "entries": entries, "publicationLink": False}

        inventory = [describe(empty, "empty", []), describe(stage, "populated", [filename]),
                     describe(symlink, "unreviewed", None)]
        expected = {"receipt": tip, "publicationMissing": True,
                    "stages": sorted(inventory, key=lambda entry: entry["name"])}
        self.assertEqual(inspect(include_stages=True), expected)

        inventory_stages = receipts._stage_inventory
        sidecar = target.with_name(target.name + "-wal")
        held_evidence = evidence_path.with_suffix(".held")
        for late_path in (target, sidecar, held_evidence):
            with self.subTest(late_path=late_path.name):
                def interfere(*args):
                    result = inventory_stages(*args)
                    if late_path == held_evidence:
                        evidence_path.rename(held_evidence)
                    else:
                        late_path.write_bytes(b"unrelated file")
                    return result

                with (patch.object(receipts, "_stage_inventory", interfere),
                      self.assertRaises(recovery.DecimalRecoveryDenied)):
                    inspect(include_stages=True)
                if late_path == held_evidence:
                    held_evidence.rename(evidence_path)
                else:
                    self.assertEqual(late_path.read_bytes(), b"unrelated file")
                    late_path.unlink()

        target.symlink_to(candidate)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            inspect(include_stages=True)
        target.unlink()
        self.assertEqual(inspect(include_stages=True), expected)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            cleanup(candidate)
        self.assertEqual(candidate.stat(), candidate_stat)
        self.assertEqual(candidate.read_bytes(), content)
        self.assertFalse(target.exists())

    def test_terminal_inventory_after_exit_before_publication(self):
        retained, evidence, _, _ = self.terminal_recovery_evidence()
        self.assert_missing_publication_inventory(
            self.pin_path, ".decimal-terminal-receipt-", "receipt.db",
            partial(retained.repair_local_terminal, self.pins, self.store, **evidence),
            partial(retained.inspect_local_terminal, self.pins, self.store, **evidence),
            lambda stage: retained.cleanup_local_terminal_stage(
                stage, self.pins, self.store, **evidence),
            retained._store.path, evidence["reviewed_receipt"])

    def test_checkpoint_inventory_after_exit_before_publication_requires_independent_pin(self):
        self.prepare_checkpoint()
        tip = self.promote()
        exported = self.checkpoint.export(expected_receipt=tip)
        independent = self.retain_independent_recovery_receipt(tip)
        self.checkpoint_path.unlink()
        evidence = self.recovery_evidence() | {"trusted_receipt": tip}
        inspect = partial(self.checkpoint.inspect_recovered, exported, **evidence)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            inspect(include_stages=True)
        self.assert_missing_publication_inventory(
            self.checkpoint_path, ".edgepilot-checkpoint-", "checkpoint.db",
            partial(receipts.DecimalPromotionCheckpoint.recover, self.checkpoint_path, exported,
                    checkpoint_key=self.checkpoint_key, recovery_receipt=independent, **evidence),
            partial(inspect, recovery_receipt=independent),
            lambda stage: self.checkpoint.cleanup_recovered_stage(
                stage, exported, recovery_receipt=independent, **evidence),
            independent._store.path, tip)

    def copy_receipt_file(self, store):
        folder = tempfile.TemporaryDirectory(prefix="decimal-concurrent-publication-")
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / store.path.name
        shutil.copyfile(store.path, path)
        path.chmod(0o600)
        return path

    def assert_concurrent_missing_inventory(
            self, target, prefix, filename, publish, inspect, independent, tip):
        abandoned = target.parent / (prefix + "interrupted")
        abandoned.mkdir(mode=0o700)
        candidate = abandoned / filename
        candidate.write_bytes(b"unreviewed prior candidate")
        listdir = os.listdir
        link = os.link

        for timing in ("already-staging", "during-scan"):
            with self.subTest(timing=timing), ThreadPoolExecutor(max_workers=1) as pool:
                staged, allow_link = Event(), Event()
                writer_folders = set(target.parent.glob(prefix + "*"))

                def pause_at_link(*args, **kwargs):
                    staged.set()
                    if not allow_link.wait(timeout=5):
                        raise TimeoutError("Timed out releasing the staged publisher")
                    return link(*args, **kwargs)

                def publish_during_scan(fd):
                    names = listdir(fd)
                    if not staged.is_set() and os.path.samestat(os.fstat(fd), target.parent.stat()):
                        publisher = pool.submit(publish)
                        self.assertTrue(staged.wait(timeout=5))
                        allow_link.set()
                        publisher.result(timeout=5)
                    return names

                with patch.object(receipts.os, "link", pause_at_link):
                    if timing == "already-staging":
                        publisher = pool.submit(publish)
                        try:
                            self.assertTrue(staged.wait(timeout=5))
                            stage, = set(target.parent.glob(prefix + "*")) - writer_folders
                            self.assertTrue((stage / filename).is_file())
                            self.assertFalse(target.exists())
                            with self.assertRaises(recovery.DecimalRecoveryDenied):
                                inspect(include_stages=True)
                            self.assertTrue((stage / filename).is_file())
                            self.assertFalse(target.exists())
                        finally:
                            allow_link.set()
                        publisher.result(timeout=5)
                    else:
                        with (patch.object(receipts.os, "listdir", publish_during_scan),
                              self.assertRaises(recovery.DecimalRecoveryDenied)):
                            inspect(include_stages=True)
                        self.assertTrue(staged.is_set())
                        self.assertTrue(target.is_file())

                self.assertEqual(inspect(), {"receipt": tip, "additionalLinkPresent": False})
                self.assertEqual(candidate.read_bytes(), b"unreviewed prior candidate")
                target.unlink()

        moved = abandoned.with_name(abandoned.name + ".moved")
        original = abandoned.stat()

        def rename_during_scan(fd):
            names = listdir(fd)
            if not moved.exists() and os.path.samestat(os.fstat(fd), original):
                abandoned.rename(moved)
                abandoned.mkdir(mode=0o700)
                candidate.write_bytes(b"unreviewed replacement")
            return names

        with (patch.object(receipts.os, "listdir", rename_during_scan),
              self.assertRaises(recovery.DecimalRecoveryDenied)):
            inspect(include_stages=True)
        result = inspect(include_stages=True)
        self.assertTrue(result["publicationMissing"])
        stages = {stage["name"]: stage for stage in result["stages"]}
        self.assertEqual(stages[moved.name]["inode"], original.st_ino)
        self.assertFalse(stages[abandoned.name]["publicationLink"])

        # A previously signed pin cannot establish this missing publication.
        pin_bytes = independent.path.read_bytes()
        with independent._open() as db:
            independent._save(db, self.claim, pending=False)
            db.commit()
        try:
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                inspect(include_stages=True)
        finally:
            independent.path.write_bytes(pin_bytes)
        self.assertEqual(inspect(include_stages=True), result)
        self.assertEqual((moved / filename).read_bytes(), b"unreviewed prior candidate")
        self.assertEqual(candidate.read_bytes(), b"unreviewed replacement")
        self.assertFalse(target.exists())

    def test_terminal_inventory_refuses_concurrent_staging_and_publication(self):
        retained, evidence, _, _ = self.terminal_recovery_evidence()
        writer_pin = receipts.DecimalRecoveryReceipt(
            self.copy_receipt_file(retained._store), receipt_key=retained._store.key)
        self.assert_concurrent_missing_inventory(
            self.pin_path, ".decimal-terminal-receipt-", "receipt.db",
            partial(writer_pin.repair_local_terminal, self.pins, self.store, **evidence),
            partial(retained.inspect_local_terminal, self.pins, self.store, **evidence),
            retained._store, evidence["reviewed_receipt"])

    def test_checkpoint_inventory_refuses_concurrent_staging_and_publication(self):
        self.prepare_checkpoint()
        tip = self.promote()
        exported = self.checkpoint.export(expected_receipt=tip)
        retained = self.retain_independent_recovery_receipt(tip)
        writer_pin = receipts.DecimalRecoveryReceipt(
            self.copy_receipt_file(retained._store), receipt_key=retained._store.key)
        writer_receipts = receipts.DecimalReceiptStore(
            self.copy_receipt_file(self.pins), receipt_key=self.pins.key)
        evidence = self.recovery_evidence() | {"trusted_receipt": tip}
        writer_evidence = evidence | {"receipts": writer_receipts, "recovery_receipt": writer_pin}
        self.checkpoint_path.unlink()
        self.assert_concurrent_missing_inventory(
            self.checkpoint_path, ".edgepilot-checkpoint-", "checkpoint.db",
            partial(receipts.DecimalPromotionCheckpoint.recover, self.checkpoint_path, exported,
                    checkpoint_key=self.checkpoint_key, **writer_evidence),
            partial(self.checkpoint.inspect_recovered, exported, recovery_receipt=retained, **evidence),
            retained._store, tip)


    def assert_shared_evidence_exit_readback(
            self, target, prefix, filename, publish, inspect, cleanup, tip, evidence_paths):
        """Fork a real publisher with the reviewer's same independent evidence files."""
        original_link = os.link
        original_evidence = {path: path.read_bytes() for path in evidence_paths}
        before = set(target.parent.glob(prefix + "*"))
        abandoned = None
        abandoned_bytes = None

        for linked in (False, True):
            with self.subTest(publisher_linked=linked):
                def exit_at_link(*args, **kwargs):
                    if linked:
                        original_link(*args, **kwargs)
                    os._exit(96 if linked else 95)

                pid = os.fork()
                if pid == 0:
                    try:
                        with patch.object(receipts.os, "link", side_effect=exit_at_link):
                            publish()
                    finally:
                        os._exit(97)

                _, status = os.waitpid(pid, 0)
                self.assertEqual(os.waitstatus_to_exitcode(status), 96 if linked else 95)
                folders = set(target.parent.glob(prefix + "*"))
                new, = folders - before
                stage = new / filename
                self.assertTrue(stage.is_file())
                self.assertEqual(stage.stat().st_nlink, 2 if linked else 1)

                if not linked:
                    self.assertFalse(target.exists())
                    with self.assertRaises(recovery.DecimalRecoveryDenied):
                        inspect()
                    review = inspect(include_stages=True)
                    self.assertEqual(review["receipt"], tip)
                    self.assertTrue(review["publicationMissing"])
                    record, = (entry for entry in review["stages"]
                               if entry["name"] == new.name)
                    self.assertEqual(record["entries"], [filename])
                    self.assertFalse(record["publicationLink"])
                    abandoned = stage
                    abandoned_bytes = stage.read_bytes()
                else:
                    self.assertTrue(stage.samefile(target))
                    review = inspect(include_stages=True)
                    self.assertEqual(review["receipt"], tip)
                    self.assertEqual(review["additionalLinkPresent"], True)
                    self.assertNotIn("publicationMissing", review)
                    confirmed = [entry["name"] for entry in review["stages"]
                                 if entry["publicationLink"]]
                    self.assertEqual(confirmed, [new.name])
                    self.assertEqual(abandoned.read_bytes(), abandoned_bytes)
                    old, = (entry for entry in review["stages"]
                            if entry["name"] == abandoned.parent.name)
                    self.assertFalse(old["publicationLink"])

                    cleanup(stage)
                    self.assertFalse(stage.exists())
                    self.assertTrue(new.is_dir())  # Retire only the verified link.
                    settled = inspect(include_stages=True)
                    self.assertEqual(settled["receipt"], tip)
                    self.assertFalse(settled["additionalLinkPresent"])
                    self.assertFalse(any(s["publicationLink"] for s in settled["stages"]))
                    self.assertEqual(abandoned.read_bytes(), abandoned_bytes)

                for path, content in original_evidence.items():
                    self.assertEqual(path.read_bytes(), content)
                before = folders

    def test_terminal_exit_readback_uses_same_evidence_locations(self):
        retained, evidence, _, _ = self.terminal_recovery_evidence()
        self.assert_shared_evidence_exit_readback(
            self.pin_path, ".decimal-terminal-receipt-", "receipt.db",
            partial(retained.repair_local_terminal, self.pins, self.store, **evidence),
            partial(retained.inspect_local_terminal, self.pins, self.store, **evidence),
            lambda stage: retained.cleanup_local_terminal_stage(
                stage, self.pins, self.store, **evidence),
            evidence["reviewed_receipt"], (retained._store.path, self.store_path))

    def test_checkpoint_exit_readback_uses_same_evidence_locations(self):
        self.prepare_checkpoint()
        tip = self.promote()
        exported = self.checkpoint.export(expected_receipt=tip)
        retained = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {
            "trusted_receipt": tip, "recovery_receipt": retained}
        self.checkpoint_path.unlink()
        self.assert_shared_evidence_exit_readback(
            self.checkpoint_path, ".edgepilot-checkpoint-", "checkpoint.db",
            partial(receipts.DecimalPromotionCheckpoint.recover,
                    self.checkpoint_path, exported,
                    checkpoint_key=self.checkpoint_key, **evidence),
            partial(self.checkpoint.inspect_recovered, exported, **evidence),
            lambda stage: self.checkpoint.cleanup_recovered_stage(
                stage, exported, **evidence),
            tip, (retained._store.path, self.pin_path, self.store_path, self.path))

    def assert_final_unlink_recheck_preserves_replacement(self, target, stage, cleanup):
        stat_path = os.stat
        folder = stage.parent.stat()
        held = stage.with_suffix(".held")

        def substitute_after_first_stat(path, *args, **kwargs):
            observed = stat_path(path, *args, **kwargs)
            fd = kwargs.get("dir_fd")
            if path == stage.name and fd is not None and os.path.samestat(os.fstat(fd), folder):
                if not held.exists():
                    stage.rename(held)
                    stage.write_bytes(b"preserve replacement")
            return observed

        with (patch.object(receipts.os, "stat", substitute_after_first_stat),
              patch.object(receipts.os, "unlink", side_effect=AssertionError("Unexpected unlink")),
              self.assertRaises(recovery.DecimalRecoveryDenied)):
            cleanup()
        self.assertTrue(held.samefile(target))
        self.assertEqual(stage.read_bytes(), b"preserve replacement")

    def test_terminal_cleanup_refuses_substitution_after_stage_stat(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        self.assert_final_unlink_recheck_preserves_replacement(
            self.pin_path, stage, partial(retained.cleanup_local_terminal_stage, stage,
                                          self.pins, self.store, **evidence))

    def test_checkpoint_cleanup_refuses_substitution_after_stage_stat(self):
        stage, exported, tip = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(tip)
        self.assert_final_unlink_recheck_preserves_replacement(
            self.checkpoint_path, stage,
            partial(self.checkpoint.cleanup_recovered_stage, stage, exported, trusted_receipt=tip,
                    recovery_receipt=independent, **self.recovery_evidence()))


    def assert_directory_swap_after_last_stage_stat(
            self, target, stage, inspect, cleanup, tip, evidence_paths):
        """A noncooperating same-user writer replaces the stage directory name."""
        folder = stage.parent
        selected = folder.stat()
        renamed = folder.with_name(folder.name + ".moved")
        target_bytes = target.read_bytes()
        independent = {path: path.read_bytes() for path in evidence_paths}
        original_stat = os.stat
        observations = []

        def swap_directory_after_final_observation(path, *args, **kwargs):
            info = original_stat(path, *args, **kwargs)
            fd = kwargs.get("dir_fd")
            if (path == stage.name and fd is not None
                    and os.path.samestat(os.fstat(fd), selected)):
                observations.append(info)
                if len(observations) == 2:
                    folder.rename(renamed)
                    folder.mkdir(mode=0o700)
                    stage.write_bytes(b"unreviewed replacement: preserve")
            return info

        with (patch.object(receipts.os, "stat", swap_directory_after_final_observation),
              patch.object(receipts.os, "unlink",
                           side_effect=AssertionError("Unexpected stage unlink")),
              self.assertRaises(recovery.DecimalRecoveryDenied)):
            cleanup()

        self.assertEqual(len(observations), 2)
        moved_link = renamed / stage.name
        self.assertTrue(moved_link.samefile(target))
        self.assertEqual(stage.read_bytes(), b"unreviewed replacement: preserve")
        self.assertEqual(target.read_bytes(), target_bytes)
        self.assertEqual(target.stat().st_nlink, 2)
        for path, content in independent.items():
            self.assertEqual(path.read_bytes(), content)

        # A remembered selection must not be silently applied to a new name.
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            cleanup()
        self.assertTrue(moved_link.samefile(target))
        self.assertEqual(stage.read_bytes(), b"unreviewed replacement: preserve")

        review = inspect(include_stages=True)
        self.assertEqual(review["receipt"], tip)
        self.assertTrue(review["additionalLinkPresent"])
        records = {entry["name"]: entry for entry in review["stages"]}
        self.assertTrue(records[renamed.name]["publicationLink"])
        self.assertFalse(records[folder.name]["publicationLink"])
        self.assertEqual(records[folder.name]["entries"], [stage.name])
        self.assertEqual(target.read_bytes(), target_bytes)

    def test_terminal_directory_swap_after_final_stage_stat_is_refused(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        self.assert_directory_swap_after_last_stage_stat(
            self.pin_path, stage,
            partial(retained.inspect_local_terminal, self.pins, self.store, **evidence),
            partial(retained.cleanup_local_terminal_stage, stage,
                    self.pins, self.store, **evidence),
            evidence["reviewed_receipt"], (retained._store.path, self.store_path))

    def test_checkpoint_directory_swap_after_final_stage_stat_is_refused(self):
        stage, exported, tip = self.reviewed_staging_link()
        retained = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": retained}
        self.assert_directory_swap_after_last_stage_stat(
            self.checkpoint_path, stage,
            partial(self.checkpoint.inspect_recovered, exported,
                    trusted_receipt=tip, **evidence),
            partial(self.checkpoint.cleanup_recovered_stage, stage, exported,
                    trusted_receipt=tip, **evidence),
            tip, (retained._store.path, self.pin_path, self.store_path, self.path))


    def assert_unlink_boundary_is_non_atomic(
            self, target, stage, inspect, cleanup, tip, evidence_paths, *, swap):
        """Prove late noncooperating changes may mutate names before refusal."""
        self.assertIn(swap, ("stage-file", "directory"))
        original_unlink = os.unlink
        folder = stage.parent
        saved_link = stage.with_name(stage.name + ".late-moved")
        moved_folder = folder.with_name(folder.name + ".late-moved")
        unreviewed = b"unreviewed late replacement"
        published = target.read_bytes()
        original_evidence = {path: path.read_bytes() for path in evidence_paths}

        initial = inspect(include_stages=True)
        self.assertEqual(initial["receipt"], tip)
        self.assertTrue(initial["additionalLinkPresent"])
        self.assertTrue(next(entry for entry in initial["stages"]
                             if entry["name"] == folder.name)["publicationLink"])
        intercepted = []

        def replace_after_last_check(name, *args, **kwargs):
            if name != stage.name or kwargs.get("dir_fd") is None:
                return original_unlink(name, *args, **kwargs)
            self.assertEqual(intercepted, [])
            intercepted.append(swap)
            if swap == "stage-file":
                stage.rename(saved_link)
                stage.write_bytes(unreviewed)
            else:
                folder.rename(moved_folder)
                folder.mkdir(mode=0o700)
                stage.write_bytes(unreviewed)
            # The held dirfd still acts on the originally opened folder.
            return original_unlink(name, *args, **kwargs)

        with (patch.object(receipts.os, "unlink", replace_after_last_check),
              self.assertRaises(recovery.DecimalRecoveryDenied)):
            cleanup()

        self.assertEqual(intercepted, [swap])
        self.assertEqual(target.read_bytes(), published)
        for path, content in original_evidence.items():
            self.assertEqual(path.read_bytes(), content)

        if swap == "stage-file":
            # The unreviewed replacement was removed before the later
            # link-count check refused cleanup: not a safe retry state.
            self.assertFalse(stage.exists())
            self.assertTrue(saved_link.samefile(target))
            self.assertEqual(target.stat().st_nlink, 2)
        else:
            # The verified link was removed from the moved directory even
            # though the checked directory name now points at a replacement.
            self.assertFalse((moved_folder / stage.name).exists())
            self.assertEqual(stage.read_bytes(), unreviewed)
            self.assertEqual(target.stat().st_nlink, 1)

        review = inspect(include_stages=True)
        self.assertEqual(review["receipt"], tip)
        self.assertEqual(review["additionalLinkPresent"], swap == "stage-file")
        entries = {record["name"]: record for record in review["stages"]}
        self.assertFalse(entries[folder.name]["publicationLink"])
        if swap == "stage-file":
            self.assertEqual(entries[folder.name]["entries"], [saved_link.name])
        else:
            self.assertEqual(entries[folder.name]["entries"], [stage.name])
            self.assertFalse(entries[moved_folder.name]["publicationLink"])
            self.assertEqual(entries[moved_folder.name]["entries"], [])
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            cleanup()
        self.assertEqual(target.read_bytes(), published)

        # A non-destructive inventory is the supported choice while another
        # same-UID writer can change names; it does not authenticate loose bytes.
        self.assertEqual(inspect(include_stages=True), review)

    def test_terminal_unlink_boundary_late_file_swap_is_ambiguous(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        self.assert_unlink_boundary_is_non_atomic(
            self.pin_path, stage,
            partial(retained.inspect_local_terminal, self.pins, self.store, **evidence),
            partial(retained.cleanup_local_terminal_stage, stage,
                    self.pins, self.store, **evidence),
            evidence["reviewed_receipt"], (retained._store.path, self.store_path),
            swap="stage-file")

    def test_terminal_unlink_boundary_late_directory_swap_is_ambiguous(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        self.assert_unlink_boundary_is_non_atomic(
            self.pin_path, stage,
            partial(retained.inspect_local_terminal, self.pins, self.store, **evidence),
            partial(retained.cleanup_local_terminal_stage, stage,
                    self.pins, self.store, **evidence),
            evidence["reviewed_receipt"], (retained._store.path, self.store_path),
            swap="directory")

    def test_checkpoint_unlink_boundary_late_file_swap_is_ambiguous(self):
        stage, exported, tip = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.assert_unlink_boundary_is_non_atomic(
            self.checkpoint_path, stage,
            partial(self.checkpoint.inspect_recovered, exported,
                    trusted_receipt=tip, **evidence),
            partial(self.checkpoint.cleanup_recovered_stage, stage, exported,
                    trusted_receipt=tip, **evidence),
            tip, (independent._store.path, self.pin_path, self.store_path, self.path),
            swap="stage-file")

    def test_checkpoint_unlink_boundary_late_directory_swap_is_ambiguous(self):
        stage, exported, tip = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.assert_unlink_boundary_is_non_atomic(
            self.checkpoint_path, stage,
            partial(self.checkpoint.inspect_recovered, exported,
                    trusted_receipt=tip, **evidence),
            partial(self.checkpoint.cleanup_recovered_stage, stage, exported,
                    trusted_receipt=tip, **evidence),
            tip, (independent._store.path, self.pin_path, self.store_path, self.path),
            swap="directory")


    def assert_operator_directory_parking_prototype(
            self, target, stage, inspect, tip, independent_paths, *, case):
        """Offline-only directory parking, never invoked by live recovery."""
        self.assertIn(case, ("roundtrip", "source-swap", "occupied-reservation"))
        original = stage.parent
        saved_bytes = target.read_bytes()
        verified = original.stat()
        evidence = {path: path.read_bytes() for path in independent_paths}
        marker = original / "operator-note"
        marker.write_bytes(b"preserve-stage-notes")

        initial = inspect(include_stages=True)
        self.assertEqual(initial["receipt"], tip)
        self.assertTrue(initial["additionalLinkPresent"])
        self.assertTrue(next(row for row in initial["stages"]
                             if row["name"] == original.name)["publicationLink"])

        reservation = tempfile.TemporaryDirectory(
            prefix=".operator-holding-prototype-", dir=original.parent)
        self.addCleanup(reservation.cleanup)
        parked = Path(reservation.name) / "retained-stage"
        displaced = original.with_name(original.name + ".displaced")
        ordinary_rename = os.rename
        interventions = []

        def park_for_operator_review():
            # This is a test-local prototype, not a production API.
            observed = original.lstat()
            if os.path.lexists(parked):
                recovery._deny()
            try:
                os.rename(original, parked)
            except OSError:
                recovery._deny()
            if not os.path.samestat(observed, parked.lstat()):
                recovery._deny()
            return parked

        def interfere_at_rename(source, destination, *args, **kwargs):
            if (Path(source) == original and Path(destination) == parked
                    and not interventions):
                interventions.append(case)
                if case == "source-swap":
                    ordinary_rename(original, displaced)
                    original.mkdir(mode=0o700)
                    (original / stage.name).write_bytes(b"unreviewed replacement")
                elif case == "occupied-reservation":
                    parked.mkdir(mode=0o700)
                    (parked / "collision-note").write_bytes(b"do not overwrite")
            return ordinary_rename(source, destination, *args, **kwargs)

        if case == "roundtrip":
            self.assertEqual(park_for_operator_review(), parked)
            self.assertFalse(original.exists())
            self.assertTrue((parked / stage.name).samefile(target))
            self.assertEqual((parked / marker.name).read_bytes(), b"preserve-stage-notes")
            intermediate = inspect(include_stages=True)
            self.assertEqual(intermediate["receipt"], tip)
            self.assertTrue(intermediate["additionalLinkPresent"])
            self.assertFalse(any(row["publicationLink"] for row in intermediate["stages"]))
            # Reversal is demonstrated only in an uncontended synthetic fixture.
            os.rename(parked, original)
            self.assertTrue(stage.samefile(target))
            self.assertEqual(marker.read_bytes(), b"preserve-stage-notes")
            self.assertEqual(inspect(include_stages=True), initial)
        else:
            with (patch.object(os, "rename", interfere_at_rename),
                  self.assertRaises(recovery.DecimalRecoveryDenied)):
                park_for_operator_review()
            self.assertEqual(interventions, [case])
            if case == "source-swap":
                # The swapped-in candidate was moved, not deleted. A mismatch
                # must never trigger an automatic move back over another name.
                self.assertFalse(original.exists())
                self.assertTrue((displaced / stage.name).samefile(target))
                self.assertEqual((displaced / marker.name).read_bytes(),
                                 b"preserve-stage-notes")
                self.assertEqual((parked / stage.name).read_bytes(),
                                 b"unreviewed replacement")
                current = inspect(include_stages=True)
                self.assertTrue(next(row for row in current["stages"]
                                     if row["name"] == displaced.name)["publicationLink"])
                self.assertTrue(current["additionalLinkPresent"])
            else:
                # A nonempty reservation prevents a same-directory rename
                # from overwriting preexisting evidence.
                self.assertTrue(stage.samefile(target))
                self.assertEqual((parked / "collision-note").read_bytes(),
                                 b"do not overwrite")
                self.assertEqual(inspect(include_stages=True), initial)

        self.assertTrue(os.path.samestat(verified, (
            (displaced if case == "source-swap" else original).stat()
            if case != "roundtrip" else original.stat())))
        self.assertEqual(target.read_bytes(), saved_bytes)
        self.assertEqual(target.stat().st_nlink, 2)
        for path, content in evidence.items():
            self.assertEqual(path.read_bytes(), content)

    def test_terminal_operator_parking_roundtrip_prototype(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        self.assert_operator_directory_parking_prototype(
            self.pin_path, stage,
            partial(retained.inspect_local_terminal, self.pins, self.store, **evidence),
            evidence["reviewed_receipt"], (retained._store.path, self.store_path),
            case="roundtrip")

    def test_checkpoint_operator_parking_roundtrip_prototype(self):
        stage, exported, tip = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.assert_operator_directory_parking_prototype(
            self.checkpoint_path, stage,
            partial(self.checkpoint.inspect_recovered, exported,
                    trusted_receipt=tip, **evidence),
            tip, (independent._store.path, self.pin_path, self.store_path, self.path),
            case="roundtrip")

    def test_terminal_operator_parking_detects_replaced_source(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        self.assert_operator_directory_parking_prototype(
            self.pin_path, stage,
            partial(retained.inspect_local_terminal, self.pins, self.store, **evidence),
            evidence["reviewed_receipt"], (retained._store.path, self.store_path),
            case="source-swap")

    def test_checkpoint_operator_parking_detects_replaced_source(self):
        stage, exported, tip = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.assert_operator_directory_parking_prototype(
            self.checkpoint_path, stage,
            partial(self.checkpoint.inspect_recovered, exported,
                    trusted_receipt=tip, **evidence),
            tip, (independent._store.path, self.pin_path, self.store_path, self.path),
            case="source-swap")

    def test_terminal_operator_parking_preserves_occupied_reservation(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        self.assert_operator_directory_parking_prototype(
            self.pin_path, stage,
            partial(retained.inspect_local_terminal, self.pins, self.store, **evidence),
            evidence["reviewed_receipt"], (retained._store.path, self.store_path),
            case="occupied-reservation")

    def test_checkpoint_operator_parking_preserves_occupied_reservation(self):
        stage, exported, tip = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.assert_operator_directory_parking_prototype(
            self.checkpoint_path, stage,
            partial(self.checkpoint.inspect_recovered, exported,
                    trusted_receipt=tip, **evidence),
            tip, (independent._store.path, self.pin_path, self.store_path, self.path),
            case="occupied-reservation")


    def assert_rename_noreplace_operator_prototype(
            self, target, stage, inspect, tip, evidence_paths, *, case):
        """Linux-only test of descriptor-based no-overwrite directory moves."""
        self.assertIn(case, ("roundtrip", "empty-directory", "symlink",
                             "source-swap", "restore-collision"))
        libc = ctypes.CDLL(None, use_errno=True)
        if not hasattr(libc, "renameat2"):
            self.skipTest("Linux libc renameat2 unavailable")
        renameat2 = libc.renameat2
        renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                              ctypes.c_char_p, ctypes.c_uint)
        renameat2.restype = ctypes.c_int
        RENAME_NOREPLACE = 1
        folder = stage.parent
        original = folder.stat()
        destination = tempfile.TemporaryDirectory(
            prefix=".operator-noreplace-prototype-", dir=folder.parent)
        self.addCleanup(destination.cleanup)
        holding = Path(destination.name)
        parked = holding / "retained-stage"
        displaced = folder.with_name(folder.name + ".moved-evidence")
        note = folder / "operator-note"
        note.write_bytes(b"keep operator note")
        source_bytes = target.read_bytes()
        independent = {path: path.read_bytes() for path in evidence_paths}
        initial = inspect(include_stages=True)
        self.assertEqual(initial["receipt"], tip)
        self.assertTrue(initial["additionalLinkPresent"])
        self.assertTrue(next(s for s in initial["stages"]
                             if s["name"] == folder.name)["publicationLink"])
        failures = []
        intervention = []

        def noreplace(source_parent, source_name, dest_parent, dest_name,
                      *, before=None):
            source_fd = os.open(source_parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                dest_fd = os.open(dest_parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    if before:
                        before()
                    result = renameat2(source_fd, os.fsencode(source_name),
                                       dest_fd, os.fsencode(dest_name), RENAME_NOREPLACE)
                    if result != 0:
                        number = ctypes.get_errno()
                        raise OSError(number, os.strerror(number))
                finally:
                    os.close(dest_fd)
            finally:
                os.close(source_fd)

        def compete():
            intervention.append(case)
            if case == "empty-directory":
                parked.mkdir(mode=0o700)
            elif case == "symlink":
                parked.symlink_to("unreviewed-link-target")
            elif case == "source-swap":
                folder.rename(displaced)
                folder.mkdir(mode=0o700)
                stage.write_bytes(b"unreviewed source replacement")

        def park():
            observed = folder.lstat()
            try:
                noreplace(folder.parent, folder.name, holding, parked.name, before=compete)
            except OSError as error:
                failures.append(error.errno)
                recovery._deny()
            if not os.path.samestat(observed, parked.lstat()):
                recovery._deny()

        if case in ("empty-directory", "symlink"):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                park()
            self.assertEqual(failures, [errno.EEXIST])
            self.assertEqual(intervention, [case])
            self.assertTrue(stage.samefile(target))
            if case == "symlink":
                self.assertTrue(parked.is_symlink())
                self.assertEqual(os.readlink(parked), "unreviewed-link-target")
            else:
                self.assertTrue(parked.is_dir())
                self.assertEqual(list(parked.iterdir()), [])
            self.assertEqual(inspect(include_stages=True), initial)
        elif case == "source-swap":
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                park()
            self.assertEqual(intervention, [case])
            self.assertEqual(failures, [])
            self.assertFalse(folder.exists())
            self.assertTrue((displaced / stage.name).samefile(target))
            self.assertEqual((displaced / note.name).read_bytes(), b"keep operator note")
            self.assertEqual((parked / stage.name).read_bytes(), b"unreviewed source replacement")
            inspected = inspect(include_stages=True)
            self.assertTrue(inspected["additionalLinkPresent"])
            self.assertTrue(next(s for s in inspected["stages"]
                                 if s["name"] == displaced.name)["publicationLink"])
            # No automatic retry/rollback: the identity-mismatched candidate
            # must remain held without replacing an operator-selected pathname.
        else:
            park()
            self.assertEqual(intervention, [case])
            self.assertTrue((parked / stage.name).samefile(target))
            self.assertEqual((parked / note.name).read_bytes(), b"keep operator note")
            mid = inspect(include_stages=True)
            self.assertEqual(mid["receipt"], tip)
            self.assertTrue(mid["additionalLinkPresent"])
            self.assertFalse(any(s["publicationLink"] for s in mid["stages"]))
            if case == "roundtrip":
                noreplace(holding, parked.name, folder.parent, folder.name)
                self.assertTrue(stage.samefile(target))
                self.assertEqual(note.read_bytes(), b"keep operator note")
                self.assertEqual(inspect(include_stages=True), initial)
            else:
                folder.mkdir(mode=0o700)
                stage.write_bytes(b"conflicting rollback destination")
                with self.assertRaises(OSError) as refused:
                    noreplace(holding, parked.name, folder.parent, folder.name)
                self.assertEqual(refused.exception.errno, errno.EEXIST)
                self.assertTrue((parked / stage.name).samefile(target))
                self.assertEqual(stage.read_bytes(), b"conflicting rollback destination")
                observed = inspect(include_stages=True)
                self.assertTrue(observed["additionalLinkPresent"])
                self.assertFalse(next(s for s in observed["stages"]
                                      if s["name"] == folder.name)["publicationLink"])

        current = displaced if case == "source-swap" else (parked if case == "restore-collision" else folder)
        self.assertTrue(os.path.samestat(current.stat(), original))
        self.assertEqual(target.read_bytes(), source_bytes)
        self.assertEqual(target.stat().st_nlink, 2)
        for path, content in independent.items():
            self.assertEqual(path.read_bytes(), content)

    def test_terminal_operator_noreplace_roundtrip(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        self.assert_rename_noreplace_operator_prototype(
            self.pin_path, stage,
            partial(retained.inspect_local_terminal, self.pins, self.store, **evidence),
            evidence["reviewed_receipt"], (retained._store.path, self.store_path),
            case="roundtrip")

    def test_terminal_operator_noreplace_empty_directory(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        self.assert_rename_noreplace_operator_prototype(
            self.pin_path, stage,
            partial(retained.inspect_local_terminal, self.pins, self.store, **evidence),
            evidence["reviewed_receipt"], (retained._store.path, self.store_path),
            case="empty-directory")

    def test_terminal_operator_noreplace_symlink(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        self.assert_rename_noreplace_operator_prototype(
            self.pin_path, stage,
            partial(retained.inspect_local_terminal, self.pins, self.store, **evidence),
            evidence["reviewed_receipt"], (retained._store.path, self.store_path),
            case="symlink")

    def test_terminal_operator_noreplace_source_swap(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        self.assert_rename_noreplace_operator_prototype(
            self.pin_path, stage,
            partial(retained.inspect_local_terminal, self.pins, self.store, **evidence),
            evidence["reviewed_receipt"], (retained._store.path, self.store_path),
            case="source-swap")

    def test_terminal_operator_noreplace_restore_collision(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        self.assert_rename_noreplace_operator_prototype(
            self.pin_path, stage,
            partial(retained.inspect_local_terminal, self.pins, self.store, **evidence),
            evidence["reviewed_receipt"], (retained._store.path, self.store_path),
            case="restore-collision")

    def test_checkpoint_operator_noreplace_roundtrip(self):
        stage, exported, tip = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.assert_rename_noreplace_operator_prototype(
            self.checkpoint_path, stage,
            partial(self.checkpoint.inspect_recovered, exported,
                    trusted_receipt=tip, **evidence),
            tip, (independent._store.path, self.pin_path, self.store_path, self.path),
            case="roundtrip")

    def test_checkpoint_operator_noreplace_empty_directory(self):
        stage, exported, tip = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.assert_rename_noreplace_operator_prototype(
            self.checkpoint_path, stage,
            partial(self.checkpoint.inspect_recovered, exported,
                    trusted_receipt=tip, **evidence),
            tip, (independent._store.path, self.pin_path, self.store_path, self.path),
            case="empty-directory")

    def test_checkpoint_operator_noreplace_symlink(self):
        stage, exported, tip = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.assert_rename_noreplace_operator_prototype(
            self.checkpoint_path, stage,
            partial(self.checkpoint.inspect_recovered, exported,
                    trusted_receipt=tip, **evidence),
            tip, (independent._store.path, self.pin_path, self.store_path, self.path),
            case="symlink")

    def test_checkpoint_operator_noreplace_source_swap(self):
        stage, exported, tip = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.assert_rename_noreplace_operator_prototype(
            self.checkpoint_path, stage,
            partial(self.checkpoint.inspect_recovered, exported,
                    trusted_receipt=tip, **evidence),
            tip, (independent._store.path, self.pin_path, self.store_path, self.path),
            case="source-swap")

    def test_checkpoint_operator_noreplace_restore_collision(self):
        stage, exported, tip = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.assert_rename_noreplace_operator_prototype(
            self.checkpoint_path, stage,
            partial(self.checkpoint.inspect_recovered, exported,
                    trusted_receipt=tip, **evidence),
            tip, (independent._store.path, self.pin_path, self.store_path, self.path),
            case="restore-collision")


    def assert_operator_parked_manifest_review(
            self, target, stage, inspect, tip, evidence_paths, *, kind, case):
        """Test-local signed location manifest for a parked synthetic stage.

        A signed record is not atomic with rename and is not a safe production
        operation against uncontrolled same-UID filesystem writers.
        """
        import hashlib
        import hmac
        import json
        import stat

        self.assertIn(kind, ("terminal", "checkpoint"))
        exit_points = {"before-record": 90, "partial-record": 91,
                       "prepared": 92, "moved": 93, "conflict": 93,
                       "interrupted-evidence-change": 93,
                       "both-source": 92, "both-parked": 93, "neither": 93,
                       "stale-and-current": 93, "stale-only": 93, "missing-pin": 93}
        pin_update_cases = ("pin-update-during-open", "pin-update-before-return",
                            "pin-exit-before-replace", "pin-exit-after-replace",
                            "pin-same-digest-replacement")
        pinned_cases = ("stale-and-current", "stale-only", "missing-pin", *pin_update_cases)
        self.assertIn(case, (*exit_points, *pin_update_cases,
                             "clean", "holding-swap", "parked-name-swap",
                             "manifest-tamper", "evidence-tamper"))
        libc = ctypes.CDLL(None, use_errno=True)
        if not hasattr(libc, "renameat2"):
            self.skipTest("Linux libc renameat2 unavailable")
        renameat2 = libc.renameat2
        renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                              ctypes.c_char_p, ctypes.c_uint)
        renameat2.restype = ctypes.c_int

        folder = stage.parent
        original = folder.stat()
        target_stat = target.stat()
        original_bytes = target.read_bytes()
        independent = {path: path.read_bytes() for path in evidence_paths}
        before = inspect(include_stages=True)
        self.assertEqual(before["receipt"], tip)
        self.assertTrue(before["additionalLinkPresent"])
        self.assertTrue(next(item for item in before["stages"]
                             if item["name"] == folder.name)["publicationLink"])
        root_dir = tempfile.TemporaryDirectory(
            prefix=".operator-parked-review-v02151-", dir=folder.parent)
        self.addCleanup(root_dir.cleanup)
        root = Path(root_dir.name)
        holding = root / "holding"
        records = root / "independent-records"
        holding.mkdir(mode=0o700)
        records.mkdir(mode=0o700)
        parked = holding / "retained-stage"
        key = os.urandom(32)  # In-memory synthetic operator authority only.

        # Both parent directories are descriptor-pinned for the no-overwrite
        # operation. The source basename itself is still raceable by same UID.
        def move_no_replace(source, destination):
            source_fd = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                holding_fd = os.open(destination.parent,
                                     os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    result = renameat2(source_fd, os.fsencode(source.name),
                                       holding_fd, os.fsencode(destination.name), 1)
                    if result != 0:
                        number = ctypes.get_errno()
                        raise OSError(number, os.strerror(number))
                finally:
                    os.close(holding_fd)
            finally:
                os.close(source_fd)

        def sha(data):
            return hashlib.sha256(data).hexdigest()

        # A source-attributed location record is retained outside the
        # holding directory and the ordinary stage-prefix inventory.
        signed = {
            "format": "test-only-v02151",
            "source_kind": kind,
            "source_stage": folder.name,
            "stage_file": stage.name,
            "stage_dev": original.st_dev,
            "stage_ino": original.st_ino,
            "target": target.name,
            "target_dev": target_stat.st_dev,
            "target_ino": target_stat.st_ino,
            "target_sha256": sha(original_bytes),
            "holding_dev": holding.stat().st_dev,
            "holding_ino": holding.stat().st_ino,
            "parked_name": parked.name,
            "receipt_sha256": sha(repr(tip).encode("utf-8")),
            "evidence": [
                {"name": path.name, "sha256": sha(data)}
                for path, data in independent.items()
            ],
        }

        def encode(record):
            return json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")

        def seal(data):
            return hmac.new(key, data, hashlib.sha256).hexdigest()

        raw = encode(signed)
        manifest = records / "location.json"
        signature = records / "location.mac"
        conflicting_manifest = records / "conflicting-location.json"
        conflicting_signature = records / "conflicting-location.mac"
        prior_manifest = records / "previous-location.json"
        prior_signature = records / "previous-location.mac"
        pin = root / "independently-retained-location.sha256"
        staged_pin = root / "pending-location.sha256"
        original_pin = root / "original-location.sha256"
        competing_pin = root / "competing-location.sha256"

        if case in pinned_cases:
            # Complete an earlier operation with the same stage, target and
            # signing authority, then explicitly return the stage for a new one.
            earlier_holding = root / "previous-holding"
            earlier_holding.mkdir(mode=0o700)
            earlier_parked = earlier_holding / parked.name
            earlier_stat = earlier_holding.stat()
            earlier_record = signed | {
                "holding_dev": earlier_stat.st_dev,
                "holding_ino": earlier_stat.st_ino,
            }
            earlier_raw = encode(earlier_record)
            prior_manifest.write_bytes(earlier_raw)
            prior_signature.write_text(seal(earlier_raw), encoding="ascii")
            move_no_replace(folder, earlier_parked)
            self.assertTrue(os.path.samestat(original, earlier_parked.stat()))
            self.assertTrue((earlier_parked / stage.name).samefile(target))
            move_no_replace(earlier_parked, folder)
            # Retain the exact current record digest outside the directory
            # where the publisher leaves its candidate files.
            if case != "missing-pin":
                pin.write_text(sha(raw), encoding="ascii")

        def write_record():
            manifest.write_bytes(raw)
            if case == "partial-record":
                os._exit(91)
            signature.write_text(seal(raw), encoding="ascii")

        if case in exit_points:
            pid = os.fork()
            if pid == 0:
                try:
                    if case == "before-record":
                        os._exit(90)
                    write_record()
                    if case in ("prepared", "both-source"):
                        os._exit(92)
                    move_no_replace(folder, parked)
                    os._exit(93)
                except BaseException:
                    os._exit(99)
            _, status = os.waitpid(pid, 0)
            self.assertEqual(os.waitstatus_to_exitcode(status), exit_points[case])
        else:
            move_no_replace(folder, parked)
            write_record()

        def read_signed_bytes(record_path, seal_path, *, after_open=None):
            try:
                with record_path.open("rb") as record:
                    if after_open is not None:
                        after_open()
                    candidate = record.read()
                observed_seal = seal_path.read_text(encoding="ascii")
            except (OSError, UnicodeError):
                recovery._deny()
            if not hmac.compare_digest(seal(candidate), observed_seal):
                recovery._deny()
            return candidate

        def decode_record(candidate):
            try:
                return json.loads(candidate)
            except (ValueError, UnicodeError):
                recovery._deny()

        def read_signed_record(record_path, seal_path):
            return decode_record(read_signed_bytes(record_path, seal_path))

        def observe_pin():
            if os.path.lexists(staged_pin):
                recovery._deny()
            try:
                fd = os.open(pin, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, "rb") as stream:
                    identity = os.fstat(stream.fileno())
                    if not stat.S_ISREG(identity.st_mode):
                        recovery._deny()
                    digest = stream.read(65)
                named_identity = pin.lstat()
            except OSError:
                recovery._deny()
            if (not os.path.samestat(identity, named_identity)
                    or len(digest) != 64 or os.path.lexists(staged_pin)):
                recovery._deny()
            return (identity.st_dev, identity.st_ino, digest)

        def read_pinned_record(observed_pin, *, after_open=None):
            # Consult the earlier valid record first to exercise stale replay.
            candidates = [(prior_manifest, prior_signature)]
            if os.path.lexists(manifest) or os.path.lexists(signature):
                candidates.append((manifest, signature))
            matches = []
            for record_path, seal_path in candidates:
                on_open = after_open if record_path == manifest else None
                candidate = read_signed_bytes(record_path, seal_path, after_open=on_open)
                if hmac.compare_digest(sha(candidate).encode("ascii"), observed_pin[2]):
                    matches.append(candidate)
            if len(matches) != 1:
                recovery._deny()
            return decode_record(matches[0])

        def inventory_locations(record):
            def observe(path):
                try:
                    identity = path.lstat()
                except FileNotFoundError:
                    return "absent"
                if (identity.st_dev, identity.st_ino) == (record["stage_dev"],
                                                         record["stage_ino"]):
                    return "recorded-stage"
                return "other-entry"

            return (observe(folder.parent / record["source_stage"]),
                    observe(holding / record["parked_name"]))

        def independently_review(*, after_open=None, before_return=None):
            # Require all supplied local evidence to agree before interpreting
            # either location. A valid seal cannot break a tie between records.
            if case in pinned_cases:
                observed_pin = observe_pin()
                record = read_pinned_record(observed_pin, after_open=after_open)
                if observe_pin() != observed_pin:
                    recovery._deny()
            else:
                record = read_signed_record(manifest, signature)
            if os.path.lexists(conflicting_manifest) or os.path.lexists(conflicting_signature):
                if read_signed_record(conflicting_manifest, conflicting_signature) != record:
                    recovery._deny()
            if record != signed or record["source_kind"] != kind:
                recovery._deny()
            if record["receipt_sha256"] != sha(repr(tip).encode("utf-8")):
                recovery._deny()
            if record["evidence"] != [
                    {"name": path.name, "sha256": sha(path.read_bytes())}
                    for path in evidence_paths]:
                recovery._deny()
            locations = inventory_locations(record)
            if locations not in (("recorded-stage", "absent"), ("absent", "recorded-stage")):
                recovery._deny()
            original_present = locations[0] == "recorded-stage"
            try:
                hold_fd = os.open(holding, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            except OSError:
                recovery._deny()
            try:
                held_stat = os.fstat(hold_fd)
                if (held_stat.st_dev, held_stat.st_ino) != (
                        record["holding_dev"], record["holding_ino"]):
                    recovery._deny()
                try:
                    if original_present:
                        stage_fd = os.open(
                            folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                    else:
                        stage_fd = os.open(
                            record["parked_name"],
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=hold_fd)
                except OSError:
                    recovery._deny()
                try:
                    directory = os.fstat(stage_fd)
                    if (directory.st_dev, directory.st_ino) != (
                            record["stage_dev"], record["stage_ino"]):
                        recovery._deny()
                    try:
                        link_fd = os.open(
                            record["stage_file"], os.O_RDONLY | os.O_NOFOLLOW,
                            dir_fd=stage_fd)
                    except OSError:
                        recovery._deny()
                    with os.fdopen(link_fd, "rb") as source:
                        link = os.fstat(source.fileno())
                        if (link.st_dev, link.st_ino) != (
                                record["target_dev"], record["target_ino"]):
                            recovery._deny()
                        if sha(source.read()) != record["target_sha256"]:
                            recovery._deny()
                finally:
                    os.close(stage_fd)
            finally:
                os.close(hold_fd)
            target_now = target.stat()
            if (target_now.st_dev, target_now.st_ino) != (
                    record["target_dev"], record["target_ino"]):
                recovery._deny()
            if sha(target.read_bytes()) != record["target_sha256"]:
                recovery._deny()
            checked = inspect(include_stages=True)
            visible_links = [item["name"] for item in checked["stages"]
                             if item["publicationLink"]]
            expected_links = [record["source_stage"]] if original_present else []
            if (checked["receipt"] != tip or
                    not checked["additionalLinkPresent"] or
                    visible_links != expected_links):
                recovery._deny()
            if before_return is not None:
                before_return()
            if case in pinned_cases and observe_pin() != observed_pin:
                recovery._deny()
            return "stage-at-source" if original_present else "stage-at-parked-location"

        displaced = None
        decoy = None
        observed_locations = None
        if case in ("both-source", "both-parked"):
            decoy = parked if case == "both-source" else folder
            decoy.mkdir(mode=0o700)
            (decoy / stage.name).write_bytes(b"preserve unreviewed candidate")
            observed_locations = (("recorded-stage", "other-entry") if case == "both-source"
                                  else ("other-entry", "recorded-stage"))
        elif case == "neither":
            displaced = root / "unattributed-stage"
            move_no_replace(parked, displaced)
            observed_locations = ("absent", "absent")
        elif case == "stale-only":
            # The publisher slot can be absent while the older signed bytes
            # remain available. Keep the current record pair intact elsewhere.
            manifest.rename(root / manifest.name)
            signature.rename(root / signature.name)
        elif case == "holding-swap":
            displaced = root / "authentic-holding"
            holding.rename(displaced)
            holding.mkdir(mode=0o700)
            (holding / parked.name).mkdir(mode=0o700)
            (holding / parked.name / stage.name).write_bytes(b"unreviewed holding")
        elif case == "parked-name-swap":
            displaced = holding / "authentic-parked"
            parked.rename(displaced)
            parked.mkdir(mode=0o700)
            (parked / stage.name).write_bytes(b"unreviewed parked name")
        elif case == "manifest-tamper":
            # The manifest is not authorized merely because the replacement
            # contains plausible source and inode fields.
            manifest.write_bytes(raw.replace(b"test-only-v02151",
                                             b"test-only-v02150"))
        elif case in ("evidence-tamper", "interrupted-evidence-change"):
            evidence_paths[0].write_bytes(b"unreviewed evidence replacement")
        elif case == "conflict":
            alternative = encode(signed | {"parked_name": "other-retained-stage"})
            conflicting_manifest.write_bytes(alternative)
            conflicting_signature.write_text(seal(alternative), encoding="ascii")
            self.assertEqual(read_signed_record(manifest, signature), signed)
            self.assertEqual(read_signed_record(conflicting_manifest, conflicting_signature),
                             signed | {"parked_name": "other-retained-stage"})

        retained_before_review = {path.name: path.read_bytes() for path in records.iterdir()}
        review_evidence_paths = [*evidence_paths]
        if case in pinned_cases:
            self.assertEqual(read_signed_record(prior_manifest, prior_signature), earlier_record)
            self.assertNotEqual(sha(earlier_raw), sha(raw))
            if case not in ("missing-pin", *pin_update_cases):
                review_evidence_paths.append(pin)
            if case == "stale-only":
                review_evidence_paths.extend((root / manifest.name, root / signature.name))
        evidence_before_review = {path: path.read_bytes() for path in review_evidence_paths}
        if observed_locations is not None:
            self.assertEqual(inventory_locations(signed), observed_locations)
        if decoy is not None:
            decoy_identity = decoy.lstat()
        if case == "stale-and-current":
            self.assertEqual(read_pinned_record(observe_pin()), signed)
        elif case in ("stale-only", "missing-pin"):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                read_pinned_record(observe_pin())
        if case in pin_update_cases:
            current_digest = sha(raw).encode("ascii")
            competing_digest = (current_digest if case == "pin-same-digest-replacement"
                                else sha(earlier_raw).encode("ascii"))
            os.link(pin, original_pin)
            self.assertEqual(independently_review(), "stage-at-parked-location")

            def write_competing_pin(*, exit_at=None):
                with staged_pin.open("xb") as stream:
                    stream.write(competing_digest)
                os.link(staged_pin, competing_pin)
                if exit_at == "staged":
                    os._exit(94)
                os.replace(staged_pin, pin)
                if exit_at == "replaced":
                    os._exit(95)

            def compete():
                exit_at = {"pin-exit-before-replace": "staged",
                           "pin-exit-after-replace": "replaced"}.get(case)
                if exit_at is None:
                    write_competing_pin()
                    return
                pid = os.fork()
                if pid == 0:
                    try:
                        write_competing_pin(exit_at=exit_at)
                    finally:
                        os._exit(99)
                _, status = os.waitpid(pid, 0)
                self.assertEqual(os.waitstatus_to_exitcode(status),
                                 94 if exit_at == "staged" else 95)

            during_open = case == "pin-update-during-open"
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                independently_review(after_open=compete if during_open else None,
                                     before_return=None if during_open else compete)
            self.assertEqual(original_pin.read_bytes(), current_digest)
            self.assertEqual(competing_pin.read_bytes(), competing_digest)
            self.assertFalse(original_pin.samefile(competing_pin))
            if case == "pin-exit-before-replace":
                self.assertTrue(pin.samefile(original_pin))
                self.assertTrue(staged_pin.samefile(competing_pin))
            else:
                self.assertTrue(pin.samefile(competing_pin))
                self.assertFalse(os.path.lexists(staged_pin))
        elif case in ("clean", "moved", "stale-and-current"):
            self.assertEqual(independently_review(), "stage-at-parked-location")
        elif case == "prepared":
            self.assertEqual(independently_review(), "stage-at-source")
        else:
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                independently_review()

        # A process exit before parking must leave the exact original link
        # discoverable. Review may describe that location, never retry the move.
        before_move = case in ("before-record", "partial-record", "prepared", "both-source")
        authentic = folder if before_move else parked
        if case == "holding-swap":
            authentic = displaced / parked.name
        elif case in ("parked-name-swap", "neither"):
            authentic = displaced
        self.assertEqual(os.path.lexists(folder), before_move or case == "both-parked")
        if before_move:
            self.assertEqual(os.path.lexists(parked), case == "both-source")
        if observed_locations is not None:
            self.assertEqual(inventory_locations(signed), observed_locations)
        if decoy is not None:
            self.assertTrue(os.path.samestat(decoy.lstat(), decoy_identity))
            self.assertEqual((decoy / stage.name).read_bytes(), b"preserve unreviewed candidate")
        self.assertTrue(os.path.samestat(authentic.stat(), original))
        self.assertTrue((authentic / stage.name).samefile(target))
        self.assertEqual(target.read_bytes(), original_bytes)
        self.assertEqual(target.stat().st_nlink, 2)

        expected_records = {manifest.name, signature.name}
        if case == "before-record":
            expected_records.clear()
        elif case == "partial-record":
            expected_records.remove(signature.name)
            self.assertEqual(retained_before_review.get(manifest.name), raw)
        elif case == "conflict":
            expected_records.update((conflicting_manifest.name, conflicting_signature.name))
        if case in pinned_cases:
            expected_records.update((prior_manifest.name, prior_signature.name))
            self.assertEqual(pin.is_file(), case != "missing-pin")
        if case == "stale-only":
            expected_records.difference_update((manifest.name, signature.name))
        self.assertEqual(set(retained_before_review), expected_records)
        self.assertEqual({path.name: path.read_bytes() for path in records.iterdir()},
                         retained_before_review)
        expected_evidence = independent.copy()
        if case in ("evidence-tamper", "interrupted-evidence-change"):
            expected_evidence[evidence_paths[0]] = b"unreviewed evidence replacement"
        self.assertEqual({path: evidence_before_review[path] for path in evidence_paths},
                         expected_evidence)
        self.assertEqual({path: path.read_bytes() for path in review_evidence_paths},
                         evidence_before_review)

    def test_terminal_operator_parked_manifest_clean(self):
        self.assert_terminal_operator_parking_exit("clean")

    def test_terminal_operator_parked_manifest_holding_swap(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        self.assert_operator_parked_manifest_review(
            self.pin_path, stage,
            partial(retained.inspect_local_terminal,
                    self.pins, self.store, **evidence),
            evidence["reviewed_receipt"],
            (retained._store.path, self.store_path),
            kind="terminal", case="holding-swap")

    def test_terminal_operator_parked_manifest_parked_name_swap(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        self.assert_operator_parked_manifest_review(
            self.pin_path, stage,
            partial(retained.inspect_local_terminal,
                    self.pins, self.store, **evidence),
            evidence["reviewed_receipt"],
            (retained._store.path, self.store_path),
            kind="terminal", case="parked-name-swap")

    def test_terminal_operator_parked_manifest_manifest_tamper(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        self.assert_operator_parked_manifest_review(
            self.pin_path, stage,
            partial(retained.inspect_local_terminal,
                    self.pins, self.store, **evidence),
            evidence["reviewed_receipt"],
            (retained._store.path, self.store_path),
            kind="terminal", case="manifest-tamper")

    def test_terminal_operator_parked_manifest_evidence_tamper(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        self.assert_operator_parked_manifest_review(
            self.pin_path, stage,
            partial(retained.inspect_local_terminal,
                    self.pins, self.store, **evidence),
            evidence["reviewed_receipt"],
            (retained._store.path, self.store_path),
            kind="terminal", case="evidence-tamper")

    def test_checkpoint_operator_parked_manifest_clean(self):
        self.assert_checkpoint_operator_parking_exit("clean")

    def test_checkpoint_operator_parked_manifest_holding_swap(self):
        stage, exported, tip = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.assert_operator_parked_manifest_review(
            self.checkpoint_path, stage,
            partial(self.checkpoint.inspect_recovered, exported,
                    trusted_receipt=tip, **evidence),
            tip, (independent._store.path, self.pin_path,
                  self.store_path, self.path),
            kind="checkpoint", case="holding-swap")

    def test_checkpoint_operator_parked_manifest_parked_name_swap(self):
        stage, exported, tip = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.assert_operator_parked_manifest_review(
            self.checkpoint_path, stage,
            partial(self.checkpoint.inspect_recovered, exported,
                    trusted_receipt=tip, **evidence),
            tip, (independent._store.path, self.pin_path,
                  self.store_path, self.path),
            kind="checkpoint", case="parked-name-swap")

    def test_checkpoint_operator_parked_manifest_manifest_tamper(self):
        stage, exported, tip = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.assert_operator_parked_manifest_review(
            self.checkpoint_path, stage,
            partial(self.checkpoint.inspect_recovered, exported,
                    trusted_receipt=tip, **evidence),
            tip, (independent._store.path, self.pin_path,
                  self.store_path, self.path),
            kind="checkpoint", case="manifest-tamper")

    def test_checkpoint_operator_parked_manifest_evidence_tamper(self):
        stage, exported, tip = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.assert_operator_parked_manifest_review(
            self.checkpoint_path, stage,
            partial(self.checkpoint.inspect_recovered, exported,
                    trusted_receipt=tip, **evidence),
            tip, (independent._store.path, self.pin_path,
                  self.store_path, self.path),
            kind="checkpoint", case="evidence-tamper")

    def assert_terminal_operator_parking_exit(self, case):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        self.assert_operator_parked_manifest_review(
            self.pin_path, stage,
            partial(retained.inspect_local_terminal,
                    self.pins, self.store, **evidence),
            evidence["reviewed_receipt"],
            (retained._store.path, self.store_path),
            kind="terminal", case=case)

    def test_terminal_parking_exit_before_record(self):
        self.assert_terminal_operator_parking_exit("before-record")

    def test_terminal_parking_exit_partial_record(self):
        self.assert_terminal_operator_parking_exit("partial-record")

    def test_terminal_parking_exit_prepared(self):
        self.assert_terminal_operator_parking_exit("prepared")

    def test_terminal_parking_exit_moved(self):
        self.assert_terminal_operator_parking_exit("moved")

    def test_terminal_parking_exit_conflict(self):
        self.assert_terminal_operator_parking_exit("conflict")

    def test_terminal_parking_exit_interrupted_evidence_change(self):
        self.assert_terminal_operator_parking_exit("interrupted-evidence-change")

    def assert_checkpoint_operator_parking_exit(self, case):
        stage, exported, tip = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.assert_operator_parked_manifest_review(
            self.checkpoint_path, stage,
            partial(self.checkpoint.inspect_recovered, exported,
                    trusted_receipt=tip, **evidence),
            tip, (independent._store.path, self.pin_path,
                  self.store_path, self.path),
            kind="checkpoint", case=case)

    def test_checkpoint_parking_exit_before_record(self):
        self.assert_checkpoint_operator_parking_exit("before-record")

    def test_checkpoint_parking_exit_partial_record(self):
        self.assert_checkpoint_operator_parking_exit("partial-record")

    def test_checkpoint_parking_exit_prepared(self):
        self.assert_checkpoint_operator_parking_exit("prepared")

    def test_checkpoint_parking_exit_moved(self):
        self.assert_checkpoint_operator_parking_exit("moved")

    def test_checkpoint_parking_exit_conflict(self):
        self.assert_checkpoint_operator_parking_exit("conflict")

    def test_checkpoint_parking_exit_interrupted_evidence_change(self):
        self.assert_checkpoint_operator_parking_exit("interrupted-evidence-change")

    def test_terminal_parking_inventory_both_source(self):
        self.assert_terminal_operator_parking_exit("both-source")

    def test_terminal_parking_inventory_both_parked(self):
        self.assert_terminal_operator_parking_exit("both-parked")

    def test_terminal_parking_inventory_neither(self):
        self.assert_terminal_operator_parking_exit("neither")

    def test_terminal_parking_inventory_stale_and_current(self):
        self.assert_terminal_operator_parking_exit("stale-and-current")

    def test_terminal_parking_inventory_stale_only(self):
        self.assert_terminal_operator_parking_exit("stale-only")

    def test_terminal_parking_inventory_missing_pin(self):
        self.assert_terminal_operator_parking_exit("missing-pin")

    def test_checkpoint_parking_inventory_both_source(self):
        self.assert_checkpoint_operator_parking_exit("both-source")

    def test_checkpoint_parking_inventory_both_parked(self):
        self.assert_checkpoint_operator_parking_exit("both-parked")

    def test_checkpoint_parking_inventory_neither(self):
        self.assert_checkpoint_operator_parking_exit("neither")

    def test_checkpoint_parking_inventory_stale_and_current(self):
        self.assert_checkpoint_operator_parking_exit("stale-and-current")

    def test_checkpoint_parking_inventory_stale_only(self):
        self.assert_checkpoint_operator_parking_exit("stale-only")

    def test_checkpoint_parking_inventory_missing_pin(self):
        self.assert_checkpoint_operator_parking_exit("missing-pin")

    def test_terminal_pin_update_during_open(self):
        self.assert_terminal_operator_parking_exit("pin-update-during-open")

    def test_terminal_pin_update_before_return(self):
        self.assert_terminal_operator_parking_exit("pin-update-before-return")

    def test_terminal_pin_exit_before_replace(self):
        self.assert_terminal_operator_parking_exit("pin-exit-before-replace")

    def test_terminal_pin_exit_after_replace(self):
        self.assert_terminal_operator_parking_exit("pin-exit-after-replace")

    def test_terminal_pin_same_digest_replacement(self):
        self.assert_terminal_operator_parking_exit("pin-same-digest-replacement")

    def test_checkpoint_pin_update_during_open(self):
        self.assert_checkpoint_operator_parking_exit("pin-update-during-open")

    def test_checkpoint_pin_update_before_return(self):
        self.assert_checkpoint_operator_parking_exit("pin-update-before-return")

    def test_checkpoint_pin_exit_before_replace(self):
        self.assert_checkpoint_operator_parking_exit("pin-exit-before-replace")

    def test_checkpoint_pin_exit_after_replace(self):
        self.assert_checkpoint_operator_parking_exit("pin-exit-after-replace")

    def test_checkpoint_pin_same_digest_replacement(self):
        self.assert_checkpoint_operator_parking_exit("pin-same-digest-replacement")

    def assert_concurrent_review_after_interrupted_cleanup(self, target, stage, independent,
                                                           inspect, cleanup, tip):
        published = target.read_bytes()
        note = stage.with_name("operator-note")
        note.write_bytes(b"preserve this file")
        unlink = os.unlink

        for did_unlink in (False, True):
            with self.subTest(did_unlink=did_unlink):
                if did_unlink:
                    os.link(target, stage)

                def interrupt(*args, **kwargs):
                    if did_unlink:
                        unlink(*args, **kwargs)
                    os._exit(95)

                pid = os.fork()
                if pid == 0:
                    try:
                        with patch.object(receipts.os, "unlink", interrupt):
                            cleanup()
                    finally:
                        os._exit(96)
                _, status = os.waitpid(pid, 0)
                self.assertEqual(os.waitstatus_to_exitcode(status), 95)

                held = independent.with_suffix(".held")
                independent.rename(held)
                try:
                    for operation in (inspect, cleanup):
                        with self.assertRaises(recovery.DecimalRecoveryDenied):
                            operation()
                    self.assertEqual(stage.exists(), not did_unlink)
                finally:
                    held.rename(independent)

                start = Barrier(3, timeout=5)

                def compete(operation):
                    start.wait()
                    return operation()

                with ThreadPoolExecutor(max_workers=3) as pool:
                    reader = pool.submit(compete, inspect)
                    attempts = [pool.submit(compete, cleanup) for _ in range(2)]
                    result = reader.result(timeout=8)
                    errors = [attempt.exception(timeout=8) for attempt in attempts]
                self.assertEqual(result["receipt"], tip)
                if did_unlink:
                    self.assertFalse(result["additionalLinkPresent"])
                self.assertEqual(errors.count(None), int(not did_unlink))
                self.assertEqual(sum(isinstance(error, recovery.DecimalRecoveryDenied)
                                     for error in errors), 1 + int(did_unlink))
                self.assertEqual(inspect(), {"receipt": tip, "additionalLinkPresent": False})
                self.assertFalse(stage.exists())
                self.assertEqual(target.read_bytes(), published)
                self.assertEqual(note.read_bytes(), b"preserve this file")

    def test_terminal_readback_and_competing_cleanup_retry_after_process_exit(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        self.assert_concurrent_review_after_interrupted_cleanup(
            self.pin_path, stage, retained._store.path,
            partial(retained.inspect_local_terminal, self.pins, self.store, **evidence),
            partial(retained.cleanup_local_terminal_stage, stage, self.pins, self.store, **evidence),
            evidence["reviewed_receipt"])

    def test_checkpoint_readback_and_competing_cleanup_retry_after_process_exit(self):
        stage, exported, tip = self.reviewed_staging_link()
        independent = self.retain_independent_recovery_receipt(tip)
        evidence = self.recovery_evidence() | {"recovery_receipt": independent}
        self.assert_concurrent_review_after_interrupted_cleanup(
            self.checkpoint_path, stage, independent._store.path,
            partial(self.checkpoint.inspect_recovered, exported, trusted_receipt=tip, **evidence),
            partial(self.checkpoint.cleanup_recovered_stage, stage, exported,
                    trusted_receipt=tip, **evidence), tip)

    def assert_recovery_reader_holds_writer_commit(self, cleanup, writer, recorder, method):
        began = Event()
        sync = receipts._sync_directory
        write = getattr(recorder, method)
        jobs = []

        def write_under_lock(*args, **options):
            result = write(*args, **options)
            began.set()
            return result

        with ThreadPoolExecutor(max_workers=1) as pool:
            def sync_with_writer(directory):
                sync(directory)
                job = pool.submit(writer)
                jobs.append(job)
                self.assertTrue(began.wait(timeout=3))
                with self.assertRaises(TimeoutError):
                    job.result(timeout=0.05)

            with (patch.object(recorder, method, write_under_lock),
                  patch.object(receipts, "_sync_directory", sync_with_writer)):
                cleanup()
            job, = jobs
            return job.result(timeout=5)

    def test_checkpoint_cleanup_holds_signed_witness_commit_until_review_finishes(self):
        stage, exported, tip = self.reviewed_staging_link()
        updated = self.assert_recovery_reader_holds_writer_commit(
            lambda: self.cleanup_stage(stage, exported, tip),
            lambda: self.advance_signed_witness(tip), self.store, "_append")
        self.assertFalse(stage.exists())
        self.assertEqual(self.store.read(trusted_receipt=updated[1]), updated)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.checkpoint.inspect_recovered(exported, trusted_receipt=tip,
                                              **self.recovery_evidence())

    def test_checkpoint_cleanup_requires_fresh_exact_ledger_after_writer_commit(self):
        stage, exported, tip = self.reviewed_staging_link()
        fill = self.assert_recovery_reader_holds_writer_commit(
            lambda: self.cleanup_stage(stage, exported, tip),
            self.append_synthetic_ledger_fill, ledger, "_step")
        self.assertFalse(stage.exists())
        self.assertFalse(fill["duplicate"])
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.checkpoint.inspect_recovered(exported, trusted_receipt=tip,
                                              **self.recovery_evidence())

    def advance_signed_witness(self, tip, *, interrupt=None):
        record = recovery.quarantine_decimal_recovery(
            record=self.promotion, trusted_tip=recovery.evidence_tip(self.promotion),
            operator_key=self.operator, reason="INTEGRITY_FAILURE")
        updated = self.store.publish(record, expected_receipt=tip, _interrupt=interrupt)
        return record, updated, False

    def append_synthetic_ledger_fill(self, *, fail_before_commit=False):
        return ledger.decimal_fill(
            self.path, hmac_key=self.replacement, request_id=str(uuid4()), side="BUY",
            asset_class="stock", symbol="MSFT", quantity="0.25",
            assumed_unit_price="2.00", _fail_before_commit=fail_before_commit, **self.scope)

    def assert_checkpoint_readback_after_writer_rollback(self, recorder, method, writer, denied):
        stage, exported, tip = self.reviewed_staging_link()
        unrelated = stage.with_name("operator-note")
        unrelated.write_bytes(b"keep this file")
        original, content = self.checkpoint_path.stat(), self.checkpoint_path.read_bytes()
        witness_before, ledger_before = self.store_path.read_bytes(), self.path.read_bytes()
        read = self.checkpoint._store._read_published
        write = getattr(recorder, method)
        attempted = []

        def mark_written(*args, **kwargs):
            result = write(*args, **kwargs)
            attempted.append(True)
            return result

        with ThreadPoolExecutor(max_workers=1) as pool:
            @contextmanager
            def read_with_rollback(receipt):
                # Recovery has already acquired and verified all evidence snapshots.
                with read(receipt) as info:
                    with self.assertRaises(denied):
                        pool.submit(writer, tip).result(timeout=5)
                    yield info

            with (patch.object(recorder, method, mark_written),
                  patch.object(self.checkpoint._store, "_read_published", read_with_rollback)):
                self.assert_checkpoint_readback(stage, exported, tip, original, content, linked=True)

        self.assertEqual(attempted, [True])
        self.assertEqual(self.store_path.read_bytes(), witness_before)
        self.assertEqual(self.path.read_bytes(), ledger_before)
        self.assertTrue(stage.samefile(self.checkpoint_path))
        self.cleanup_stage(stage, exported, tip)
        self.assert_checkpoint_readback(stage, exported, tip, original, content, linked=False)
        self.assertEqual(unrelated.read_bytes(), b"keep this file")

    def test_checkpoint_readback_and_cleanup_survive_signed_witness_rollback(self):
        self.assert_checkpoint_readback_after_writer_rollback(
            self.store, "_append",
            lambda tip: self.advance_signed_witness(tip, interrupt="before_commit"),
            recovery.DecimalRecoveryDenied)

    def test_checkpoint_readback_and_cleanup_survive_ledger_rollback(self):
        self.assert_checkpoint_readback_after_writer_rollback(
            ledger, "_step", lambda _: self.append_synthetic_ledger_fill(fail_before_commit=True),
            ledger.DecimalAtomicDenied)

    def test_terminal_readback_and_cleanup_wait_for_independent_receipt_rollback(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        independent = retained._store
        tip = evidence["reviewed_receipt"]
        unrelated = stage.with_name("operator-note")
        unrelated.write_bytes(b"keep this file")
        original, content = self.pin_path.stat(), self.pin_path.read_bytes()
        independent_before = independent.path.read_bytes()
        pin = independent._pin

        def inspect():
            return retained.inspect_local_terminal(self.pins, self.store, **evidence)

        def cleanup():
            retained.cleanup_local_terminal_stage(stage, self.pins, self.store, **evidence)

        with ThreadPoolExecutor(max_workers=1) as pool:
            for operation in (inspect, cleanup):
                with self.subTest(operation=operation.__name__):
                    trying = Event()

                    def pin_under_contention(*args, **kwargs):
                        trying.set()
                        return pin(*args, **kwargs)

                    with patch.object(independent, "_pin", pin_under_contention):
                        with independent._open() as transaction:
                            independent._save(transaction, tip, pending=True)
                            self.assertEqual(independent._read_state(transaction), (tip, True))
                            pending = pool.submit(operation)
                            self.assertTrue(trying.wait(timeout=3))
                            with self.assertRaises(TimeoutError):
                                pending.result(timeout=0.05)
                            self.assertTrue(stage.samefile(self.pin_path))
                            transaction.rollback()
                        result = pending.result(timeout=5)
                        if operation is inspect:
                            self.assertEqual(result, {"receipt": tip, "additionalLinkPresent": True})
                    self.assertEqual(independent.path.read_bytes(), independent_before)
                    self.assertEqual(independent.latest(), tip)
                    self.assertTrue(os.path.samestat(self.pin_path.stat(), original))
                    self.assertEqual(self.pin_path.read_bytes(), content)
                    self.assertEqual(unrelated.read_bytes(), b"keep this file")

        self.assertFalse(stage.exists())
        self.assertEqual(inspect(), {"receipt": tip, "additionalLinkPresent": False})

    def assert_stale_checkpoint_operations_refused(self, stage, exported, tip, unrelated,
                                                  *, stage_present):
        original, content = self.checkpoint_path.stat(), self.checkpoint_path.read_bytes()
        missing = self.checkpoint_path.with_name("missing-checkpoint.db")
        folders = set(self.checkpoint_path.parent.iterdir())
        for operation in (
                lambda: self.checkpoint.inspect_recovered(
                    exported, trusted_receipt=tip, **self.recovery_evidence()),
                lambda: self.cleanup_stage(stage, exported, tip),
                lambda: receipts.DecimalPromotionCheckpoint.recover(
                    missing, exported, trusted_receipt=tip,
                    checkpoint_key=self.checkpoint_key, **self.recovery_evidence())):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                operation()
            self.assertFalse(missing.exists())
            self.assertEqual(set(self.checkpoint_path.parent.iterdir()), folders)
            self.assertTrue(os.path.samestat(self.checkpoint_path.stat(), original))
            self.assertEqual(self.checkpoint_path.read_bytes(), content)
            self.assertEqual(stage.exists(), stage_present)
            if stage_present:
                self.assertTrue(stage.samefile(self.checkpoint_path))
            self.assertEqual(unrelated.read_bytes(), b"unrelated evidence")

    def test_checkpoint_recovery_refuses_witness_commit_before_review(self):
        stage, exported, tip = self.reviewed_staging_link()
        unrelated = stage.with_name("operator-note")
        unrelated.write_bytes(b"unrelated evidence")
        updated = self.advance_signed_witness(tip)
        self.assertEqual(self.store.read(trusted_receipt=updated[1]), updated)
        self.assert_stale_checkpoint_operations_refused(
            stage, exported, tip, unrelated, stage_present=True)

    def test_checkpoint_recovery_refuses_ledger_commit_before_review(self):
        stage, exported, tip = self.reviewed_staging_link()
        unrelated = stage.with_name("operator-note")
        unrelated.write_bytes(b"unrelated evidence")
        self.assertFalse(self.append_synthetic_ledger_fill()["duplicate"])
        self.assert_stale_checkpoint_operations_refused(
            stage, exported, tip, unrelated, stage_present=True)

    def exit_at_cleanup_unlink_with_writer(self, cleanup, writer, recorder, method, *, unlink_first):
        parent, child = socket.socketpair()
        with parent, child:
            parent.settimeout(5)
            child.settimeout(5)
            pid = os.fork()
            if pid == 0:
                parent.close()
                unlink = os.unlink

                def stop_at_unlink(*args, **kwargs):
                    if unlink_first:
                        unlink(*args, **kwargs)
                    child.sendall(b"R")
                    os._exit(95 if child.recv(1) == b"X" else 96)

                try:
                    with patch.object(receipts.os, "unlink", stop_at_unlink):
                        cleanup()
                finally:
                    os._exit(96)
            child.close()
            began = Event()
            write = getattr(recorder, method)

            def mark_started(*args, **kwargs):
                result = write(*args, **kwargs)
                began.set()
                return result

            with ThreadPoolExecutor(max_workers=1) as pool:
                with patch.object(recorder, method, mark_started):
                    try:
                        self.assertEqual(parent.recv(1), b"R")
                        pending = pool.submit(writer)
                        self.assertTrue(began.wait(timeout=3))
                        with self.assertRaises(TimeoutError):
                            pending.result(timeout=0.05)
                        parent.sendall(b"X")
                    except BaseException:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        raise
                    finally:
                        _, status = os.waitpid(pid, 0)
                    self.assertEqual(os.waitstatus_to_exitcode(status), 95)
                    return pending.result(timeout=5)

    def test_checkpoint_cleanup_exit_before_unlink_releases_signed_witness_writer(self):
        stage, exported, tip = self.reviewed_staging_link()
        unrelated = stage.with_name("operator-note")
        unrelated.write_bytes(b"unrelated evidence")
        updated = self.exit_at_cleanup_unlink_with_writer(
            lambda: self.cleanup_stage(stage, exported, tip),
            lambda: self.advance_signed_witness(tip), self.store, "_append", unlink_first=False)
        self.assertEqual(self.store.read(trusted_receipt=updated[1]), updated)
        self.assert_stale_checkpoint_operations_refused(
            stage, exported, tip, unrelated, stage_present=True)

    def test_checkpoint_cleanup_exit_after_unlink_releases_ledger_writer(self):
        stage, exported, tip = self.reviewed_staging_link()
        unrelated = stage.with_name("operator-note")
        unrelated.write_bytes(b"unrelated evidence")
        result = self.exit_at_cleanup_unlink_with_writer(
            lambda: self.cleanup_stage(stage, exported, tip),
            self.append_synthetic_ledger_fill, ledger, "_step", unlink_first=True)
        self.assertFalse(result["duplicate"])
        self.assert_stale_checkpoint_operations_refused(
            stage, exported, tip, unrelated, stage_present=False)

    def assert_reviewed_cleanup_checks(self, target, stage, evidence_path, cleanup, inspect, tip):
        original, content = target.stat(), target.read_bytes()
        sync = receipts._sync_directory

        def write_evidence():
            with sqlite3.connect(evidence_path, timeout=0) as writer:
                writer.execute("BEGIN IMMEDIATE")
                self.assertEqual(writer.execute(
                    "UPDATE retained_receipt SET pending=pending WHERE id=1").rowcount, 1)

        with ThreadPoolExecutor(max_workers=1) as pool:
            for replacement in (target, stage, stage.parent):
                saved = replacement.with_name(replacement.name + ".saved")

                def replace_during_review(directory):
                    sync(directory)
                    with self.assertRaisesRegex(sqlite3.OperationalError, "database is locked"):
                        pool.submit(write_evidence).result(timeout=5)
                    replacement.rename(saved)
                    if replacement == stage.parent:
                        replacement.symlink_to(saved, target_is_directory=True)
                    else:
                        replacement.write_bytes(content)
                        replacement.chmod(0o600)

                with self.subTest(replacement=replacement):
                    with patch.object(receipts, "_sync_directory", replace_during_review):
                        with self.assertRaises(recovery.DecimalRecoveryDenied):
                            cleanup()
                    if replacement == stage.parent:
                        self.assertTrue(stage.samefile(target))
                        self.assertTrue((saved / stage.name).samefile(target))
                        replacement.unlink()
                    else:
                        self.assertEqual(replacement.read_bytes(), content)
                        self.assertFalse(replacement.samefile(saved))
                    saved.replace(replacement)
                    self.assertTrue(stage.samefile(target))
                    self.assertTrue(os.path.samestat(target.stat(), original))
                    self.assertEqual(inspect(), {"receipt": tip, "additionalLinkPresent": True})
                    pool.submit(write_evidence).result(timeout=5)

        cleanup()
        self.assertFalse(stage.exists())
        self.assertTrue(os.path.samestat(target.stat(), original))
        self.assertEqual(target.read_bytes(), content)
        self.assertEqual(inspect(), {"receipt": tip, "additionalLinkPresent": False})

    def test_terminal_cleanup_refuses_replaced_publication_names_under_evidence_lock(self):
        retained, evidence, stage, _ = self.terminal_cleanup_fixture()
        self.assert_reviewed_cleanup_checks(
            self.pin_path, stage, retained._store.path,
            lambda: retained.cleanup_local_terminal_stage(stage, self.pins, self.store, **evidence),
            lambda: retained.inspect_local_terminal(self.pins, self.store, **evidence),
            evidence["reviewed_receipt"])

    def test_checkpoint_cleanup_refuses_replaced_publication_names_under_evidence_lock(self):
        stage, exported, tip = self.reviewed_staging_link()
        self.assert_reviewed_cleanup_checks(
            self.checkpoint_path, stage, self.pin_path,
            lambda: self.cleanup_stage(stage, exported, tip),
            lambda: self.checkpoint.inspect_recovered(
                exported, trusted_receipt=tip, **self.recovery_evidence()),
            tip)

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
        folder, = self.checkpoint_path.parent.glob(".edgepilot-checkpoint-*")
        self.assertEqual(list(folder.iterdir()), [])

    def test_cleanup_refuses_active_publisher_even_at_exact_link(self):
        self.prepare_checkpoint()
        tip = self.promote()
        exported = self.checkpoint.export(expected_receipt=tip)
        self.checkpoint_path.unlink()
        link = os.link

        def while_publishing(*args, **kwargs):
            link(*args, **kwargs)
            target = self.checkpoint_path
            stage, = target.parent.glob(".edgepilot-checkpoint-*/checkpoint.db")
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
