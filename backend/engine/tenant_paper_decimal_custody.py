"""Single-lineage offline custody for synthetic Decimal recovery evidence."""
from contextlib import contextmanager, closing, nullcontext, ExitStack
import hmac
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
from urllib.parse import quote

from . import tenant_paper_decimal_archive as archive
from . import tenant_paper_decimal_atomic_rehearsal as ledger
from . import tenant_paper_decimal_recovery as recovery


_PROTOCOL = "EDGEPILOT-SYNTHETIC-DECIMAL-CUSTODY-v1"
_STATUSES = ("ACTIVE", *recovery._PENDING, "QUARANTINED")
_MAX_SNAPSHOT = 8 * 1024 * 1024


def _check_transition(current, proposed, claimed):
    if current is None:
        if (proposed["sequence"] != 1 or proposed["previousMac"] != ledger._GENESIS
                or proposed["status"] != "ACTIVE" or proposed["current"]["epoch"] != 1
                or proposed["target"] is not None or proposed["retiredKeyIds"]
                or proposed["quarantineReason"] is not None):
            recovery._deny()
        return
    if (proposed["fixtureId"] != current["fixtureId"]
            or proposed["sequence"] != current["sequence"] + 1
            or proposed["previousMac"] != current["mac"]
            or current["status"] == "QUARANTINED"):
        recovery._deny()
    old, new = current["status"], proposed["status"]
    pin, target, retired = current["current"], proposed["target"], current["retiredKeyIds"]
    if new == "QUARANTINED":
        reason = proposed["quarantineReason"]
        expected = set(retired)
        if reason == "COMPROMISED_KEY":
            expected.add(pin["journalKeyId"])
            if current["target"] is not None:
                expected.add(current["target"]["journalKeyId"])
        elif reason not in ("AMBIGUOUS_OLD_STATE", "INTEGRITY_FAILURE"):
            recovery._deny()
        if (proposed["current"] != pin or target is not None
                or proposed["retiredKeyIds"] != sorted(expected)):
            recovery._deny()
        return
    if proposed["quarantineReason"] is not None:
        recovery._deny()
    if old == "ACTIVE" and new in recovery._PENDING:
        if (proposed["current"] != pin or proposed["retiredKeyIds"] != retired
                or target["epoch"] != pin["epoch"] + 1
                or target["journalKeyId"] in retired
                or (target["journalKeyId"] == pin["journalKeyId"]) != (new == "ADVANCE_PENDING")):
            recovery._deny()
        return
    if old in recovery._PENDING and new == "ACTIVE":
        if old == "ROTATION_PENDING":
            if not claimed:
                recovery._deny()
            retired = [*retired, pin["journalKeyId"]]
        if (proposed["current"] != current["target"] or target is not None
                or proposed["retiredKeyIds"] != retired):
            recovery._deny()
        return
    recovery._deny()


