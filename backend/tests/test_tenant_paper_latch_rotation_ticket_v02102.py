"""v0.2.102: offline precommitted synthetic rotation ticket failures."""
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid

from engine import tenant_paper_latch_rehearsal as latch
from engine import tenant_paper_latch_attestation as attest
from engine import tenant_paper_latch_rotation_ticket as ticket


def ident():
    return str(uuid.uuid4())


class OfflineRotationTicketTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(
            dir="/dev/shm", prefix="edgepilot-rotation-ticket-v02102-")
        self.path = Path(self.folder.name) / "fixture.db"
        self.backup = Path(self.folder.name) / "old-copy.db"
        self.old, self.fresh, self.anchor = (
            os.urandom(32), os.urandom(32), os.urandom(32))
        self.a, self.b = ident(), ident()
        self.x, self.y, self.z = ident(), ident(), ident()
        latch.create_synthetic_fixture(self.path)
        for user, account, threshold in (
                (self.a, self.x, 14),
                (self.a, self.y, 7),
                (self.b, self.z, 30)):
            latch.register_synthetic_policy(
                self.path, hmac_key=self.old,
                principal_user_id=user, account_id=account,
                max_loss_cents=threshold)
        self.record("REALIZE", -14, user=self.a, account=self.x)
        self.record("OPEN", user=self.a, account=self.x)
        self.record("REALIZE", -7, user=self.b, account=self.z)
        self.pinned = attest.make_synthetic_checkpoint(
            self.path, journal_key=self.old,
            anchor_key=self.anchor, epoch=1)

    def tearDown(self):
        self.folder.cleanup()

    def record(self, kind, delta=0, *, user=None, account=None, key=None):
        return latch.rehearse_atomic_request(
            self.path, hmac_key=key or self.old,
            principal_user_id=user or self.a, account_id=account or self.x,
            request_id=ident(), kind=kind, realized_delta_cents=delta)

    def plan(self, *, pinned=None, fresh=None, epoch=2, anchor=None):
        return ticket.prepare_synthetic_rotation_ticket(
            self.path, old_journal_key=self.old,
            new_journal_key=fresh or self.fresh,
            anchor_key=anchor or self.anchor,
            pinned=pinned if pinned is not None else self.pinned,
            new_epoch=epoch)

    def execute(self, intent, *, fail=False, fresh=None):
        return ticket.execute_synthetic_prepared_rotation(
            self.path, old_journal_key=self.old,
            new_journal_key=fresh or self.fresh,
            anchor_key=self.anchor, ticket=intent,
            _fail_before_commit=fail)

    def outcome(self, intent, *, anchor=None):
        return ticket.inspect_synthetic_rotation_outcome(
            self.path, old_journal_key=self.old,
            new_journal_key=self.fresh,
            anchor_key=anchor or self.anchor, ticket=intent)

    def test_precomputed_all_scope_ticket_matches_committed_state(self):
        intent = self.plan()
        self.assertEqual((intent["before"]["accounts"],
                          intent["before"]["events"]), (3, 3))
        self.assertEqual((intent["after"]["accounts"],
                          intent["after"]["events"],
                          intent["after"]["epoch"]), (3, 3, 2))
        self.assertEqual(self.outcome(intent)["outcome"],
                         "OLD_STATE_AMBIGUOUS")
        result = self.execute(intent)
        self.assertTrue(result["syntheticRotationCommitted"])
        self.assertEqual(result["checkpointAwaitingExternalPromotion"],
                         intent["after"])
        self.assertEqual(self.outcome(intent)["outcome"],
                         "NEW_STATE_VERIFIED")
        self.assertTrue(self.outcome(intent)["operatorApprovalRequired"])
        self.assertTrue(attest.verify_synthetic_checkpoint(
            self.path, journal_key=self.fresh,
            anchor_key=self.anchor, pinned=intent["after"])[
                "checkpointVerified"])
        with self.assertRaises(attest.AttestedLatchDenied):
            attest.verify_synthetic_checkpoint(
                self.path, journal_key=self.old,
                anchor_key=self.anchor, pinned=self.pinned)
        state = latch.inspect_synthetic_policy(
            self.path, hmac_key=self.fresh,
            principal_user_id=self.a, account_id=self.x)
        self.assertTrue(state["durableSyntheticLatch"])
        self.assertEqual(state["worstHistoricalRealizedCents"], -14)

    def test_crash_before_commit_keeps_old_ambiguous_state(self):
        intent = self.plan()
        with self.assertRaises(ticket.RotationTicketDenied):
            self.execute(intent, fail=True)
        observed = self.outcome(intent)
        self.assertEqual(observed["outcome"], "OLD_STATE_AMBIGUOUS")
        self.assertTrue(observed["operatorApprovalRequired"])
        self.assertTrue(attest.verify_synthetic_checkpoint(
            self.path, journal_key=self.old,
            anchor_key=self.anchor, pinned=self.pinned)[
                "checkpointVerified"])
        self.assertTrue(self.execute(intent)["syntheticRotationCommitted"])

    def test_rollback_after_commit_remains_ambiguous_not_mislabeled_safe(self):
        intent = self.plan()
        shutil.copy2(self.path, self.backup)
        self.execute(intent)
        shutil.copy2(self.backup, self.path)
        # The ticket cannot distinguish a precommit crash from a rollback
        # of the committed state. Never automatically accept the old fixture.
        self.assertEqual(self.outcome(intent)["outcome"],
                         "OLD_STATE_AMBIGUOUS")
        self.assertTrue(self.outcome(intent)["operatorApprovalRequired"])

    def test_tampered_ticket_wrong_keys_and_untrusted_epoch_refused(self):
        intent = self.plan()
        for field, value in (
                ("protocol", "wrong"),
                ("intentMac", "0" * 64),
                ("after", dict(intent["after"], epoch=3)),
                ("before", dict(intent["before"], events=1)),
                ("unknown", True)):
            with self.subTest(field=field):
                changed = copy.deepcopy(intent)
                changed[field] = value
                with self.assertRaises(ticket.RotationTicketDenied):
                    self.execute(changed)
                with self.assertRaises(ticket.RotationTicketDenied):
                    self.outcome(changed)
        with self.assertRaises(ticket.RotationTicketDenied):
            self.plan(epoch=4)
        with self.assertRaises(ticket.RotationTicketDenied):
            self.plan(fresh=self.old)
        with self.assertRaises(ticket.RotationTicketDenied):
            self.plan(fresh=self.anchor)
        with self.assertRaises(ticket.RotationTicketDenied):
            self.execute(intent, fresh=os.urandom(32))
        with self.assertRaises(ticket.RotationTicketDenied):
            self.outcome(intent, anchor=os.urandom(32))
        self.assertEqual(self.outcome(intent)["outcome"],
                         "OLD_STATE_AMBIGUOUS")

    def test_ticket_roundtrip_and_stale_state_fail_closed(self):
        intent = json.loads(json.dumps(self.plan(), sort_keys=True))
        self.assertEqual(self.outcome(intent)["outcome"],
                         "OLD_STATE_AMBIGUOUS")
        self.record("REALIZE", 8, user=self.b, account=self.z)
        with self.assertRaises(ticket.RotationTicketDenied):
            self.execute(intent)
        with self.assertRaises(ticket.RotationTicketDenied):
            self.outcome(intent)
        with self.assertRaises(ticket.RotationTicketDenied):
            self.plan()

    def test_does_not_touch_broker_app_or_paper_ledger(self):
        root = Path(__file__).resolve().parents[1]
        for filename in ("app.py", "engine/tenant_paper_ledger.py"):
            contents = (root / filename).read_text()
            self.assertNotIn("tenant_paper_latch_rotation_ticket", contents)
            self.assertNotIn("execute_synthetic_prepared_rotation", contents)
        with tempfile.TemporaryDirectory() as ordinary:
            with self.assertRaises(ticket.RotationTicketDenied):
                ticket.prepare_synthetic_rotation_ticket(
                    Path(ordinary) / "other.db",
                    old_journal_key=self.old, new_journal_key=self.fresh,
                    anchor_key=self.anchor, pinned=self.pinned, new_epoch=2)


if __name__ == "__main__":
    unittest.main()
