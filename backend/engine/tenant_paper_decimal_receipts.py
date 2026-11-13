"""Independent receipt storage for the offline synthetic Decimal rehearsal."""
from contextlib import closing, contextmanager
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
_SCHEMA = """CREATE TABLE retained_receipt (
    id INTEGER PRIMARY KEY CHECK (id = 1), number INTEGER NOT NULL,
    tip TEXT NOT NULL, pending INTEGER NOT NULL, signature TEXT NOT NULL)"""


class DecimalReceiptStore:
    """A separately operated receipt pin and persistent rotation reservation."""

    def __init__(self, path, *, receipt_key):
        self.path = Path(path)
        self.key = ledger._key(receipt_key)

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
        try:
            store._check_directory()
            with witness._open(write=False) as db:
                _, receipt, _ = witness._read(db, genesis, exact=True)
                if receipt["number"] != 1:
                    recovery._deny()
                fd = os.open(store.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                os.close(fd)
                with closing(sqlite3.connect(store.path, isolation_level=None)) as pins:
                    pins.execute("PRAGMA synchronous=EXTRA")
                    pins.execute("BEGIN IMMEDIATE")
                    pins.execute(_SCHEMA)
                    store._save(pins, receipt, pending=False)
                    pins.commit()
                fd = os.open(store.path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            return store
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
        return ledger._mac(self.key, _PROTOCOL, number, tip, pending)

    def _save(self, db, receipt, *, pending):
        number, tip = receipt["number"], receipt["mac"]
        reserved = int(pending)
        db.execute("INSERT OR REPLACE INTO retained_receipt VALUES (1,?,?,?,?)",
                   (number, tip, reserved, self._signature(number, tip, reserved)))

    def _read(self, db, *, pending):
        row = db.execute("SELECT number,tip,pending,signature FROM retained_receipt WHERE id=1"
                         ).fetchone()
        if row is None:
            recovery._deny()
        number, tip, reserved, signature = row
        if (type(number) is not int or number < 1 or type(tip) is not str or len(tip) != 64
                or reserved != pending or type(signature) is not str or not signature.isascii()
                or not hmac.compare_digest(signature, self._signature(number, tip, reserved))):
            recovery._deny()
        return {"number": number, "mac": tip}

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
