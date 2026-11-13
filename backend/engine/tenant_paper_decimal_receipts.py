"""Independent receipt storage for the offline synthetic Decimal rehearsal."""
from contextlib import closing, contextmanager, ExitStack, nullcontext
import fcntl
import hmac
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
from urllib.parse import quote

from . import tenant_paper_decimal_archive as archive
from . import tenant_paper_decimal_atomic_rehearsal as ledger
from . import tenant_paper_decimal_custody as custody
from . import tenant_paper_decimal_recovery as recovery


_PROTOCOL = "EDGEPILOT-SYNTHETIC-DECIMAL-RECEIPT-v1"
_PROMOTION_PROTOCOL = "EDGEPILOT-SYNTHETIC-DECIMAL-PROMOTION-CHECKPOINT-v1"
_EXPORT_PROTOCOL = "EDGEPILOT-SYNTHETIC-DECIMAL-PROMOTION-EXPORT-v1"
_RECOVERY_PROTOCOL = "EDGEPILOT-SYNTHETIC-DECIMAL-RECOVERY-RECEIPT-v1"
_SIDECARS = ("-journal", "-wal", "-shm")
_CHECKPOINT_STAGE_PREFIX = ".edgepilot-checkpoint-"
_TERMINAL_STAGE_PREFIX = ".decimal-terminal-receipt-"
_SCHEMA = """CREATE TABLE retained_receipt (
    id INTEGER PRIMARY KEY CHECK (id = 1), number INTEGER NOT NULL,
    tip TEXT NOT NULL, pending INTEGER NOT NULL, signature TEXT NOT NULL)"""


