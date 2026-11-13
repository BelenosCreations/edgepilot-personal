"""v0.2.100: separate, HMAC-authenticated synthetic paper stop latch tests."""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid

from engine import tenant_paper_latch_rehearsal as latch

def ident():
    return str(uuid.uuid4())


class OfflineAtomicLatchRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(
            dir="/dev/shm", prefix="edgepilot-latch-v02100-")
        self.path = Path(self.tmp.name) / "scratch.db"
        self.key = os.urandom(32)
        self.owner, self.other = ident(), ident()
        self.primary, self.second, self.foreign = ident(), ident(), ident()
        latch.create_synthetic_fixture(self.path)
        self.register(self.owner, self.primary, 14)
        self.register(self.owner, self.second, 7)
        self.register(self.other, self.foreign, 7)

    def tearDown(self):
        self.tmp.cleanup()

    def register(self, user, account, limit):
        return latch.register_synthetic_policy(
            self.path, hmac_key=self.key, principal_user_id=user,
            account_id=account, max_loss_cents=limit)

    def attempt(self, kind, delta=0, *, user=None, account=None,
                req=None, fail=False, key=None):
        return latch.rehearse_atomic_request(
            self.path, hmac_key=self.key if key is None else key,
            principal_user_id=user or self.owner,
            account_id=account or self.primary,
            request_id=req or ident(), kind=kind,
            realized_delta_cents=delta, _fail_before_commit=fail)

    def inspect(self, *, user=None, account=None, key=None):
        return latch.inspect_synthetic_policy(
            self.path, hmac_key=self.key if key is None else key,
            principal_user_id=user or self.owner,
            account_id=account or self.primary)

    def test_threshold_latches_durably_through_gains_and_restart(self):
        self.assertTrue(self.attempt("OPEN")["simulatedAccepted"])
        self.attempt("REALIZE", -7)
        self.assertFalse(self.inspect()["durableSyntheticLatch"])
        self.attempt("REALIZE", -7)
        self.assertEqual(self.inspect()["worstHistoricalRealizedCents"], -14)
        self.assertTrue(self.inspect()["durableSyntheticLatch"])
        blocked = self.attempt("OPEN")
        self.assertFalse(blocked["simulatedAccepted"])
        self.attempt("REALIZE", 30)  # Closing/reconciliation is not blocked.
        after = self.inspect()  # Reads new SQLite connection after commit.
        self.assertEqual(after["currentRealizedCents"], 16)
        self.assertEqual(after["worstHistoricalRealizedCents"], -14)
        self.assertTrue(after["durableSyntheticLatch"])
        self.assertFalse(self.attempt("OPEN")["simulatedAccepted"])
        self.assertFalse(after["executionEnabled"])
        self.assertFalse(after["atomicFillEnforcementActive"])

    def test_idempotency_and_conflict_replay(self):
        first_id = ident()
        first = self.attempt("REALIZE", -14, req=first_id)
        self.assertFalse(first["duplicate"])
        again = self.attempt("REALIZE", -14, req=first_id)
        self.assertTrue(again["duplicate"])
        self.assertEqual(self.inspect()["currentRealizedCents"], -14)
        with self.assertRaises(latch.PaperLatchDenied):
            self.attempt("REALIZE", -13, req=first_id)
        with self.assertRaises(latch.PaperLatchDenied):
            self.attempt("OPEN", req=first_id)
        # Retry of a pre-latch accepted OPEN returns its original outcome.
        earlier = ident()
        self.attempt("OPEN", account=self.second, req=earlier)
        self.attempt("REALIZE", -7, account=self.second)
        replay = self.attempt("OPEN", account=self.second, req=earlier)
        self.assertTrue(replay["duplicate"])
        self.assertTrue(replay["simulatedAccepted"])
        self.assertFalse(self.attempt("OPEN", account=self.second)[
            "simulatedAccepted"])

    def test_account_and_user_partitioning(self):
        self.attempt("REALIZE", -14)
        self.assertTrue(self.inspect()["durableSyntheticLatch"])
        self.assertFalse(self.inspect(account=self.second)["durableSyntheticLatch"])
        self.assertFalse(self.inspect(user=self.other,
                                      account=self.foreign)["durableSyntheticLatch"])
        self.assertTrue(self.attempt("OPEN", account=self.second)[
            "simulatedAccepted"])
        self.assertTrue(self.attempt("OPEN", user=self.other,
                                     account=self.foreign)["simulatedAccepted"])
        with self.assertRaises(latch.PaperLatchDenied):
            self.inspect(user=self.other, account=self.primary)
        with self.assertRaises(latch.PaperLatchDenied):
            self.attempt("OPEN", user=self.other, account=self.primary)
        with self.assertRaises(latch.PaperLatchDenied):
            self.register(self.owner, self.primary, 99)
        self.assertFalse(self.register(self.owner, self.primary, 14)["registered"])

    def test_transaction_rolls_back_before_commit(self):
        baseline = self.inspect()
        req = ident()
        with self.assertRaises(latch.PaperLatchDenied):
            self.attempt("REALIZE", -14, req=req, fail=True)
        self.assertEqual(self.inspect(), baseline)
        self.assertFalse(self.attempt("REALIZE", -14, req=req)["duplicate"])
        self.assertTrue(self.inspect()["durableSyntheticLatch"])

    def test_hmac_tamper_missing_key_and_log_deletion_fail_closed(self):
        self.attempt("REALIZE", -7)
        wrong_key = os.urandom(32)
        with self.assertRaises(latch.PaperLatchDenied):
            self.inspect(key=wrong_key)
        with sqlite3.connect(self.path) as db:
            db.execute("""UPDATE offline_latch_journal SET delta_cents=-8
                WHERE user_id=? AND account_id=?""",
                (self.owner, self.primary))
        with self.assertRaises(latch.PaperLatchDenied):
            self.inspect()
        with self.assertRaises(latch.PaperLatchDenied):
            self.attempt("OPEN")
        with sqlite3.connect(self.path) as db:
            db.execute("""UPDATE offline_latch_journal SET delta_cents=-7
                WHERE user_id=? AND account_id=?""",
                (self.owner, self.primary))
        self.assertEqual(self.inspect()["currentRealizedCents"], -7)
        with sqlite3.connect(self.path) as db:
            db.execute("""DELETE FROM offline_latch_journal
                WHERE user_id=? AND account_id=?""",
                (self.owner, self.primary))
        with self.assertRaises(latch.PaperLatchDenied):
            self.inspect()

    def test_refuse_unsafe_inputs_and_existing_files(self):
        with self.assertRaises(latch.PaperLatchDenied):
            latch.create_synthetic_fixture(self.path)
        with tempfile.TemporaryDirectory() as ordinary_dir:
            with self.assertRaises(latch.PaperLatchDenied):
                latch.create_synthetic_fixture(
                    Path(ordinary_dir) / "unsafe.db")
        for amount in (0, -1, True, 0.1, "14", None, 100_000_000_001):
            with self.subTest(amount=amount):
                with self.assertRaises(latch.PaperLatchDenied):
                    self.register(ident(), ident(), amount)
        with self.assertRaises(latch.PaperLatchDenied):
            self.attempt("OPEN", -1)
        with self.assertRaises(latch.PaperLatchDenied):
            self.attempt("BUY")
        with self.assertRaises(latch.PaperLatchDenied):
            self.attempt("OPEN", req="not-a-uuid")
        with self.assertRaises(latch.PaperLatchDenied):
            self.attempt("OPEN", key=b"short")
        source = (Path(__file__).resolve().parents[1] / "app.py").read_text()
        self.assertNotIn("tenant_paper_latch_rehearsal", source)
        self.assertNotIn("/api/identity/paper/latch", source)


if __name__ == "__main__":
    unittest.main()
