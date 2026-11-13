"""Offline operator checkpoints for the fractional Decimal SQLite rehearsal.

The latest tip must come from an independent custodian. This module proposes
records and audits private synthetic fixtures. It has no production callers
or durable publisher.
"""
from contextlib import contextmanager, closing
from functools import lru_cache
import hmac
import json
import os
import sqlite3
import uuid

from . import tenant_paper_decimal_atomic_rehearsal as ledger


_PROTOCOL = "EDGEPILOT-OFFLINE-DECIMAL-RECOVERY-v1"
_PENDING = ("ADVANCE_PENDING", "ROTATION_PENDING")
_POLICY_FIELDS = ("seed", "protected", "spend", "trade", "loss")
_SIDECARS = ("-journal", "-wal", "-shm")


class DecimalRecoveryDenied(ValueError):
    """Safe refusal for offline recovery evidence or fixture failures."""


def _deny():
    raise DecimalRecoveryDenied("Offline Decimal recovery unavailable")


def _key_id(key):
    # HMAC-equivalent byte strings must identify the same key for retirement.
    return ledger._mac(key, _PROTOCOL, "KEY_ID")


def _keys(*keys):
    checked = tuple(ledger._key(key) for key in keys)
    if len({_key_id(key) for key in checked}) != len(checked):
        _deny()
    return checked


def _schema(db):
    return [(name, kind, table, " ".join(sql.split()) if sql else None)
            for name, kind, table, sql in db.execute(
                "SELECT name, type, tbl_name, sql FROM sqlite_master ORDER BY name")]


@lru_cache(maxsize=1)
def _expected_schema():
    with closing(sqlite3.connect(":memory:")) as db:
        db.executescript(ledger._SCHEMA)
        return _schema(db)


def _source(path):
    source = ledger.base._file(path)
    if any(os.path.lexists(str(source) + suffix) for suffix in _SIDECARS):
        _deny()  # A crash sidecar needs operator review before SQLite reopens it.
    return source


@contextmanager
def _fixture(path, *, write=False):
    try:
        with closing(ledger._open(_source(path), read_only=not write)) as db:
            if not write:
                db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            if (_schema(db) != _expected_schema()
                    or db.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                    or db.execute("PRAGMA foreign_key_check").fetchone() is not None
                    or [tuple(row) for row in db.execute("SELECT id,label FROM decimal_marker")]
                    != [(1, ledger._MAGIC)]):
                _deny()
            yield db
    except Exception:
        raise DecimalRecoveryDenied("Offline Decimal recovery unavailable") from None


def _checkpoint(db, journal, anchor, epoch):
    accounts = ledger._checkpoint_data(db, journal)
    if not accounts:
        _deny()
    for user, account, *_ in accounts:
        ledger._identity(user, account)
    payload = [epoch, _key_id(journal), accounts]
    return {
        "epoch": epoch,
        "journalKeyId": payload[1],
        "accounts": accounts,
        "mac": ledger._mac(anchor, _PROTOCOL, "CHECKPOINT", payload),
    }


def _record(operator, *, sequence, fixture_id, previous, status, current,
            target=None, retired=(), reason=None):
    record = {
        "fixtureId": fixture_id,
        "sequence": sequence,
        "previousMac": previous,
        "status": status,
        "current": current,
        "target": target,
        "retiredKeyIds": list(retired),
        "quarantineReason": reason,
    }
    record["mac"] = _record_mac(operator, record)
    return record


def _record_mac(operator, record):
    payload = json.dumps({k: v for k, v in record.items() if k != "mac"},
                         sort_keys=True, separators=(",", ":"))
    return ledger._mac(operator, _PROTOCOL, "RECORD", payload)


def evidence_tip(record):
    """Return a candidate tip for independent publication with its record."""
    return {field: record[field] for field in ("fixtureId", "sequence", "mac")}