class DecimalReceiptStore:
    """A separately operated receipt pin and persistent rotation reservation."""

    def __init__(self, path, *, receipt_key, _protocol=_PROTOCOL):
        self.path = Path(path)
        self.key = ledger._key(receipt_key)
        self._protocol = _protocol

    def _check_directory(self):
        parent = self.path.parent
        info = parent.stat()
        if (parent != parent.resolve(strict=True) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            recovery._deny()

    def _verify_separation(self, witness, *keys):
        recovery._keys(self.key, witness.custody_key, witness.operator_key, *keys)
        if self.path.parent == witness.path.parent:
            recovery._deny()

    @classmethod
    def create(cls, path, *, receipt_key, witness, genesis):
        """Provision only at a verified new witness genesis."""
        store = cls(path, receipt_key=receipt_key)
        store._verify_separation(witness)
        with witness._open(write=False) as db:
            _, receipt, _ = witness._read(db, genesis, exact=True)
            if receipt["number"] != 1:
                recovery._deny()
            store._initialize(receipt)
        return store

    def _initialize(self, receipt):
        try:
            self._check_directory()
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            with closing(sqlite3.connect(self.path, isolation_level=None)) as pins:
                pins.execute("PRAGMA synchronous=EXTRA")
                pins.execute("BEGIN IMMEDIATE")
                pins.execute(_SCHEMA)
                self._save(pins, receipt, pending=False)
                pins.commit()
            fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except (OSError, sqlite3.Error, recovery.DecimalRecoveryDenied):
            recovery._deny()

    @contextmanager
    def _open(self, *, read_only=False):
        try:
            self._check_directory()
            info = self.path.lstat()
            if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_uid != os.getuid() or info.st_nlink not in (
                        (1, 2) if read_only else (1,))):
                recovery._deny()
            if read_only:
                if any(os.path.lexists(str(self.path) + suffix) for suffix in _SIDECARS):
                    recovery._deny()
                with self.path.open("rb") as source:
                    if source.read(20)[18:20] != b"\x01\x01":
                        recovery._deny()
            uri = "file:" + quote(str(self.path), safe="/") + ("?mode=ro" if read_only else "?mode=rw")
            with closing(sqlite3.connect(uri, uri=True, isolation_level=None)) as db:
                db.execute("PRAGMA trusted_schema=OFF")
                if not read_only:
                    db.execute("PRAGMA synchronous=EXTRA")
                db.execute("BEGIN" if read_only else "BEGIN IMMEDIATE")
                if (db.execute("PRAGMA journal_mode").fetchone() != ("delete",)
                        or db.execute("SELECT sql FROM sqlite_master "
                                      "WHERE name NOT LIKE 'sqlite_%'").fetchall() != [(_SCHEMA,)]):
                    recovery._deny()
                yield db
        except (OSError, sqlite3.Error, recovery.DecimalRecoveryDenied):
            recovery._deny()

    def _signature(self, number, tip, pending):
        return ledger._mac(self.key, self._protocol, number, tip, pending)

    def _save(self, db, receipt, *, pending):
        number, tip = receipt["number"], receipt["mac"]
        reserved = int(pending)
        db.execute("INSERT OR REPLACE INTO retained_receipt VALUES (1,?,?,?,?)",
                   (number, tip, reserved, self._signature(number, tip, reserved)))

    def _read_state(self, db):
        row = db.execute("SELECT number,tip,pending,signature FROM retained_receipt WHERE id=1"
                         ).fetchone()
        if row is None:
            recovery._deny()
        number, tip, reserved, signature = row
        if (type(number) is not int or number < 1 or type(tip) is not str or len(tip) != 64
                or reserved not in (0, 1) or type(signature) is not str or not signature.isascii()
                or not hmac.compare_digest(signature, self._signature(number, tip, reserved))):
            recovery._deny()
        return {"number": number, "mac": tip}, bool(reserved)

    def _read(self, db, *, pending):
        receipt, reserved = self._read_state(db)
        if reserved != pending:
            recovery._deny()
        return receipt

    @contextmanager
    def _pin(self, expected=None):
        with self._open() as db:
            current = self._read(db, pending=False)
            if expected is not None and current != expected:
                recovery._deny()
            yield current

    def latest(self):
        """Return the retained receipt only when no handoff is unresolved."""
        with self._pin() as current:
            return current

    @contextmanager
    def _read_published(self, receipt):
        try:
            before = self.path.lstat()
            with self._open(read_only=True) as db:
                if self._read(db, pending=False) != receipt:
                    recovery._deny()
                after = self.path.lstat()
                if (not os.path.samestat(before, after) or before.st_ctime_ns != after.st_ctime_ns
                        or before.st_nlink != after.st_nlink):
                    recovery._deny()
                yield after
        except OSError:
            recovery._deny()

    @contextmanager
    def _lock_staging_directory(self):
        self._check_directory()
        fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                recovery._deny()
            # Cleanup takes this lock before the evidence locks. Refuse an active
            # publisher immediately, even while it holds those evidence locks.
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield fd
        finally:
            os.close(fd)

    def publish(self, witness, proposed):
        """Reserve before publishing a record and retain only its exact successor."""
        self._verify_separation(witness)
        with self._open() as db, witness._open(write=False) as journal:
            expected = self._read(db, pending=False)
            current, _, claimed = witness._read(journal, expected, exact=True)
            witness._verify_record(proposed)
            custody._check_transition(current, proposed, claimed)
            self._save(db, expected, pending=True)
            db.commit()
        published = witness.publish(proposed, expected_receipt=expected)
        with self._open() as db, witness._open(write=False) as journal:
            current = self._read(db, pending=True)
            actual, tip, _ = witness._read(journal, published, exact=True)
            if current != expected or actual != proposed or tip["number"] != current["number"] + 1:
                recovery._deny()
            self._save(db, tip, pending=False)
            db.commit()
            return tip

    def quarantine_frozen(self, witness, *, reserved_receipt, observed_receipt,
                          operator_record):
        """Resolve a frozen handoff with explicitly signed terminal quarantine.

        The operator supplies both receipts from independent review. This can
        publish a new quarantine or retain an already-published quarantine
        after a lost reply. It never resumes the interrupted operation.
        """
        self._verify_separation(witness)
        with self._open() as db, witness._open(write=True) as journal:
            reserved = self._read(db, pending=True)
            if reserved != reserved_receipt:
                recovery._deny()
            # Verify the reserved ancestor and require the separately reviewed
            # observed tip to be the exact current witness state.
            witness._read(journal, reserved, exact=False)
            record, tip, claimed = witness._read(journal, observed_receipt, exact=True)
            witness._verify_record(operator_record)
            if operator_record["status"] != "QUARANTINED":
                recovery._deny()
            if record["status"] == "QUARANTINED":
                if record != operator_record:
                    recovery._deny()
            else:
                custody._check_transition(record, operator_record, claimed)
                tip = witness._append(journal, tip, "record", operator_record)
                journal.commit()
            self._save(db, tip, pending=False)
            db.commit()
            return tip

    def promote_frozen(self, witness, path, *, reserved_receipt, prepared_receipt,
                       operator_record, journal_key, anchor_key, checkpoint=None):
        """Retain an explicitly approved prepared target without writing the ledger.

        Both receipts come from independent review. An exact committed promotion
        can be acknowledged after a lost reply, with the same target reaudited.
        An independent checkpoint can pin the promotion before local retention.
        """
        self._verify_separation(witness, journal_key, anchor_key)
        if checkpoint is not None:
            checkpoint._verify_separation(self, witness, journal_key, anchor_key)
        with ExitStack() as locks:
            external = None
            if checkpoint is not None:
                external = locks.enter_context(checkpoint._store._open())
            db = locks.enter_context(self._open())
            journal = locks.enter_context(witness._open(write=True))
            retained, pending = self._read_state(db)
            witness._read(journal, reserved_receipt, exact=False)
            record, tip, claimed = witness._read(journal, prepared_receipt, exact=False)
            if prepared_receipt["number"] not in (reserved_receipt["number"],
                                                  reserved_receipt["number"] + 1):
                recovery._deny()
            witness._verify_record(operator_record)
            if operator_record["status"] != "ACTIVE":
                recovery._deny()
            number, _, _, _, mac = witness._next_event(prepared_receipt, "record", operator_record)
            promoted = {"number": number, "mac": mac}
            anchored = None
            if checkpoint is not None:
                anchored = checkpoint._store._read(external, pending=False)
                if (anchored not in (prepared_receipt, promoted)
                        or (anchored == promoted and tip != promoted)):
                    recovery._deny()
            if pending:
                if retained != reserved_receipt:
                    recovery._deny()
            elif anchored != promoted or retained != promoted:
                recovery._deny()
            publish = tip == prepared_receipt
            if publish:
                custody._check_transition(record, operator_record, claimed)
            elif tip != promoted or record != operator_record:
                recovery._deny()

            source = recovery._source(path)
            with (witness._hold_original(source) as same_ledger,
                  witness._hold_original(witness.path) as same_witness,
                  recovery._fixture(source) as candidate):
                recovery._require_checkpoint(candidate, journal_key, anchor_key,
                                             operator_record["current"])
                if not same_ledger() or not same_witness():
                    recovery._deny()
                if publish:
                    tip = witness._append(journal, tip, "record", operator_record)
                    journal.commit()
                with witness._open(write=False) as readback:
                    witness._read(readback, tip, exact=True)
                    if not same_ledger() or not same_witness():
                        recovery._deny()
                    if checkpoint is not None and anchored == prepared_receipt:
                        checkpoint._store._save(external, tip, pending=False)
                        external.commit()
                    if pending:
                        self._save(db, tip, pending=False)
                        db.commit()
                return tip

    def _retain_claim(self, expected, claim):
        with self._open() as db:
            current = self._read(db, pending=True)
            if current != expected or claim["number"] != current["number"] + 1:
                recovery._deny()
            self._save(db, claim, pending=False)
            db.commit()
            return claim

    def rotate(self, witness, path, *, journal_key, replacement_key, anchor_key):
        """Reserve before the witness write and pin its claim through the ledger write."""
        self._verify_separation(witness, journal_key, replacement_key, anchor_key)
        with self._open() as db, witness._open(write=False) as journal:
            expected = self._read(db, pending=False)
            witness._rotation_plan(journal, expected, journal_key, replacement_key, anchor_key)
            self._save(db, expected, pending=True)
            db.commit()
        return witness.rotate(
            path, expected_receipt=expected, journal_key=journal_key,
            replacement_key=replacement_key, anchor_key=anchor_key,
            retain_claim=self._retain_claim, _claim_guard=self._pin)

    def restore_ledger(self, witness, ciphertext, destination, *, approval,
                       journal_key, anchor_key, archive_key):
        """Restore an explicitly approved ledger at the retained active receipt."""
        self._verify_separation(witness, journal_key, anchor_key)
        try:
            archive._cipher(archive_key, self.key)
        except (TypeError, ValueError):
            recovery._deny()
        with self._pin() as receipt:
            return witness.restore_ledger(
                ciphertext, destination, approval=approval, expected_receipt=receipt,
                journal_key=journal_key, anchor_key=anchor_key, archive_key=archive_key)

    def recover_witness(self, witness, snapshot, *, ledger_path, journal_key, anchor_key,
                        recovery_receipt=None):
        """Rebuild a witness at the retained receipt, with an optional independent pin."""
        self._verify_separation(witness, journal_key, anchor_key)
        external = nullcontext()
        if recovery_receipt is not None:
            recovery_receipt._verify_separation(self, witness, journal_key, anchor_key)
            external = recovery_receipt._store._pin()
        with external as independently_retained, self._pin(independently_retained) as receipt:
            return custody.DecimalCustody.recover(
                witness.path, snapshot, trusted_receipt=receipt,
                custody_key=witness.custody_key, operator_key=witness.operator_key,
                ledger_path=ledger_path, journal_key=journal_key, anchor_key=anchor_key,
                _require_prepared_target=True)