class DecimalCustody:
    """An offline operator-side SQLite journal, opened afresh per operation."""

    def __init__(self, path, *, custody_key, operator_key):
        self.path = Path(path)
        self.custody_key, self.operator_key = recovery._keys(custody_key, operator_key)
        parent = self.path.parent
        info = parent.stat()
        if (parent != parent.resolve(strict=True) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            recovery._deny()

    @classmethod
    def create(cls, path, *, genesis, custody_key, operator_key):
        """Provision one new witness file and return its authenticated genesis receipt."""
        witness = cls(path, custody_key=custody_key, operator_key=operator_key)
        try:
            witness._verify_record(genesis)
            _check_transition(None, genesis, False)
            fd = os.open(witness.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            with closing(sqlite3.connect(str(witness.path), isolation_level=None)) as db:
                db.execute("PRAGMA synchronous=EXTRA")
                db.execute("BEGIN IMMEDIATE")
                db.execute("CREATE TABLE custody_marker (label TEXT PRIMARY KEY)")
                db.execute("INSERT INTO custody_marker VALUES (?)", (_PROTOCOL,))
                db.execute("""CREATE TABLE custody_events (
                    number INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
                    previous TEXT NOT NULL, mac TEXT NOT NULL)""")
                receipt = witness._append(db, None, "record", genesis)
                db.commit()
            return witness, receipt
        except Exception:
            # A failed or interrupted genesis may have published. Leave the
            # path for operator inspection rather than deleting or reusing it.
            raise recovery.DecimalRecoveryDenied("Offline Decimal custody unavailable") from None

    @contextmanager
    def _open(self, *, write):
        try:
            info = self.path.lstat()
            if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_uid != os.getuid() or info.st_nlink != 1):
                recovery._deny()
            mode = "rw" if write else "ro"
            uri = "file:" + quote(str(self.path), safe="/") + "?mode=" + mode
            with closing(sqlite3.connect(uri, uri=True, isolation_level=None)) as db:
                db.execute("PRAGMA trusted_schema=OFF")
                if write:
                    db.execute("PRAGMA synchronous=EXTRA")
                db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                if (db.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' "
                               "ORDER BY name").fetchall()
                        != [("custody_events", "table"), ("custody_marker", "table")]
                        or db.execute("SELECT label FROM custody_marker").fetchall() != [(_PROTOCOL,)]
                        or db.execute("PRAGMA journal_mode").fetchone()[0] != "delete"):
                    recovery._deny()
                yield db
        except Exception:
            raise recovery.DecimalRecoveryDenied("Offline Decimal custody unavailable") from None

    def _verify_record(self, record):
        recovery._review(record, recovery.evidence_tip(record), self.operator_key, *_STATUSES)

    def _mac(self, number, kind, payload, previous):
        return ledger._mac(self.custody_key, _PROTOCOL, number, kind, payload, previous)

    def _next_event(self, receipt, kind, data):
        number = 1 if receipt is None else receipt["number"] + 1
        previous = ledger._GENESIS if receipt is None else receipt["mac"]
        payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
        mac = self._mac(number, kind, payload, previous)
        return number, kind, payload, previous, mac

    def _append(self, db, receipt, kind, data):
        event = self._next_event(receipt, kind, data)
        db.execute("INSERT INTO custody_events VALUES (?,?,?,?,?)", event)
        number, _, _, _, mac = event
        return {"number": number, "mac": mac}

    def _read(self, db, trusted_receipt, *, exact):
        record, receipt, claimed, found = None, None, False, False
        for number, kind, payload, previous, mac in db.execute(
                "SELECT * FROM custody_events ORDER BY number"):
            expected_number = 1 if receipt is None else receipt["number"] + 1
            expected_previous = ledger._GENESIS if receipt is None else receipt["mac"]
            if (number != expected_number or previous != expected_previous
                    or not hmac.compare_digest(mac, self._mac(number, kind, payload, previous))):
                recovery._deny()
            value = json.loads(payload)
            if kind == "record":
                self._verify_record(value)
                _check_transition(record, value, claimed)
                record, claimed = value, False
            elif (kind == "rotation_claim" and record is not None
                  and record["status"] == "ROTATION_PENDING" and value == record["mac"]
                  and not claimed):
                claimed = True
            else:
                recovery._deny()
            receipt = {"number": number, "mac": mac}
            found |= receipt == trusted_receipt
        if not found or (exact and receipt != trusted_receipt):
            recovery._deny()
        return record, receipt, claimed

    def read(self, *, trusted_receipt):
        """Read back a descendant of an independently retained receipt."""
        with self._open(write=False) as db:
            return self._read(db, trusted_receipt, exact=False)

    def backup(self, *, expected_receipt):
        """Export a consistent signed journal at an independently retained tip."""
        with self._open(write=False) as db:
            self._read(db, expected_receipt, exact=True)
            page_count = db.execute("PRAGMA page_count").fetchone()[0]
            page_size = db.execute("PRAGMA page_size").fetchone()[0]
            if page_count * page_size > _MAX_SNAPSHOT:
                recovery._deny()
            return db.serialize()

    @classmethod
    def recover(cls, path, snapshot, *, trusted_receipt, custody_key, operator_key,
                ledger_path, journal_key, anchor_key, _require_prepared_target=False):
        """Rebuild a lost witness using its exact retained copy and the surviving ledger."""
        try:
            recovery._keys(custody_key, operator_key, journal_key, anchor_key)
            target = cls(path, custody_key=custody_key, operator_key=operator_key)
            if (type(snapshot) is not bytes or len(snapshot) > _MAX_SNAPSHOT
                    or not snapshot.startswith(archive._SQLITE_HEADER)
                    or any(os.path.lexists(str(target.path) + suffix)
                           for suffix in ("", *recovery._SIDECARS))):
                recovery._deny()
            with tempfile.TemporaryDirectory(prefix=".custody-recover-", dir=target.path.parent) as folder:
                staged = cls(Path(folder) / "witness.db", custody_key=custody_key,
                             operator_key=operator_key)
                fd = os.open(staged.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as writer:
                    writer.write(snapshot)
                    writer.flush()
                    os.fsync(writer.fileno())
                with staged._open(write=False) as db:
                    record, _, claimed = staged._read(db, trusted_receipt, exact=True)
                    if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                        recovery._deny()
                if record["status"] == "ROTATION_PENDING" and not claimed:
                    # A later claim may have been lost before receipt handoff.
                    # Do not restore an unconsumed rotation permit.
                    recovery._deny()
                if record["status"] != "QUARANTINED":
                    observed = recovery.inspect_decimal_recovery(
                        ledger_path, record=record, trusted_tip=recovery.evidence_tip(record),
                        journal_key=journal_key, anchor_key=anchor_key, operator_key=operator_key)
                    if _require_prepared_target and observed == "AMBIGUOUS_OLD_STATE":
                        recovery._deny()
                if any(os.path.lexists(str(target.path) + suffix) for suffix in recovery._SIDECARS):
                    recovery._deny()
                os.link(staged.path, target.path)
            directory_fd = os.open(target.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return target
        except Exception:
            raise recovery.DecimalRecoveryDenied("Offline Decimal custody unavailable") from None

    def restore_ledger(self, ciphertext, destination, *, approval, expected_receipt,
                       journal_key, anchor_key, archive_key, _interrupt_before_publish=False):
        """Restore a lost ledger at the exact active witness tip with operator approval."""
        with self._open(write=True) as db:
            record, _, _ = self._read(db, expected_receipt, exact=True)
            archive._cipher(archive_key, self.custody_key, self.operator_key, journal_key, anchor_key)
            return archive.restore_decimal_archive(
                ciphertext, destination, approval=approval, record=record,
                trusted_tip=recovery.evidence_tip(record), journal_key=journal_key,
                anchor_key=anchor_key, operator_key=self.operator_key, archive_key=archive_key,
                _interrupt_before_publish=_interrupt_before_publish)

    def publish(self, proposed, *, expected_receipt, _interrupt=None):
        """CAS against the exact tip, publishing signed operator evidence once."""
        with self._open(write=True) as db:
            current, receipt, claimed = self._read(db, expected_receipt, exact=True)
            self._verify_record(proposed)
            _check_transition(current, proposed, claimed)
            updated = self._append(db, receipt, "record", proposed)
            if _interrupt == "before_commit":
                recovery._deny()
            db.commit()
            if _interrupt == "after_commit":
                recovery._deny()
            return updated

    def _rotation_plan(self, db, expected_receipt, journal_key, replacement_key, anchor_key):
        current, receipt, claimed = self._read(db, expected_receipt, exact=True)
        if current["status"] != "ROTATION_PENDING" or claimed:
            recovery._deny()
        for key, pin in ((journal_key, current["current"]),
                         (replacement_key, current["target"])):
            key_id = recovery._key_id(key)
            expected = ledger._mac(anchor_key, recovery._PROTOCOL, "CHECKPOINT",
                                   [pin["epoch"], key_id, pin["accounts"]])
            if key_id != pin["journalKeyId"] or not hmac.compare_digest(expected, pin["mac"]):
                recovery._deny()
        return current, receipt

    @staticmethod
    @contextmanager
    def _hold_original(path):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            original = os.fstat(fd)

            def unchanged():
                current = Path(path).lstat()
                return (original.st_dev, original.st_ino) == (current.st_dev, current.st_ino)

            yield unchanged
        finally:
            os.close(fd)

    def rotate(self, path, *, expected_receipt, journal_key, replacement_key,
               anchor_key, retain_claim, _interrupt=None, _claim_guard=nullcontext):
        """Consume a claim and require independent retention before changing the ledger.

        The operator's retain_claim callback must compare-and-swap from the
        pending receipt and return the exact new receipt only after retaining it.
        A failed or ambiguous handoff still consumes the local claim.
        """
        recovery._keys(self.custody_key, self.operator_key, journal_key, replacement_key, anchor_key)
        if not callable(retain_claim):
            recovery._deny()
        with ExitStack() as originals:
            with self._open(write=True) as db:
                current, receipt = self._rotation_plan(
                    db, expected_receipt, journal_key, replacement_key, anchor_key)
                ledger_path = recovery._source(path)
                same_ledger = originals.enter_context(self._hold_original(ledger_path))
                same_witness = originals.enter_context(self._hold_original(self.path))
                claim = self._append(db, receipt, "rotation_claim", current["mac"])
                db.commit()
            try:
                confirmed = retain_claim(receipt.copy(), claim.copy())
            except Exception:
                recovery._deny()
            if confirmed != claim:
                recovery._deny()
            if _interrupt == "after_claim":
                recovery._deny()
            # The independent receipt guard, when supplied, takes its lock first.
            # Then recheck the witness: quarantine may have won the race.
            with _claim_guard(claim), self._open(write=True) as db:
                self._read(db, claim, exact=True)
                if not same_ledger() or not same_witness():
                    recovery._deny()
                recovery.execute_prepared_decimal_rotation(
                    ledger_path, record=current, trusted_tip=recovery.evidence_tip(current),
                    journal_key=journal_key, replacement_key=replacement_key,
                    anchor_key=anchor_key, operator_key=self.operator_key,
                    _interrupt_before_commit=_interrupt == "before_ledger_commit")
                if _interrupt == "after_ledger_commit":
                    recovery._deny()
                return claim
