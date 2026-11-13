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

from cryptography.fernet import Fernet

from engine import tenant_paper_decimal_archive as archive
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
        options = {"retain_claim": lambda _expected, claim: claim} | kwargs
        return self.store.rotate(
            self.path, expected_receipt=receipt, journal_key=self.journal,
            replacement_key=self.replacement, anchor_key=self.anchor, **options)

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
                              replacement_key=self.replacement, anchor_key=os.urandom(32),
                              retain_claim=lambda _expected, claim: claim)
        self.assertEqual(self.store.read(trusted_receipt=receipt), (pending, receipt, False))

    def recover_witness(self, snapshot, receipt, *, journal_key=None):
        return custody.DecimalCustody.recover(
            self.store_path, snapshot, trusted_receipt=receipt, custody_key=self.custody,
            operator_key=self.operator, ledger_path=self.path,
            journal_key=self.journal if journal_key is None else journal_key,
            anchor_key=self.anchor)

    def test_lost_witness_requires_exact_independent_copy_and_surviving_ledger(self):
        snapshot = self.store.backup(expected_receipt=self.genesis)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.recover_witness(snapshot, self.genesis)
        self.store_path.unlink()
        self.path.rename(self.old)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.recover_witness(snapshot, self.genesis)
        self.assertFalse(self.store_path.exists())
        self.old.rename(self.path)
        reopened = self.recover_witness(snapshot, self.genesis)
        self.assertEqual(reopened.read(trusted_receipt=self.genesis),
                         (self.active, self.genesis, False))
        self.assertEqual(reopened.path.stat().st_mode & 0o777, 0o600)

    def test_recovered_witness_never_replays_claim_or_recovers_a_stale_copy(self):
        pending = self.prepare()
        receipt = self.store.publish(pending, expected_receipt=self.genesis)
        unclaimed = self.store.backup(expected_receipt=receipt)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.rotate(receipt, _interrupt="after_claim")
        _, claim, _ = self.store.read(trusted_receipt=receipt)
        claimed = self.store.backup(expected_receipt=claim)
        self.store_path.unlink()
        for snapshot, pin in ((unclaimed, receipt), (unclaimed, claim), (claimed, receipt)):
            with self.subTest(pin=pin), self.assertRaises(recovery.DecimalRecoveryDenied):
                self.recover_witness(snapshot, pin)
        self.store = self.recover_witness(claimed, claim)
        self.assertEqual(self.store.read(trusted_receipt=claim), (pending, claim, True))
        self.assertEqual(self.inspect(pending, self.journal), "AMBIGUOUS_OLD_STATE")
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.rotate(claim)

    def test_lost_ledger_restore_uses_latest_active_witness_and_exact_archive(self):
        archive_key = Fernet.generate_key()
        old = archive.seal_decimal_archive(
            self.path, record=self.active, trusted_tip=recovery.evidence_tip(self.active),
            archive_key=archive_key, **self.keys)
        pending = self.prepare()
        receipt = self.store.publish(pending, expected_receipt=self.genesis)
        claim = self.rotate(receipt)
        keys = self.keys | {"journal_key": self.replacement}
        active = recovery.approve_decimal_promotion(
            self.path, record=pending, trusted_tip=recovery.evidence_tip(pending), **keys)
        tip = self.store.publish(active, expected_receipt=claim)
        token = archive.seal_decimal_archive(
            self.path, record=active, trusted_tip=recovery.evidence_tip(active),
            archive_key=archive_key, **keys)
        self.path.unlink()

        def restore(ciphertext, approval_record, expected_receipt, **kwargs):
            approval = archive.approve_decimal_restore(
                ciphertext, self.path, record=approval_record,
                trusted_tip=recovery.evidence_tip(approval_record), operator_key=self.operator)
            return self.store.restore_ledger(
                ciphertext, self.path, approval=approval, expected_receipt=expected_receipt,
                journal_key=self.replacement, anchor_key=self.anchor, archive_key=archive_key,
                **kwargs)

        for ciphertext, approval_record, expected_receipt in (
                (old, self.active, self.genesis), (token, active, claim), (old, active, tip)):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                restore(ciphertext, approval_record, expected_receipt)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            restore(token, active, tip, _interrupt_before_publish=True)
        self.assertFalse(self.path.exists())
        self.assertEqual(restore(token, active, tip), self.path)
        self.assertEqual(self.inspect(active, self.replacement), "PINNED_ACTIVE")
        before = self.path.read_bytes()
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            restore(token, active, tip)
        self.assertEqual(self.path.read_bytes(), before)

    def test_lost_external_claim_acknowledgment_stops_before_ledger_write(self):
        pending = self.prepare()
        receipt = self.store.publish(pending, expected_receipt=self.genesis)
        prior = self.path.read_bytes()
        receipt_path = self.store_path.with_name("retained-receipt")

        def retain_then_lose_reply(expected, claim):
            self.assertEqual(expected, receipt)
            with receipt_path.open("x") as file:
                file.write(claim["mac"])
                file.flush()
                os.fsync(file.fileno())
            raise ConnectionError

        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.rotate(receipt, retain_claim=retain_then_lose_reply)
        _, claim, claimed = self.store.read(trusted_receipt=receipt)
        self.assertTrue(claimed)
        self.assertEqual(receipt_path.read_text(), claim["mac"])
        self.assertEqual(self.path.read_bytes(), prior)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.rotate(claim)