class DecimalRecoveryReceipt:
    """Offline monotonic witness receipt under separate operator custody."""

    def __init__(self, path, *, receipt_key):
        self._store = DecimalReceiptStore(path, receipt_key=receipt_key,
                                         _protocol=_RECOVERY_PROTOCOL)

    def _verify_separation(self, receipts, witness, *keys):
        self._store._verify_separation(witness, receipts.key, *keys)
        if self._store.path.parent == receipts.path.parent:
            recovery._deny()

    @classmethod
    def create(cls, path, *, receipt_key, receipts, witness, reviewed_receipt):
        """Provision against an explicitly reviewed tip held by both local resources."""
        retained = cls(path, receipt_key=receipt_key)
        retained._verify_separation(receipts, witness)
        with receipts._pin(reviewed_receipt) as receipt, witness._open(write=False) as journal:
            if receipt != reviewed_receipt:
                recovery._deny()
            witness._read(journal, receipt, exact=True)
            retained._store._initialize(receipt)
        return retained

    def retain(self, receipts, witness, *, expected_receipt, reviewed_receipt):
        """Advance to the exact reviewed descendant retained by both local resources."""
        self._verify_separation(receipts, witness)
        with (self._store._open() as db, receipts._pin(reviewed_receipt) as receipt,
              witness._open(write=False) as journal):
            current = self._store._read(db, pending=False)
            if (current != expected_receipt or receipt != reviewed_receipt
                    or receipt["number"] < current["number"]):
                recovery._deny()
            witness._read(journal, current, exact=False)
            witness._read(journal, receipt, exact=True)
            if receipt != current:
                self._store._save(db, receipt, pending=False)
                db.commit()
            return receipt

    def retain_terminal(self, receipts, witness, *, expected_receipt, reviewed_receipt,
                        operator_record):
        """Retain an explicitly reviewed terminal witness tip after a lost handoff."""
        self._verify_separation(receipts, witness)
        with self._store._open() as db, witness._open(write=False) as journal:
            current = self._store._read(db, pending=False)
            if current != expected_receipt:
                recovery._deny()
            witness._read(journal, current, exact=False)
            self._require_terminal(witness, journal, reviewed_receipt, operator_record)
            if reviewed_receipt != current:
                self._store._save(db, reviewed_receipt, pending=False)
                db.commit()
            return reviewed_receipt

    def repair_local_terminal(self, receipts, witness, *, reviewed_receipt, operator_record):
        """Restore only a terminal local pin from the exact independent and witness tips."""
        self._verify_separation(receipts, witness)
        with self._store._pin(reviewed_receipt) as tip:
            if tip != reviewed_receipt:
                recovery._deny()
            local = receipts._open() if os.path.lexists(receipts.path) else nullcontext()
            with local as db, witness._open(write=False) as journal:
                self._require_terminal(witness, journal, tip, operator_record)
                if db is None:
                    self._publish_missing_local(receipts, tip)
                else:
                    previous, pending = receipts._read_state(db)
                    witness._read(journal, previous, exact=False)
                    if previous != tip or pending:
                        receipts._save(db, tip, pending=False)
                        db.commit()
                return tip

    def inspect_local_terminal(self, receipts, witness, *, reviewed_receipt, operator_record):
        """Verify a published terminal receipt after interruption without changing files."""
        with self._verified_terminal(receipts, witness, reviewed_receipt, operator_record) as tip:
            with receipts._read_published(tip) as info:
                return {"receipt": tip, "additionalLinkPresent": info.st_nlink == 2}

    def cleanup_local_terminal_stage(self, staging_path, receipts, witness, *, reviewed_receipt,
                                     operator_record):
        """Remove only the selected orphan hard link to the verified terminal receipt."""
        stage_path = Path(staging_path)
        target = receipts.path
        if (stage_path.parent.parent != target.parent or stage_path.name != "receipt.db"
                or not stage_path.parent.name.startswith(_TERMINAL_STAGE_PREFIX)):
            recovery._deny()
        stage = DecimalReceiptStore(stage_path, receipt_key=receipts.key)
        try:
            with (stage._lock_staging_directory() as folder_fd,
                  self._verified_terminal(receipts, witness, reviewed_receipt, operator_record) as tip,
                  receipts._read_published(tip) as verified):
                # Make the destination name durable before removing its other link.
                self._sync_receipt_directory(target.parent)
                current = target.lstat()
                link = os.stat(stage_path.name, dir_fd=folder_fd, follow_symlinks=False)
                if (verified.st_nlink != 2 or current.st_nlink != 2
                        or current.st_ctime_ns != verified.st_ctime_ns
                        or not os.path.samestat(verified, current)
                        or not os.path.samestat(verified, link)
                        or not os.path.samestat(os.fstat(folder_fd), stage_path.parent.lstat())
                        or any(os.path.lexists(str(path) + suffix)
                               for path in (target, stage_path) for suffix in _SIDECARS)):
                    recovery._deny()
                os.unlink(stage_path.name, dir_fd=folder_fd)
                os.fsync(folder_fd)
        except OSError:
            recovery._deny()

    @contextmanager
    def _verified_terminal(self, receipts, witness, reviewed_receipt, operator_record):
        self._verify_separation(receipts, witness)
        with (self._store._pin(reviewed_receipt) as tip,
              witness._open(write=False) as journal):
            if tip != reviewed_receipt:
                recovery._deny()
            self._require_terminal(witness, journal, tip, operator_record)
            yield tip

    @staticmethod
    def _require_terminal(witness, journal, tip, operator_record):
        record, _, _ = witness._read(journal, tip, exact=True)
        if record["status"] != "QUARANTINED" or record != operator_record:
            recovery._deny()

    def _publish_missing_local(self, receipts, tip):
        path = receipts.path
        try:
            receipts._check_directory()
            folder = Path(tempfile.mkdtemp(prefix=_TERMINAL_STAGE_PREFIX, dir=path.parent))
            stage = DecimalReceiptStore(folder / "receipt.db", receipt_key=receipts.key)
            with stage._lock_staging_directory():
                stage._initialize(tip)
                with stage._read_published(tip):
                    if any(os.path.lexists(str(path) + suffix) for suffix in _SIDECARS):
                        recovery._deny()
                    os.link(stage.path, path, follow_symlinks=False)
                # On an ambiguous sync failure both names remain for review.
                self._sync_receipt_directory(path.parent)
                stage.path.unlink()
                folder.rmdir()
        except OSError:
            recovery._deny()

    @staticmethod
    def _sync_receipt_directory(path):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class DecimalPromotionCheckpoint:
    """Separately keyed, one-promotion compare-and-swap checkpoint rehearsal."""

    def __init__(self, path, *, checkpoint_key):
        self._store = DecimalReceiptStore(path, receipt_key=checkpoint_key,
                                         _protocol=_PROMOTION_PROTOCOL)

    def _verify_separation(self, receipts, witness, *keys):
        self._store._verify_separation(witness, receipts.key, *keys)
        if self._store.path.parent == receipts.path.parent:
            recovery._deny()

    @classmethod
    def create(cls, path, *, checkpoint_key, receipts, witness, reserved_receipt,
               prepared_receipt):
        """Provision before promotion at an independently reviewed prepared tip."""
        checkpoint = cls(path, checkpoint_key=checkpoint_key)
        checkpoint._verify_separation(receipts, witness)
        with receipts._open() as db, witness._open(write=False) as journal:
            if receipts._read(db, pending=True) != reserved_receipt:
                recovery._deny()
            witness._read(journal, reserved_receipt, exact=False)
            record, tip, claimed = witness._read(journal, prepared_receipt, exact=True)
            if (tip["number"] not in (reserved_receipt["number"], reserved_receipt["number"] + 1)
                    or record["status"] not in recovery._PENDING
                    or (record["status"] == "ROTATION_PENDING" and not claimed)):
                recovery._deny()
            checkpoint._store._initialize(tip)
        return checkpoint

    def latest(self):
        """Read the authenticated checkpoint held by the separate custodian."""
        return self._store.latest()

    def _export_mac(self, receipt):
        return ledger._mac(self._store.key, _EXPORT_PROTOCOL, receipt["number"], receipt["mac"])

    def export(self, *, expected_receipt):
        """Authenticate a retained receipt for separate storage by the custodian."""
        with self._store._pin(expected_receipt) as receipt:
            if receipt != expected_receipt:
                recovery._deny()
            return {"receipt": receipt, "mac": self._export_mac(receipt)}

    @classmethod
    def recover(cls, path, exported, *, trusted_receipt, checkpoint_key, receipts, witness,
                ledger_path, reserved_receipt, prepared_receipt, operator_record,
                journal_key, anchor_key):
        """Recreate a lost checkpoint at an independently pinned completed promotion."""
        checkpoint = cls(path, checkpoint_key=checkpoint_key)
        with checkpoint._verified_recovery(
                exported, trusted_receipt=trusted_receipt, receipts=receipts, witness=witness,
                ledger_path=ledger_path, reserved_receipt=reserved_receipt,
                prepared_receipt=prepared_receipt, operator_record=operator_record,
                journal_key=journal_key, anchor_key=anchor_key):
            checkpoint._publish_recovered(trusted_receipt)
        return checkpoint

    def _publish_recovered(self, receipt):
        target = self._store.path
        try:
            self._store._check_directory()
            with tempfile.TemporaryDirectory(prefix=_CHECKPOINT_STAGE_PREFIX, dir=target.parent) as folder:
                stage = DecimalPromotionCheckpoint(Path(folder) / "checkpoint.db",
                                                   checkpoint_key=self._store.key)
                with stage._store._lock_staging_directory():
                    stage._store._initialize(receipt)
                    with stage._store._read_published(receipt):
                        if any(os.path.lexists(str(target) + suffix) for suffix in _SIDECARS):
                            recovery._deny()
                        os.link(stage._store.path, target, follow_symlinks=False)
                    stage._store.path.unlink()
                    fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(fd)
                    finally:
                        os.close(fd)
        except OSError:
            recovery._deny()

    def inspect_recovered(self, exported, *, trusted_receipt, receipts, witness, ledger_path,
                          reserved_receipt, prepared_receipt, operator_record, journal_key,
                          anchor_key):
        """Read back an exact published candidate after an interrupted recovery."""
        with self._verified_recovery(
                exported, trusted_receipt=trusted_receipt, receipts=receipts, witness=witness,
                ledger_path=ledger_path, reserved_receipt=reserved_receipt,
                prepared_receipt=prepared_receipt, operator_record=operator_record,
                journal_key=journal_key, anchor_key=anchor_key):
            with self._store._read_published(trusted_receipt) as info:
                return {"receipt": trusted_receipt.copy(), "additionalLinkPresent": info.st_nlink == 2}

    def cleanup_recovered_stage(self, staging_path, exported, *, trusted_receipt, receipts,
                                witness, ledger_path, reserved_receipt, prepared_receipt,
                                operator_record, journal_key, anchor_key):
        """Remove only the operator-selected orphan hard link to an exact checkpoint."""
        target, stage_path = self._store.path, Path(staging_path)
        if (stage_path.parent.parent != target.parent or stage_path.name != "checkpoint.db"
                or not stage_path.parent.name.startswith(_CHECKPOINT_STAGE_PREFIX)):
            recovery._deny()
        stage = DecimalPromotionCheckpoint(stage_path, checkpoint_key=self._store.key)
        try:
            with stage._store._lock_staging_directory() as folder_fd, self._verified_recovery(
                    exported, trusted_receipt=trusted_receipt, receipts=receipts, witness=witness,
                    ledger_path=ledger_path, reserved_receipt=reserved_receipt,
                    prepared_receipt=prepared_receipt, operator_record=operator_record,
                    journal_key=journal_key, anchor_key=anchor_key):
                with self._store._read_published(trusted_receipt) as verified:
                    current = target.lstat()
                    link = os.stat(stage_path.name, dir_fd=folder_fd, follow_symlinks=False)
                    if (verified.st_nlink != 2 or current.st_nlink != 2
                            or current.st_ctime_ns != verified.st_ctime_ns
                            or not os.path.samestat(verified, current)
                            or not os.path.samestat(verified, link)
                            or not os.path.samestat(os.fstat(folder_fd), stage_path.parent.lstat())
                            or any(os.path.lexists(str(stage_path) + suffix) for suffix in _SIDECARS)):
                        recovery._deny()
                    os.unlink(stage_path.name, dir_fd=folder_fd)
                    os.fsync(folder_fd)
        except OSError:
            recovery._deny()

    @contextmanager
    def _verified_recovery(self, exported, *, trusted_receipt, receipts, witness, ledger_path,
                           reserved_receipt, prepared_receipt, operator_record, journal_key,
                           anchor_key):
        self._verify_separation(receipts, witness, journal_key, anchor_key)
        if (type(exported) is not dict or exported.keys() != {"receipt", "mac"}
                or type(trusted_receipt) is not dict
                or trusted_receipt.keys() != {"number", "mac"}
                or type(trusted_receipt["number"]) is not int
                or type(trusted_receipt["mac"]) is not str
                or exported["receipt"] != trusted_receipt or type(exported["mac"]) is not str
                or not exported["mac"].isascii()
                or not hmac.compare_digest(exported["mac"], self._export_mac(trusted_receipt))):
            recovery._deny()
        with receipts._open() as db, witness._open(write=False) as journal:
            retained, pending = receipts._read_state(db)
            witness._read(journal, reserved_receipt, exact=False)
            witness._read(journal, prepared_receipt, exact=False)
            record, tip, _ = witness._read(journal, trusted_receipt, exact=True)
            number, _, _, _, mac = witness._next_event(prepared_receipt, "record", operator_record)
            if (prepared_receipt["number"] not in (reserved_receipt["number"],
                                                   reserved_receipt["number"] + 1)
                    or tip != {"number": number, "mac": mac}
                    or record != operator_record or record["status"] != "ACTIVE"
                    or retained != (reserved_receipt if pending else tip)):
                recovery._deny()
            source = recovery._source(ledger_path)
            with (witness._hold_original(witness.path) as same_witness,
                  witness._hold_original(source) as same_ledger,
                  recovery._fixture(source) as candidate):
                recovery._require_checkpoint(candidate, journal_key, anchor_key, record["current"])
                if not same_witness() or not same_ledger():
                    recovery._deny()
                yield