def _review(record, trusted_tip, operator, *statuses):
    if (type(record) is not dict or type(trusted_tip) is not dict
            or not isinstance(record.get("mac"), str)
            or not hmac.compare_digest(record["mac"], _record_mac(operator, record))
            or evidence_tip(record) != trusted_tip or record["status"] not in statuses):
        _deny()


def _next(operator, record, status, *, current=None, target=None,
          retired=None, reason=None):
    return _record(
        operator, sequence=record["sequence"] + 1, fixture_id=record["fixtureId"],
        previous=record["mac"], status=status,
        current=record["current"] if current is None else current, target=target,
        retired=record["retiredKeyIds"] if retired is None else retired, reason=reason,
    )


def establish_decimal_recovery(path, *, journal_key, anchor_key, operator_key):
    """Propose genesis for a new synthetic fixture lineage under external custody."""
    with _fixture(path) as db:
        journal, anchor, operator = _keys(journal_key, anchor_key, operator_key)
        checkpoint = _checkpoint(db, journal, anchor, 1)
        return _record(operator, sequence=1, fixture_id=str(uuid.uuid4()),
                       previous=ledger._GENESIS, status="ACTIVE", current=checkpoint)


def _require_checkpoint(db, journal, anchor, pin):
    if _checkpoint(db, journal, anchor, pin["epoch"]) != pin:
        _deny()


def prepare_decimal_advance(current_path, candidate_path, *, record, trusted_tip,
                            journal_key, anchor_key, operator_key):
    """Verify a private candidate extends every account's pinned policy and journal."""
    with _fixture(current_path) as original, _fixture(candidate_path) as candidate:
        journal, anchor, operator = _keys(journal_key, anchor_key, operator_key)
        _review(record, trusted_tip, operator, "ACTIVE")
        current = record["current"]
        _require_checkpoint(original, journal, anchor, current)
        proposed = _checkpoint(candidate, journal, anchor, current["epoch"] + 1)
        counts = {(u, a): count for u, a, count, _, _ in proposed["accounts"]}
        if current["accounts"] == proposed["accounts"]:
            _deny()
        for user, account, count, _, last_mac in current["accounts"]:
            scope = (user, account)
            if counts.get(scope, -1) < count:
                _deny()
            policies = [
                tuple(db.execute(
                    "SELECT " + ", ".join(_POLICY_FIELDS)
                    + " FROM decimal_wallets WHERE user_id=? AND account_id=?", scope
                ).fetchone())
                for db in (original, candidate)
            ]
            if policies[0] != policies[1]:
                _deny()
            if count:
                prefix = candidate.execute(
                    "SELECT entry_mac FROM decimal_events WHERE user_id=? AND account_id=? "
                    "AND seq=?", (*scope, count)).fetchone()
                if prefix is None or prefix[0] != last_mac:
                    _deny()
        return _next(operator, record, "ADVANCE_PENDING", target=proposed)


def _remac(db, replacement):
    for row in db.execute("SELECT * FROM decimal_wallets ORDER BY user_id,account_id"):
        scope = (row["user_id"], row["account_id"])
        previous = ledger._GENESIS
        # Read the rows before updating the same table on this connection.
        events = db.execute(
            "SELECT * FROM decimal_events WHERE user_id=? AND account_id=? ORDER BY seq",
            scope).fetchall()
        for event in events:
            fields = [event[field] for field in ledger._EVENT_FIELDS[:-1]]
            entry = ledger._mac(replacement, "EVENT", *fields, previous)
            db.execute(
                "UPDATE decimal_events SET previous_mac=?,entry_mac=? "
                "WHERE user_id=? AND account_id=? AND seq=?",
                (previous, entry, *scope, event["seq"]))
            previous = entry
        wallet = dict(row, last_mac=previous, policy_mac=ledger._policy_mac(replacement, row))
        db.execute(
            "UPDATE decimal_wallets SET last_mac=?,policy_mac=?,state_mac=? "
            "WHERE user_id=? AND account_id=?",
            (previous, wallet["policy_mac"],
             ledger._state_mac(replacement, wallet, ledger._positions(db, *scope)), *scope))


