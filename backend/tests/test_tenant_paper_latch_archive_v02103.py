"""v0.2.103 — encrypted offline-only synthetic loss-stop archive tests."""
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile
import unittest
import uuid

from cryptography.fernet import Fernet

from engine import tenant_paper_latch_rehearsal as latch
from engine import tenant_paper_latch_attestation as attest
from engine import tenant_paper_latch_archive as archive


def ident():
    return str(uuid.uuid4())


class OfflineSyntheticLatchArchiveTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(
            dir="/dev/shm", prefix="edgepilot-latch-archive-v02103-")
        self.root = Path(self.scratch.name)
        self.source = self.root / "source.db"
        self.destination = self.root / "restored.db"
        self.old_backup = self.root / "old.db"
        self.journal = os.urandom(32)
        self.anchor = os.urandom(32)
        self.cipher = Fernet.generate_key()
        self.other_cipher = Fernet.generate_key()
        self.user1, self.user2 = ident(), ident()
        self.account1, self.account2, self.account3 = (
            ident(), ident(), ident())
        latch.create_synthetic_fixture(self.source)
        for user, account, limit in (
                (self.user1, self.account1, 14),
                (self.user1, self.account2, 7),
                (self.user2, self.account3, 25)):
            latch.register_synthetic_policy(
                self.source, hmac_key=self.journal,
                principal_user_id=user, account_id=account,
                max_loss_cents=limit)
        self.pin = self.checkpoint()

    def tearDown(self):
        self.scratch.cleanup()

    def checkpoint(self, *, journal=None, epoch=1):
        return attest.make_synthetic_checkpoint(
            self.source, journal_key=journal or self.journal,
            anchor_key=self.anchor, epoch=epoch)

    def event(self, kind, delta=0, *, user=None, account=None, key=None):
        return latch.rehearse_atomic_request(
            self.source, hmac_key=key or self.journal,
            principal_user_id=user or self.user1,
            account_id=account or self.account1,
            request_id=ident(), kind=kind, realized_delta_cents=delta)

    def seal(self, *, pin=None, key=None, journal=None, source=None):
        return archive.seal_synthetic_latch_archive(
            source or self.source, journal_key=journal or self.journal,
            anchor_key=self.anchor, archive_key=key or self.cipher,
            trusted_checkpoint=pin if pin is not None else self.pin)

    def restore(self, token, *, dest=None, pin=None, key=None, journal=None,
                fail=False):
        return archive.restore_synthetic_latch_archive(
            token, dest or self.destination,
            journal_key=journal or self.journal, anchor_key=self.anchor,
            archive_key=key or self.cipher,
            trusted_checkpoint=pin if pin is not None else self.pin,
            _fail_before_publish=fail)

    def test_encrypted_roundtrip_preserves_all_scopes_and_latch(self):
        self.event("REALIZE", -14)
        self.event("OPEN")
        self.event("REALIZE", 42)
        self.event("OPEN", account=self.account2)
        self.event("REALIZE", -7, user=self.user2, account=self.account3)
        self.pin = self.checkpoint()
        token = self.seal()
        self.assertIsInstance(token, bytes)
        self.assertNotIn(b"SQLite format 3", token)
        self.assertNotIn(self.user1.encode(), token)
        self.assertNotIn(self.user2.encode(), token)
        self.assertEqual(self.restore(token), self.destination)
        info = self.destination.stat()
        self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
        self.assertEqual(info.st_nlink, 1)
        self.assertTrue(attest.verify_synthetic_checkpoint(
            self.destination, journal_key=self.journal,
            anchor_key=self.anchor, pinned=self.pin)[
                "checkpointVerified"])
        state = latch.inspect_synthetic_policy(
            self.destination, hmac_key=self.journal,
            principal_user_id=self.user1, account_id=self.account1)
        self.assertTrue(state["durableSyntheticLatch"])
        self.assertEqual(state["worstHistoricalRealizedCents"], -14)
        self.assertEqual(state["currentRealizedCents"], 28)
        self.assertFalse(latch.rehearse_atomic_request(
            self.destination, hmac_key=self.journal,
            principal_user_id=self.user1, account_id=self.account1,
            request_id=ident(), kind="OPEN")["simulatedAccepted"])
        self.assertFalse(latch.inspect_synthetic_policy(
            self.destination, hmac_key=self.journal,
            principal_user_id=self.user1, account_id=self.account2)[
                "durableSyntheticLatch"])
        with self.assertRaises(latch.PaperLatchDenied):
            latch.inspect_synthetic_policy(
                self.destination, hmac_key=self.journal,
                principal_user_id=self.user2, account_id=self.account1)

    def test_wrong_keys_and_tampered_ciphertext_fail_before_publication(self):
        token = self.seal()
        for damaged, key in (
                (token, self.other_cipher),
                (token[:-6] + b"broken", self.cipher),
                (b"invalid", self.cipher),
                (b"", self.cipher),
                (token, os.urandom(32)),
                (token, None)):
            with self.subTest(token=damaged == token,
                              key_length=len(key or b"")):
                if key is None:
                    # Caller-supplied nonbytes and missing key must fail.
                    with self.assertRaises(archive.SyntheticLatchArchiveDenied):
                        self.restore(damaged, key="invalid")
                else:
                    with self.assertRaises(archive.SyntheticLatchArchiveDenied):
                        self.restore(damaged, key=key)
                self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.root.glob(".edgepilot-latch-restore-*")), [])

    def test_prior_encrypted_snapshot_rejected_by_latest_external_pin(self):
        self.event("REALIZE", -7)
        old_pin = self.checkpoint()
        old_token = self.seal(pin=old_pin)
        self.event("REALIZE", -7)
        latest_pin = self.checkpoint()
        with self.assertRaises(archive.SyntheticLatchArchiveDenied):
            self.restore(old_token, pin=latest_pin)
        self.assertFalse(self.destination.exists())
        self.assertTrue(self.restore(old_token, pin=old_pin).exists())
        # The caller MUST provide an actual independently trusted latest pin.
        self.assertFalse(latch.inspect_synthetic_policy(
            self.destination, hmac_key=self.journal,
            principal_user_id=self.user1, account_id=self.account1)[
                "durableSyntheticLatch"])

    def test_missing_account_and_signed_event_tamper_cannot_be_sealed(self):
        with sqlite3.connect(self.source) as db:
            db.execute("""DELETE FROM offline_latch_policies
                WHERE user_id=? AND account_id=?""",
                (self.user2, self.account3))
        with self.assertRaises(archive.SyntheticLatchArchiveDenied):
            self.seal()
        self.assertEqual(list(self.root.glob(".edgepilot-latch-seal-*")), [])
        with sqlite3.connect(self.source) as db:
            db.execute("""INSERT INTO offline_latch_policies
                (user_id, account_id,max_loss_cents,current_cents,worst_cents,
                 latched,seq,last_mac,policy_mac)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (self.user2,self.account3,25,0,0,0,0,latch._GENESIS,
                 latch._mac(self.journal,"POLICY",self.user2,self.account3,25)))
        self.event("REALIZE", -2)
        self.pin = self.checkpoint()
        with sqlite3.connect(self.source) as db:
            db.execute("""UPDATE offline_latch_journal SET delta_cents=-3
                WHERE user_id=? AND account_id=?""",
                (self.user1, self.account1))
        with self.assertRaises(archive.SyntheticLatchArchiveDenied):
            self.seal()

    def test_no_overwrite_or_partial_publication_across_failure(self):
        token = self.seal()
        self.destination.write_bytes(b"preexisting")
        with self.assertRaises(archive.SyntheticLatchArchiveDenied):
            self.restore(token)
        self.assertEqual(self.destination.read_bytes(), b"preexisting")
        self.destination.unlink()
        with self.assertRaises(archive.SyntheticLatchArchiveDenied):
            self.restore(token, fail=True)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.root.glob(".edgepilot-latch-restore-*")), [])
        self.restore(token)
        with self.assertRaises(archive.SyntheticLatchArchiveDenied):
            self.restore(token)
        self.assertEqual(stat.S_IMODE(self.destination.stat().st_mode), 0o600)

    def test_malformed_but_encrypted_payload_is_refused(self):
        for body in (
                b"not sqlite",
                b"SQLite format 3\x00" + b"x" * 128,
                b"SQLite format 3\x00" + b"x" * 128 + b"extraneous",
        ):
            with self.subTest(size=len(body)):
                token = Fernet(self.cipher).encrypt(archive._MAGIC + body)
                with self.assertRaises(archive.SyntheticLatchArchiveDenied):
                    self.restore(token)
                self.assertFalse(self.destination.exists())
        # A correctly authenticated archive using the wrong latest pin fails.
        token = self.seal()
        stale = dict(self.pin, epoch=2)
        with self.assertRaises(archive.SyntheticLatchArchiveDenied):
            self.restore(token, pin=stale)

    def test_rotated_key_requires_rotated_checkpoint_to_recover(self):
        old_token = self.seal()
        fresh_key = os.urandom(32)
        new_pin = attest.rotate_synthetic_journal_key(
            self.source, old_journal_key=self.journal,
            new_journal_key=fresh_key, anchor_key=self.anchor,
            pinned=self.pin, new_epoch=2)
        new_token = self.seal(
            pin=new_pin, journal=fresh_key)
        with self.assertRaises(archive.SyntheticLatchArchiveDenied):
            self.restore(old_token, pin=new_pin, journal=fresh_key)
        with self.assertRaises(archive.SyntheticLatchArchiveDenied):
            self.restore(new_token, pin=self.pin)
        self.restore(new_token, pin=new_pin, journal=fresh_key)
        self.assertEqual(self.checkpoint(journal=fresh_key,epoch=2),new_pin)

    def test_no_production_access_and_tmpfs_gate(self):
        source = (Path(__file__).resolve().parents[1] / "app.py").read_text()
        writer = (Path(__file__).resolve().parents[1] /
                  "engine" / "tenant_paper_ledger.py").read_text()
        self.assertNotIn("tenant_paper_latch_archive", source)
        self.assertNotIn("tenant_paper_latch_archive", writer)
        with tempfile.TemporaryDirectory() as elsewhere:
            ordinary = Path(elsewhere)
            with self.assertRaises(archive.SyntheticLatchArchiveDenied):
                self.restore(self.seal(), dest=ordinary / "no.db")
            with self.assertRaises(archive.SyntheticLatchArchiveDenied):
                self.seal(source=ordinary / "no.db")
        self.assertEqual(list(self.root.glob(".edgepilot-latch-restore-*")), [])


if __name__ == "__main__":
    unittest.main()
