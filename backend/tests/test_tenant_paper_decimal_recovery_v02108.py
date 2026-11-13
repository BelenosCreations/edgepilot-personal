"""Recovery and encrypted restore with independent synthetic operator evidence."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import base64
import json
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
from engine import tenant_paper_decimal_recovery as recovery


class DecimalRecoveryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(dir="/dev/shm", prefix="decimal-recovery-test-")
        self.addCleanup(folder.cleanup)
        self.directory = Path(folder.name)
        self.original = self.directory / "original.db"
        self.candidate = self.directory / "candidate.db"
        self.restored = self.directory / "restored.db"
        self.journal, self.anchor, self.operator, self.replacement = (
            os.urandom(32) for _ in range(4))
        self.archive_key = Fernet.generate_key()
        self.scopes = [(str(uuid4()), str(uuid4())) for _ in range(3)]
        self.keys = dict(journal_key=self.journal, anchor_key=self.anchor, operator_key=self.operator)
        ledger.create_decimal_fixture(self.original)
        for user, account in self.scopes:
            self.register(self.original, user, account)

    def register(self, path, user, account, *, max_loss_cents=14):
        ledger.register_decimal_account(
            path, hmac_key=self.journal, principal_user_id=user, account_id=account,
            initial_cash_cents=10000, protected_pct=90, spend_cap_cents=2000,
            per_trade_cap_cents=800, max_loss_cents=max_loss_cents)

    def trade(self, path, *, side="BUY", symbol="TEST", qty="0.125",
              price="2.03", key=None, request=None):
        user, account = self.scopes[0]
        return ledger.decimal_fill(
            path, hmac_key=self.journal if key is None else key,
            principal_user_id=user, account_id=account, request_id=request or str(uuid4()),
            side=side, asset_class="stock", symbol=symbol, quantity=qty, assumed_unit_price=price)

    def establish(self):
        return recovery.establish_decimal_recovery(self.original, **self.keys)

    def evidence(self, record, **overrides):
        # Independent fixture witness for these tests. The app has no access.
        return dict(self.keys, record=record, trusted_tip=recovery.evidence_tip(record)) | overrides

    def prepare_advance(self, record, **overrides):
        return recovery.prepare_decimal_advance(
            self.original, self.candidate, **self.evidence(record, **overrides))

    def prepare_rotation(self, record, replacement=None):
        return recovery.prepare_decimal_rotation(
            self.original, replacement_key=replacement or self.replacement,
            **self.evidence(record))

    def inspect(self, path, record, **overrides):
        return recovery.inspect_decimal_recovery(path, **self.evidence(record, **overrides))

    def seal(self, path, record, **overrides):
        return archive.seal_decimal_archive(
            path, **self.evidence(record, archive_key=self.archive_key, **overrides))

    def approval(self, token, record, destination=None):
        return archive.approve_decimal_restore(
            token, destination or self.restored, record=record,
            trusted_tip=recovery.evidence_tip(record), operator_key=self.operator)

    def restore(self, token, approval, record, **overrides):
        return archive.restore_decimal_archive(
            token, self.restored, approval=approval,
            **self.evidence(record, archive_key=self.archive_key, **overrides))

    def test_advancement_requires_prepared_tip_and_exact_explicit_promotion(self):
        record = self.establish()
        shutil.copy2(self.original, self.candidate)
        self.trade(self.candidate)
        pending = self.prepare_advance(record)
        self.assertEqual(pending["previousMac"], record["mac"])
        self.assertEqual(pending["target"]["epoch"], 2)
        self.assertEqual(self.inspect(self.original, record), "PINNED_ACTIVE")
        self.assertEqual(self.inspect(self.original, pending), "AMBIGUOUS_OLD_STATE")
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.inspect(self.original, record, trusted_tip=recovery.evidence_tip(pending))
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            recovery.approve_decimal_promotion(self.original, **self.evidence(pending))
        self.assertEqual(self.inspect(self.candidate, pending),
                         "PREPARED_TARGET_REQUIRES_APPROVAL")
        promoted = recovery.approve_decimal_promotion(self.candidate, **self.evidence(pending))
        self.assertEqual(self.inspect(self.candidate, promoted), "PINNED_ACTIVE")
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.inspect(self.original, promoted)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.inspect(self.candidate, pending, trusted_tip=recovery.evidence_tip(promoted))

    def test_advance_refuses_divergent_prefix_even_when_count_increases(self):
        shutil.copy2(self.original, self.candidate)
        self.trade(self.original)
        record = self.establish()
        self.trade(self.candidate, qty="0.126")
        self.trade(self.candidate)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.prepare_advance(record)

    def test_advance_refuses_removed_scope_or_rewritten_empty_policy(self):
        record = self.establish()
        shutil.copy2(self.original, self.candidate)
        with sqlite3.connect(self.candidate) as db:
            db.execute("DELETE FROM decimal_wallets WHERE user_id=? AND account_id=?",
                       self.scopes[1])
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.prepare_advance(record)
        self.register(self.candidate, *self.scopes[1], max_loss_cents=30)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.prepare_advance(record)

    def test_rotation_interruption_and_rollback_remain_ambiguous(self):
        self.trade(self.original)
        record = self.establish()
        original_bytes = self.original.read_bytes()
        pending = self.prepare_rotation(record)
        self.assertEqual(self.original.read_bytes(), original_bytes)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            recovery.execute_prepared_decimal_rotation(
                self.original, replacement_key=self.replacement,
                **self.evidence(pending, trusted_tip=recovery.evidence_tip(record)))
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            recovery.execute_prepared_decimal_rotation(
                self.original, replacement_key=self.replacement,
                _interrupt_before_commit=True, **self.evidence(pending))
        self.assertEqual(self.original.read_bytes(), original_bytes)
        self.assertEqual(self.inspect(self.original, pending), "AMBIGUOUS_OLD_STATE")
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            recovery.approve_decimal_promotion(self.original, **self.evidence(pending))
        recovery.execute_prepared_decimal_rotation(
            self.original, replacement_key=self.replacement, **self.evidence(pending))
        self.assertEqual(self.inspect(self.original, pending, journal_key=self.replacement),
                         "PREPARED_TARGET_REQUIRES_APPROVAL")
        self.candidate.write_bytes(original_bytes)
        self.candidate.chmod(0o600)
        self.assertEqual(self.inspect(self.candidate, pending), "AMBIGUOUS_OLD_STATE")

    def test_rotation_and_archive_preserve_sticky_loss_and_request_idempotency(self):
        request = str(uuid4())
        first = self.trade(self.original, request=request)
        self.trade(self.original, symbol="GAIN", price="1.00")
        self.trade(self.original, side="SELL", price="0.96")  # 12c received against 26c basis.
        self.trade(self.original, side="SELL", symbol="GAIN", price="4.00")
        record = self.establish()
        pending = self.prepare_rotation(record)
        recovery.execute_prepared_decimal_rotation(
            self.original, replacement_key=self.replacement, **self.evidence(pending))
        active = recovery.approve_decimal_promotion(
            self.original, **self.evidence(pending, journal_key=self.replacement))
        self.assertEqual(active["retiredKeyIds"], [record["current"]["journalKeyId"]])
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            recovery.prepare_decimal_rotation(
                self.original, replacement_key=self.journal + b"\x00",
                **self.evidence(active, journal_key=self.replacement))
        token = self.seal(self.original, active, journal_key=self.replacement)
        self.restore(token, self.approval(token, active), active, journal_key=self.replacement)
        user, account = self.scopes[0]
        state = ledger.inspect_decimal_account(
            self.restored, hmac_key=self.replacement, principal_user_id=user, account_id=account)
        self.assertEqual(state["realizedCents"], 23)
        self.assertEqual(state["worstRealizedCents"], -14)
        self.assertTrue(state["stopped"])
        replay = self.trade(self.restored, request=request, key=self.replacement)
        self.assertEqual(replay["originalCashAfterCents"], first["cashCents"])
        self.assertTrue(replay["stopped"])
        with self.assertRaises(ledger.DecimalAtomicDenied):
            self.trade(self.restored, key=self.replacement)
        with self.assertRaises(ledger.DecimalAtomicDenied):
            self.trade(self.restored, request=request, qty="0.126", key=self.replacement)

    def test_quarantine_blocks_old_signed_evidence_and_all_restore_paths(self):
        record = self.establish()
        pending = self.prepare_rotation(record)
        token = self.seal(self.original, record)
        approval = self.approval(token, record)
        hold = recovery.quarantine_decimal_recovery(
            record=pending, trusted_tip=recovery.evidence_tip(pending),
            operator_key=self.operator, reason="COMPROMISED_KEY")
        self.assertEqual(set(hold["retiredKeyIds"]), {
            record["current"]["journalKeyId"], pending["target"]["journalKeyId"]})
        self.assertEqual(self.inspect(self.original, hold), "QUARANTINED")
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.restore(token, approval, record, trusted_tip=recovery.evidence_tip(hold))
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.approval(token, hold)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.prepare_rotation(hold)

    def test_archive_refuses_stale_backup_even_with_fresh_approval(self):
        record = self.establish()
        old = self.seal(self.original, record)
        shutil.copy2(self.original, self.candidate)
        self.trade(self.candidate)
        pending = self.prepare_advance(record)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.approval(old, pending)
        active = recovery.approve_decimal_promotion(self.candidate, **self.evidence(pending))
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.restore(old, self.approval(old, active), active)
        self.assertFalse(self.restored.exists())

    def test_archive_approval_binds_operator_tip_ciphertext_and_destination(self):
        active = json.loads(json.dumps(self.establish(), sort_keys=True))
        token = self.seal(self.original, active)
        approval = self.approval(token, active)
        for candidate, supplied, overrides in (
            (token, None, {}),
            (token + b"a", approval, {}),
            (token, self.approval(token, active, self.directory / "elsewhere.db"), {}),
            (token, approval, {"operator_key": os.urandom(32)}),
            (token, approval, {"trusted_tip": {"sequence": 1, "mac": "0" * 64}}),
        ):
            with self.subTest(overrides=overrides.keys()), self.assertRaises(recovery.DecimalRecoveryDenied):
                self.restore(candidate, supplied, active, **overrides)
        tampered = deepcopy(active)
        tampered["current"]["epoch"] += 1
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.approval(token, tampered)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            archive.seal_decimal_archive(
                self.original, archive_key=base64.urlsafe_b64encode(self.operator),
                **self.evidence(active))

    def test_archive_publish_interruption_race_and_private_cleanup(self):
        record = self.establish()
        token = self.seal(self.original, record)
        approval = self.approval(token, record)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.restore(token, approval, record, _interrupt_before_publish=True)
        self.assertEqual(list(self.directory.iterdir()), [self.original])

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(self.restore, token, approval, record) for _ in range(2)]
        self.assertEqual(sum(result.exception() is None for result in results), 1)
        self.assertEqual(self.restored.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.restored.stat().st_nlink, 1)
        self.assertEqual(self.inspect(self.restored, record), "PINNED_ACTIVE")

    def test_archive_refuses_schema_injection_and_post_link_interruption(self):
        record = self.establish()
        token = self.seal(self.original, record)
        shutil.copy2(self.original, self.candidate)
        with sqlite3.connect(self.candidate) as db:
            db.execute("CREATE INDEX unexpected ON decimal_events(seq)")
        cipher = Fernet(self.archive_key)
        forged = cipher.encrypt(archive._MAGIC + self.candidate.read_bytes())
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.restore(forged, self.approval(forged, record), record)
        self.assertFalse(self.restored.exists())

        real_link = os.link

        def simulate_process_loss(stage, target):
            real_link(stage, target)
            # Keep an extra hardlink to model a process that died before cleanup.
            real_link(stage, self.directory / "abandoned-stage.db")
            raise OSError("simulated interruption after link")

        with patch.object(archive.os, "link", side_effect=simulate_process_loss):
            with self.assertRaises(recovery.DecimalRecoveryDenied):
                self.restore(token, self.approval(token, record), record)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.inspect(self.restored, record)

    def test_fixture_rejects_unsafe_path_and_sidecar(self):
        record = self.establish()
        token = self.seal(self.original, record)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.approval(token, record, Path("/tmp/edgepilot-not-allowed.db"))
        approval = self.approval(token, record)
        Path(str(self.restored) + "-journal").symlink_to(self.original)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.restore(token, approval, record)

    def test_recovery_refuses_sidecar_without_opening_the_database(self):
        record = self.establish()
        sidecar = Path(str(self.original) + "-journal")
        sidecar.write_bytes(b"interrupted synthetic write")
        before = self.original.read_bytes()
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.inspect(self.original, record)
        with self.assertRaises(recovery.DecimalRecoveryDenied):
            self.seal(self.original, record)
        self.assertEqual(self.original.read_bytes(), before)
        self.assertEqual(sidecar.read_bytes(), b"interrupted synthetic write")

    def test_recovery_is_absent_from_runtime_imports(self):
        backend = Path(__file__).resolve().parents[1]
        runtime = [backend / "app.py", *sorted((backend / "engine").glob("*.py"))]
        custody = backend / "engine" / "tenant_paper_decimal_custody.py"
        offline = {Path(recovery.__file__), Path(archive.__file__), custody}
        for path in set(runtime) - offline:
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("tenant_paper_decimal_recovery", content)
            self.assertNotIn("tenant_paper_decimal_archive", content)
            self.assertNotIn("tenant_paper_decimal_custody", content)
