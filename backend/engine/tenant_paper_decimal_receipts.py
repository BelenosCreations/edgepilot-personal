"""Independent receipt storage for the offline synthetic Decimal rehearsal."""
from contextlib import closing, contextmanager, ExitStack
import hmac
import os
from pathlib import Path
import sqlite3
import stat
from urllib.parse import quote

from . import tenant_paper_decimal_archive as archive
from . import tenant_paper_decimal_atomic_rehearsal as ledger
from . import tenant_paper_decimal_custody as custody
from . import tenant_paper_decimal_recovery as recovery


_PROTOCOL = "EDGEPILOT-SYNTHETIC-DECIMAL-RECEIPT-v1"
_PROMOTION_PROTOCOL = "EDGEPILOT-SYNTHETIC-DECIMAL-PROMOTION-CHECKPOINT-v1"
_EXPORT_PROTOCOL = "EDGEPILOT-SYNTHETIC-DECIMAL-PROMOTION-EXPORT-v1"
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
    def _open(self):
        try:
            self._check_directory()
            info = self.path.lstat()
            if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_uid != os.getuid() or info.st_nlink != 1):
                recovery._deny()
            uri = "file:" + quote(str(self.path), safe="/") + "?mode=rw"
            with closing(sqlite3.connect(uri, uri=True, isolation_level=None)) as db:
                db.execute("PRAGMA trusted_schema=OFF")
                db.execute("PRAGMA synchronous=EXTRA")
                db.execute("BEGIN IMMEDIATE")
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

    def recover_witness(self, witness, snapshot, *, ledger_path, journal_key, anchor_key):
        """Rebuild a witness at the retained receipt and refuse ambiguous old ledgers."""
        self._verify_separation(witness, journal_key, anchor_key)
        with self._pin() as receipt:
            return custody.DecimalCustody.recover(
                witness.path, snapshot, trusted_receipt=receipt,
                custody_key=witness.custody_key, operator_key=witness.operator_key,
                ledger_path=ledger_path, journal_key=journal_key, anchor_key=anchor_key,
                _require_prepared_target=True)


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
        checkpoint._verify_separation(receipts, witness, journal_key, anchor_key)
        if (type(exported) is not dict or exported.keys() != {"receipt", "mac"}
                or type(trusted_receipt) is not dict
                or trusted_receipt.keys() != {"number", "mac"}
                or type(trusted_receipt["number"]) is not int
                or type(trusted_receipt["mac"]) is not str
                or exported["receipt"] != trusted_receipt or type(exported["mac"]) is not str
                or not exported["mac"].isascii()
                or not hmac.compare_digest(exported["mac"], checkpoint._export_mac(trusted_receipt))):
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
                checkpoint._store._initialize(tip)
        return checkpoint
