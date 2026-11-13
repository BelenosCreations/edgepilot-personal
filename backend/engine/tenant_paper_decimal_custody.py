"""Single-lineage offline custody for synthetic Decimal recovery evidence."""
from contextlib import contextmanager, closing
import hmac
import json
import os
from pathlib import Path
import sqlite3
import stat
from urllib.parse import quote

from . import tenant_paper_decimal_atomic_rehearsal as ledger
from . import tenant_paper_decimal_recovery as recovery


_PROTOCOL = "EDGEPILOT-SYNTHETIC-DECIMAL-CUSTODY-v1"
_STATUSES = ("ACTIVE", *recovery._PENDING, "QUARANTINED")


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

    def _append(self, db, receipt, kind, data):
        number = 1 if receipt is None else receipt["number"] + 1
        previous = ledger._GENESIS if receipt is None else receipt["mac"]
        payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
        mac = self._mac(number, kind, payload, previous)
        db.execute("INSERT INTO custody_events VALUES (?,?,?,?,?)",
                   (number, kind, payload, previous, mac))
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

    def rotate(self, path, *, expected_receipt, journal_key, replacement_key,
               anchor_key, _interrupt=None):
        """Consume one rotation claim before touching the synthetic ledger."""
        recovery._keys(self.custody_key, self.operator_key, journal_key, replacement_key, anchor_key)
        with self._open(write=True) as db:
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
            claim = self._append(db, receipt, "rotation_claim", current["mac"])
            db.commit()
        if _interrupt == "after_claim":
            recovery._deny()
        # Recheck the durable claim under the custody lock. Quarantine may
        # have won the race before this lock. The claim is never cleared.
        with self._open(write=True) as db:
            self._read(db, claim, exact=True)
            recovery.execute_prepared_decimal_rotation(
                path, record=current, trusted_tip=recovery.evidence_tip(current),
                journal_key=journal_key, replacement_key=replacement_key,
                anchor_key=anchor_key, operator_key=self.operator_key,
                _interrupt_before_commit=_interrupt == "before_ledger_commit")
            if _interrupt == "after_ledger_commit":
                recovery._deny()
            return claim