def prepare_decimal_rotation(path, *, record, trusted_tip, journal_key,
                             replacement_key, anchor_key, operator_key):
    """Predict the replacement pin in a transaction that always rolls back."""
    with _fixture(path, write=True) as db:
        journal, replacement, anchor, operator = _keys(
            journal_key, replacement_key, anchor_key, operator_key)
        _review(record, trusted_tip, operator, "ACTIVE")
        if _key_id(replacement) in record["retiredKeyIds"]:
            _deny()
        _require_checkpoint(db, journal, anchor, record["current"])
        _remac(db, replacement)
        target = _checkpoint(db, replacement, anchor, record["current"]["epoch"] + 1)
        return _next(operator, record, "ROTATION_PENDING", target=target)


def execute_prepared_decimal_rotation(path, *, record, trusted_tip, journal_key,
                                      replacement_key, anchor_key, operator_key,
                                      _interrupt_before_commit=False):
    """Apply only the independently published rotation plan under the write lock."""
    with _fixture(path, write=True) as db:
        journal, replacement, anchor, operator = _keys(
            journal_key, replacement_key, anchor_key, operator_key)
        _review(record, trusted_tip, operator, "ROTATION_PENDING")
        _require_checkpoint(db, journal, anchor, record["current"])
        _remac(db, replacement)
        _require_checkpoint(db, replacement, anchor, record["target"])
        if _interrupt_before_commit:
            _deny()
        db.commit()


def inspect_decimal_recovery(path, *, record, trusted_tip, journal_key,
                             anchor_key, operator_key):
    """Classify an observed fixture without approving it or publishing anything."""
    try:
        journal, anchor, operator = _keys(journal_key, anchor_key, operator_key)
        _review(record, trusted_tip, operator, "ACTIVE", *_PENDING, "QUARANTINED")
        if record["status"] == "QUARANTINED":
            return "QUARANTINED"
        current = record["current"]
        target = record["target"]
        with _fixture(path) as db:
            observed = _checkpoint(db, journal, anchor, current["epoch"])
            if observed == current:
                return "PINNED_ACTIVE" if target is None else "AMBIGUOUS_OLD_STATE"
            if target is not None and _checkpoint(db, journal, anchor, target["epoch"]) == target:
                return "PREPARED_TARGET_REQUIRES_APPROVAL"
            _deny()
    except Exception:
        raise DecimalRecoveryDenied("Offline Decimal recovery unavailable") from None


def approve_decimal_promotion(path, *, record, trusted_tip, journal_key, anchor_key,
                              operator_key):
    """Explicitly approve the exact prepared target and propose its new active tip."""
    with _fixture(path) as db:
        journal, anchor, operator = _keys(journal_key, anchor_key, operator_key)
        _review(record, trusted_tip, operator, *_PENDING)
        _require_checkpoint(db, journal, anchor, record["target"])
        retired = record["retiredKeyIds"]
        if record["status"] == "ROTATION_PENDING":
            retired = [*retired, record["current"]["journalKeyId"]]
        return _next(operator, record, "ACTIVE", current=record["target"], retired=retired)


def quarantine_decimal_recovery(*, record, trusted_tip, operator_key, reason):
    """Propose terminal quarantine, including when the journal key is unavailable."""
    try:
        operator = ledger._key(operator_key)
        _review(record, trusted_tip, operator, "ACTIVE", *_PENDING)
        if reason not in ("COMPROMISED_KEY", "AMBIGUOUS_OLD_STATE", "INTEGRITY_FAILURE"):
            _deny()
        retired = set(record["retiredKeyIds"])
        if reason == "COMPROMISED_KEY":
            retired.add(record["current"]["journalKeyId"])
            if record["target"] is not None:
                retired.add(record["target"]["journalKeyId"])
        return _next(operator, record, "QUARANTINED", retired=sorted(retired), reason=reason)
    except Exception:
        raise DecimalRecoveryDenied("Offline Decimal recovery unavailable") from None
