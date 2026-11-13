"""v0.2.101: offline externally pinned synthetic latch recovery tests."""
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
import uuid

from engine import tenant_paper_latch_rehearsal as latch
from engine import tenant_paper_latch_attestation as attest


def uid():
    return str(uuid.uuid4())


class AttestedSyntheticLatchTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(
            dir="/dev/shm", prefix="edgepilot-attest-v02101-")
        self.path = Path(self.scratch.name) / "state.db"
        self.old_path = Path(self.scratch.name) / "old.db"
        self.journal_key = os.urandom(32)
        self.anchor_key = os.urandom(32)
        self.next_key = os.urandom(32)
        self.user1, self.user2 = uid(), uid()
        self.account1, self.account2, self.account3 = uid(), uid(), uid()
        latch.create_synthetic_fixture(self.path)
        for user, account, limit in (
                (self.user1, self.account1, 14),
                (self.user1, self.account2, 7),
                (self.user2, self.account3, 20)):
            latch.register_synthetic_policy(
                self.path, hmac_key=self.journal_key,
                principal_user_id=user, account_id=account,
                max_loss_cents=limit)

    def tearDown(self):
        self.scratch.cleanup()

    def event(self, kind, amount=0, *, user=None, account=None, key=None):
        return latch.rehearse_atomic_request(
            self.path,
            hmac_key=key if key is not None else self.journal_key,
            principal_user_id=user or self.user1,
            account_id=account or self.account1,
            request_id=uid(), kind=kind, realized_delta_cents=amount)

    def pin(self, *, epoch=1, key=None, anchor=None, path=None):
        return attest.make_synthetic_checkpoint(
            path or self.path,
            journal_key=key if key is not None else self.journal_key,
            anchor_key=anchor if anchor is not None else self.anchor_key,
            epoch=epoch)

    def verify(self, pinned, *, key=None, anchor=None, path=None):
        return attest.verify_synthetic_checkpoint(
            path or self.path,
            journal_key=key if key is not None else self.journal_key,
            anchor_key=anchor if anchor is not None else self.anchor_key,
            pinned=pinned)

    def rotate(self, pinned, *, key=None, epoch=2, fail=False):
        return attest.rotate_synthetic_journal_key(
            self.path, old_journal_key=self.journal_key,
            new_journal_key=key if key is not None else self.next_key,
            anchor_key=self.anchor_key, pinned=pinned,
            new_epoch=epoch, _fail_before_commit=fail)

    def test_cross_account_attestation_preserves_sticky_loss(self):
        self.event("REALIZE", -14)
        self.event("OPEN")
        self.event("REALIZE", 40)
        self.event("OPEN", account=self.account2)
        self.event("REALIZE", -6, user=self.user2, account=self.account3)
        checkpoint = self.pin()
        self.assertEqual(checkpoint["accounts"], 3)
        self.assertEqual(checkpoint["events"], 5)
        self.assertEqual(self.verify(checkpoint)["accounts"], 3)
        self.assertTrue(latch.inspect_synthetic_policy(
            self.path, hmac_key=self.journal_key,
            principal_user_id=self.user1,
            account_id=self.account1)["durableSyntheticLatch"])
        self.assertFalse(self.event("OPEN")["simulatedAccepted"])
        with self.assertRaises(attest.AttestedLatchDenied):
            self.verify(checkpoint)
        self.assertEqual(self.verify(self.pin())["events"], 6)

    def test_whole_file_rollback_is_detected_against_latest_external_pin(self):
        self.event("REALIZE", -7)
        shutil.copy2(self.path, self.old_path)
        old_pin = self.pin()
        self.event("REALIZE", -7)
        latest_pin = self.pin()
        self.assertNotEqual(old_pin["stateSha256"], latest_pin["stateSha256"])
        shutil.copy2(self.old_path, self.path)
        # The old file still has valid journal MACs; the independent pin is
        # what detects a rollback of the entire database and lost latch.
        self.assertEqual(latch.inspect_synthetic_policy(
            self.path, hmac_key=self.journal_key,
            principal_user_id=self.user1,
            account_id=self.account1)["worstHistoricalRealizedCents"], -7)
        self.assertTrue(self.verify(old_pin)["checkpointVerified"])
        with self.assertRaises(attest.AttestedLatchDenied):
            self.verify(latest_pin)
        with self.assertRaises(attest.AttestedLatchDenied):
            self.rotate(latest_pin)

    def test_wrong_anchor_keys_policy_deletion_and_orphan_journal(self):
        self.event("REALIZE", -7)
        pinned = self.pin()
        for key, anchor in (
                (os.urandom(32), self.anchor_key),
                (self.journal_key, os.urandom(32)),
                (self.journal_key, self.journal_key)):
            with self.subTest(key=key == self.journal_key,
                              anchor=anchor == self.anchor_key):
                with self.assertRaises(attest.AttestedLatchDenied):
                    self.verify(pinned, key=key, anchor=anchor)
        invalid = dict(pinned, accounts=True)
        with self.assertRaises(attest.AttestedLatchDenied):
            self.verify(invalid)
        invalid = dict(pinned, epoch=0)
        with self.assertRaises(attest.AttestedLatchDenied):
            self.verify(invalid)
        invalid = dict(pinned, untrusted=True)
        with self.assertRaises(attest.AttestedLatchDenied):
            self.verify(invalid)
        with sqlite3.connect(self.path) as db:
            db.execute("""DELETE FROM offline_latch_policies
                WHERE user_id=? AND account_id=?""",
                (self.user1, self.account1))
        with self.assertRaises(attest.AttestedLatchDenied):
            self.pin()
        with self.assertRaises(attest.AttestedLatchDenied):
            self.verify(pinned)

    def test_rollback_of_entire_account_without_orphan_is_detected(self):
        pinned = self.pin()
        with sqlite3.connect(self.path) as db:
            db.execute("""DELETE FROM offline_latch_policies
                WHERE user_id=? AND account_id=?""",
                (self.user2, self.account3))
        # Account removed with no events: only a whole-fixture pin catches it.
        self.assertEqual(self.pin()["accounts"], 2)
        with self.assertRaises(attest.AttestedLatchDenied):
            self.verify(pinned)

    def test_key_rotation_reauthenticates_all_scopes_and_refuses_old_key(self):
        self.event("REALIZE", -14)
        self.event("OPEN")
        self.event("REALIZE", -7, user=self.user2, account=self.account3)
        pinned = self.pin()
        renewed = self.rotate(pinned)
        self.assertEqual((renewed["accounts"], renewed["events"],
                          renewed["epoch"]), (3, 3, 2))
        self.assertTrue(self.verify(renewed, key=self.next_key)[
            "checkpointVerified"])
        with self.assertRaises(attest.AttestedLatchDenied):
            self.verify(renewed)
        with self.assertRaises(attest.AttestedLatchDenied):
            self.verify(pinned)
        with self.assertRaises(attest.AttestedLatchDenied):
            self.rotate(pinned)
        self.assertTrue(latch.inspect_synthetic_policy(
            self.path, hmac_key=self.next_key,
            principal_user_id=self.user1,
            account_id=self.account1)["durableSyntheticLatch"])
        self.assertFalse(self.event("OPEN", key=self.next_key)[
            "simulatedAccepted"])
        fresh = self.pin(epoch=2, key=self.next_key)
        self.assertEqual(self.verify(fresh, key=self.next_key)["events"], 4)

    def test_rotation_rejects_stale_pin_epoch_and_crash_rolls_back(self):
        pinned = self.pin()
        self.event("REALIZE", -7)
        with self.assertRaises(attest.AttestedLatchDenied):
            self.rotate(pinned)
        current = self.pin()
        for new_key, epoch in (
                (self.journal_key, 2), (self.anchor_key, 2),
                (self.next_key, 1), (self.next_key, 3)):
            with self.subTest(epoch=epoch, key=new_key == self.next_key):
                with self.assertRaises(attest.AttestedLatchDenied):
                    self.rotate(current, key=new_key, epoch=epoch)
        with self.assertRaises(attest.AttestedLatchDenied):
            self.rotate(current, fail=True)
        self.assertTrue(self.verify(current)["checkpointVerified"])
        with self.assertRaises(attest.AttestedLatchDenied):
            self.verify(current, key=self.next_key)
        new_pin = self.rotate(current)
        self.assertTrue(self.verify(new_pin, key=self.next_key)[
            "checkpointVerified"])

    def test_reject_non_tmpfs_and_keep_app_and_writer_disconnected(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            with self.assertRaises(attest.AttestedLatchDenied):
                self.pin(path=Path(elsewhere) / "missing.db")
        root = Path(__file__).resolve().parents[1]
        for path in (root / "app.py",
                     root / "engine" / "tenant_paper_ledger.py"):
            source = path.read_text()
            self.assertNotIn("tenant_paper_latch_attestation", source)
            self.assertNotIn("rotate_synthetic_journal_key", source)


if __name__ == "__main__":
    unittest.main()
