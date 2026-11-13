"""v0.2.104: offline externally pinned operator evidence and recovery refusal."""
import copy
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid

from engine import tenant_paper_latch_rehearsal as latch
from engine import tenant_paper_latch_attestation as attest
from engine import tenant_paper_latch_rotation_ticket as rotation
from engine import tenant_paper_latch_operator_evidence as evidence


def ident():
    return str(uuid.uuid4())


class SyntheticOperatorEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(
            dir="/dev/shm", prefix="edgepilot-operator-evidence-v02104-")
        self.root = Path(self.folder.name)
        self.path = self.root / "fixture.db"
        self.old_copy = self.root / "prior.db"
        self.journal, self.fresh, self.anchor, self.operator = (
            os.urandom(32), os.urandom(32), os.urandom(32), os.urandom(32))
        self.user_a, self.user_b = ident(), ident()
        self.account_a, self.account_b, self.account_c = (
            ident(), ident(), ident())
        latch.create_synthetic_fixture(self.path)
        for user, account, threshold in (
                (self.user_a, self.account_a, 14),
                (self.user_a, self.account_b, 8),
                (self.user_b, self.account_c, 21)):
            latch.register_synthetic_policy(
                self.path, hmac_key=self.journal, principal_user_id=user,
                account_id=account, max_loss_cents=threshold)
        self.event("REALIZE", -14)
        self.event("OPEN")
        self.event("REALIZE", 35)
        self.event("REALIZE", -8, user=self.user_b, account=self.account_c)
        self.pin = self.checkpoint()
        self.records = []
        self.tip = evidence.genesis_tip()

    def tearDown(self):
        self.folder.cleanup()

    def checkpoint(self, *, key=None, epoch=1):
        return attest.make_synthetic_checkpoint(
            self.path, journal_key=key or self.journal,
            anchor_key=self.anchor, epoch=epoch)

    def event(self, kind, delta=0, *, key=None, user=None, account=None,
              request_id=None):
        return latch.rehearse_atomic_request(
            self.path, hmac_key=key or self.journal,
            principal_user_id=user or self.user_a,
            account_id=account or self.account_a,
            request_id=request_id or ident(), kind=kind,
            realized_delta_cents=delta)

    def propose(self, *, status="ACTIVE", pin=None, journal=None,
                ticket=None, next_key=None, revoked=(), reason="NONE",
                path=None, records=None, tip=None, operator=None):
        return evidence.propose_synthetic_operator_record(
            path or self.path,
            records=self.records if records is None else records,
            externally_trusted_tip=self.tip if tip is None else tip,
            operator_key=operator or self.operator,
            anchor_key=self.anchor, journal_key=journal or self.journal,
            checkpoint=self.pin if pin is None else pin, status=status,
            rotation_ticket=ticket, next_journal_key=next_key,
            newly_revoked_key_ids=revoked, quarantine_reason=reason)

    def publish(self, **kwargs):
        """Simulates independent publication; does NOT implement durable I/O."""
        proposal = self.propose(**kwargs)
        self.records.append(proposal["record"])
        self.tip = proposal["proposedLatestTip"]
        return proposal

    def inspect(self, *, path=None, journal=None, ticket=None,
                next_key=None, records=None, tip=None, operator=None):
        return evidence.inspect_synthetic_recovery_candidate(
            path or self.path,
            records=self.records if records is None else records,
            externally_trusted_tip=self.tip if tip is None else tip,
            operator_key=operator or self.operator, anchor_key=self.anchor,
            journal_key=journal or self.journal,
            rotation_ticket=ticket, next_journal_key=next_key)

    def prepare_rotation(self):
        return rotation.prepare_synthetic_rotation_ticket(
            self.path, old_journal_key=self.journal,
            new_journal_key=self.fresh, anchor_key=self.anchor,
            pinned=self.pin, new_epoch=2)

    def test_initial_pinned_state_and_sticky_historical_loss(self):
        self.publish()
        result = self.inspect()
        self.assertEqual(result["disposition"],
                         "PINNED_STATE_VERIFIED_NO_ACTIVATION")
        self.assertFalse(result["executionEnabled"])
        self.assertFalse(result["productionPaperFillsEnabled"])
        state = latch.inspect_synthetic_policy(
            self.path, hmac_key=self.journal,
            principal_user_id=self.user_a, account_id=self.account_a)
        self.assertTrue(state["durableSyntheticLatch"])
        self.assertEqual(state["worstHistoricalRealizedCents"], -14)
        self.assertEqual(state["currentRealizedCents"], 21)
        self.assertFalse(self.event("OPEN")["simulatedAccepted"])
        # The new OPEN is durable and changes the chain; an old pin cannot
        # silently be accepted merely because the monetary balance is equal.
        with self.assertRaises(evidence.OperatorRecoveryDenied):
            self.inspect()
        self.pin = self.checkpoint()
        self.publish()
        self.assertEqual(self.inspect()["evidenceSequence"], 2)
        with self.assertRaises(latch.PaperLatchDenied):
            latch.inspect_synthetic_policy(
                self.path, hmac_key=self.journal,
                principal_user_id=self.user_b, account_id=self.account_a)

    def test_old_file_and_stale_external_chain_refused(self):
        self.publish()
        shutil.copy2(self.path, self.old_copy)
        self.event("REALIZE", -2, user=self.user_b, account=self.account_c)
        self.pin = self.checkpoint()
        self.publish()
        self.assertEqual(self.inspect()["disposition"],
                         "PINNED_STATE_VERIFIED_NO_ACTIVATION")
        with self.assertRaises(evidence.OperatorRecoveryDenied):
            self.inspect(path=self.old_copy)
        with self.assertRaises(evidence.OperatorRecoveryDenied):
            self.inspect(records=self.records[:1])
        with self.assertRaises(evidence.OperatorRecoveryDenied):
            self.propose(records=self.records[:1])
        with self.assertRaises(evidence.OperatorRecoveryDenied):
            self.inspect(tip=self.records[0] and {
                "sequence": 1, "recordMac": self.records[0]["recordMac"]})
        self.assertTrue(evidence.verify_synthetic_operator_evidence(
            self.records, externally_trusted_tip=self.tip,
            operator_key=self.operator, anchor_key=self.anchor)[
                "evidenceVerified"])

    def test_pending_new_state_and_explicit_promotion(self):
        self.publish()
        ticket = self.prepare_rotation()
        self.publish(status="ROTATION_PENDING", ticket=ticket,
                     next_key=self.fresh)
        self.assertEqual(self.inspect(ticket=ticket, next_key=self.fresh)[
            "disposition"], "OLD_STATE_AMBIGUOUS_QUARANTINE")
        with self.assertRaises(evidence.OperatorRecoveryDenied):
            self.propose(status="ACTIVE", pin=ticket["after"],
                         journal=self.fresh, ticket=ticket)
        committed = rotation.execute_synthetic_prepared_rotation(
            self.path, old_journal_key=self.journal,
            new_journal_key=self.fresh, anchor_key=self.anchor,
            ticket=ticket)
        self.assertTrue(committed["syntheticRotationCommitted"])
        self.assertEqual(self.inspect(ticket=ticket, next_key=self.fresh)[
            "disposition"], "NEW_STATE_NEEDS_INDEPENDENT_PROMOTION")
        self.publish(status="ACTIVE", pin=ticket["after"],
                     journal=self.fresh, ticket=ticket)
        self.assertEqual(self.inspect(journal=self.fresh)["disposition"],
                         "PINNED_STATE_VERIFIED_NO_ACTIVATION")
        with self.assertRaises(evidence.OperatorRecoveryDenied):
            self.inspect(journal=self.journal)
        self.assertTrue(latch.inspect_synthetic_policy(
            self.path, hmac_key=self.fresh,
            principal_user_id=self.user_a, account_id=self.account_a)[
                "durableSyntheticLatch"])
        self.assertEqual(self.records[-1]["epoch"], 2)

    def test_crash_and_post_commit_rollback_old_state_never_auto_approved(self):
        self.publish()
        ticket = self.prepare_rotation()
        self.publish(status="ROTATION_PENDING", ticket=ticket,
                     next_key=self.fresh)
        shutil.copy2(self.path, self.old_copy)
        with self.assertRaises(rotation.RotationTicketDenied):
            rotation.execute_synthetic_prepared_rotation(
                self.path, old_journal_key=self.journal,
                new_journal_key=self.fresh, anchor_key=self.anchor,
                ticket=ticket, _fail_before_commit=True)
        self.assertEqual(self.inspect(ticket=ticket, next_key=self.fresh)[
            "disposition"], "OLD_STATE_AMBIGUOUS_QUARANTINE")
        rotation.execute_synthetic_prepared_rotation(
            self.path, old_journal_key=self.journal,
            new_journal_key=self.fresh, anchor_key=self.anchor, ticket=ticket)
        shutil.copy2(self.old_copy, self.path)
        self.assertEqual(self.inspect(ticket=ticket, next_key=self.fresh)[
            "disposition"], "OLD_STATE_AMBIGUOUS_QUARANTINE")
        with self.assertRaises(evidence.OperatorRecoveryDenied):
            self.propose(status="ACTIVE", pin=ticket["after"],
                         journal=self.fresh, ticket=ticket)
        self.publish(status="QUARANTINED", reason="AMBIGUOUS_OLD_STATE")
        self.assertEqual(self.inspect()["disposition"],
                         "QUARANTINED_NO_RESTORE")
        with self.assertRaises(evidence.OperatorRecoveryDenied):
            self.propose(status="ACTIVE")

    def test_compromised_key_quarantine_is_monotonic(self):
        self.publish()
        compromised = evidence.journal_key_id(self.journal)
        self.publish(status="QUARANTINED", reason="COMPROMISED_KEY",
                     revoked=[compromised])
        self.assertEqual(self.records[-1]["revokedKeyIds"], [compromised])
        self.assertEqual(self.inspect()["disposition"], "QUARANTINED_NO_RESTORE")
        with self.assertRaises(evidence.OperatorRecoveryDenied):
            self.propose(status="ACTIVE")
        with self.assertRaises(evidence.OperatorRecoveryDenied):
            self.propose(status="ROTATION_PENDING",
                         ticket=self.prepare_rotation(), next_key=self.fresh)

    def test_tamper_tip_wrong_key_and_malformed_evidence_refused(self):
        self.publish()
        changed = copy.deepcopy(self.records)
        changed[0]["checkpoint"]["events"] += 1
        for bad, tip, operator in (
                (changed, self.tip, self.operator),
                (self.records, {"sequence": 1, "recordMac": "0" * 64},
                 self.operator),
                (self.records, self.tip, os.urandom(32)),
                (self.records, evidence.genesis_tip(), self.operator)):
            with self.subTest():
                with self.assertRaises(evidence.OperatorRecoveryDenied):
                    self.inspect(records=bad, tip=tip, operator=operator)
        with self.assertRaises(evidence.OperatorRecoveryDenied):
            self.propose(operator=self.anchor)
        with self.assertRaises(evidence.OperatorRecoveryDenied):
            self.publish(status="ACTIVE", revoked=[
                evidence.journal_key_id(self.fresh)])
        self.assertEqual(len(self.records), 1)
        self.assertEqual(self.inspect()["disposition"],
                         "PINNED_STATE_VERIFIED_NO_ACTIVATION")

    def test_pending_ticket_mismatch_missing_keys_and_concurrent_event(self):
        self.publish()
        ticket = self.prepare_rotation()
        self.publish(status="ROTATION_PENDING", ticket=ticket,
                     next_key=self.fresh)
        for kwargs in ({}, {"ticket": ticket},
                       {"ticket": ticket, "next_key": os.urandom(32)}):
            with self.subTest(kwargs=list(kwargs)):
                with self.assertRaises(evidence.OperatorRecoveryDenied):
                    self.inspect(**kwargs)
        forged = copy.deepcopy(ticket)
        forged["after"]["events"] += 1
        with self.assertRaises(evidence.OperatorRecoveryDenied):
            self.inspect(ticket=forged, next_key=self.fresh)
        self.event("REALIZE", -1, user=self.user_b, account=self.account_c)
        with self.assertRaises(evidence.OperatorRecoveryDenied):
            self.inspect(ticket=ticket, next_key=self.fresh)
        with self.assertRaises(evidence.OperatorRecoveryDenied):
            self.propose(status="ACTIVE", pin=ticket["after"],
                         journal=self.fresh, ticket=ticket)

    def test_no_flask_paper_writer_or_normal_disk_access(self):
        root = Path(__file__).resolve().parents[1]
        for path in ("app.py", "engine/tenant_paper_ledger.py"):
            self.assertNotIn("tenant_paper_latch_operator_evidence",
                             (root / path).read_text())
        self.publish()
        with tempfile.TemporaryDirectory() as disk:
            with self.assertRaises(evidence.OperatorRecoveryDenied):
                self.inspect(path=Path(disk) / "invalid.db")
        self.assertFalse(self.inspect()["executionEnabled"])


if __name__ == "__main__":
    unittest.main()
