"""Offline-only whole-fixture attestations and journal-key rotation rehearsal.

Separate from Flask, production storage, the dormant paper writer and brokers.
A trusted checkpoint MUST be independently pinned by the operator: an HMAC in
the same restorable database cannot detect rollback of that entire database.
These fixtures are temporary Linux /dev/shm test databases, not durable storage.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import hmac
import json
import re

from . import tenant_paper_latch_rehearsal as latch

_PROTOCOL = "EDGEPILOT-SYNTHETIC-LATCH-CHECKPOINT-v1"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = frozenset((
    "protocol", "epoch", "accounts", "events", "stateSha256", "anchorMac",
))


class AttestedLatchDenied(ValueError):
    """Nonsecret fail-closed error; no live operations are available."""


def _fail():
    raise AttestedLatchDenied("Offline attested latch recovery unavailable")


def _keys(journal_key, anchor_key, *, replacement=None):
    journal = latch._key(journal_key)
    anchor = latch._key(anchor_key)
    if hmac.compare_digest(journal, anchor):
        _fail()
    if replacement is not None:
        fresh = latch._key(replacement)
        if (hmac.compare_digest(fresh, journal)
                or hmac.compare_digest(fresh, anchor)):
            _fail()
    return journal, anchor


def _epoch(value):
    if type(value) is not int or not 1 <= value <= 2_147_483_647:
        _fail()
    return value


def _canonical(data):
    return json.dumps(data, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _collect(db, key):
    # Detect journal scopes whose entire policy row has been removed; a
    # per-account replay alone cannot see such orphaned event histories.
    orphans = db.execute("""SELECT COUNT(*) FROM offline_latch_journal j
        WHERE NOT EXISTS (SELECT 1 FROM offline_latch_policies p
            WHERE p.user_id=j.user_id AND p.account_id=j.account_id)""").fetchone()[0]
    if orphans:
        _fail()
    policies = db.execute("""SELECT * FROM offline_latch_policies
        ORDER BY user_id, account_id""").fetchall()
    if not policies:
        _fail()
    snapshot = []
    events = 0
    for p in policies:
        user, account = latch._uuid(p["user_id"]), latch._uuid(p["account_id"])
        count, current, worst, stopped, last = latch._replay(
            db, key, user, account, p)
        snapshot.append([user, account, p["max_loss_cents"], current,
                         worst, stopped, count, last, p["policy_mac"]])
        events += count
    return snapshot, events


def _checkpoint(snapshot, events, anchor, epoch):
    digest = hashlib.sha256(_canonical(snapshot)).hexdigest()
    accounts = len(snapshot)
    signature = hmac.new(
        anchor, _canonical([_PROTOCOL, epoch, accounts, events, digest]),
        hashlib.sha256).hexdigest()
    return {"protocol": _PROTOCOL, "epoch": epoch, "accounts": accounts,
            "events": events, "stateSha256": digest, "anchorMac": signature}


def _verify_pinned(db, journal, anchor, pinned):
    if not isinstance(pinned, dict) or frozenset(pinned) != _FIELDS:
        _fail()
    epoch = _epoch(pinned.get("epoch"))
    if (pinned.get("protocol") != _PROTOCOL
            or type(pinned.get("accounts")) is not int
            or type(pinned.get("events")) is not int
            or pinned["accounts"] < 1 or pinned["events"] < 0
            or not isinstance(pinned.get("stateSha256"), str)
            or not isinstance(pinned.get("anchorMac"), str)
            or not _HEX64.fullmatch(pinned["stateSha256"])
            or not _HEX64.fullmatch(pinned["anchorMac"])):
        _fail()
    snapshot, total = _collect(db, journal)
    actual = _checkpoint(snapshot, total, anchor, epoch)
    if (actual["accounts"] != pinned["accounts"]
            or actual["events"] != pinned["events"]
            or not hmac.compare_digest(actual["stateSha256"],
                                       pinned["stateSha256"])
            or not hmac.compare_digest(actual["anchorMac"],
                                       pinned["anchorMac"])):
        _fail()
    return snapshot, total, epoch


def make_synthetic_checkpoint(path, *, journal_key, anchor_key, epoch):
    """Produce a whole-fixture authenticated pin for EXTERNAL trusted storage.

    A checkpoint is current at its creation instant only. After any new
    journal event, callers must independently and safely advance the pin.
    """
    try:
        journal, anchor = _keys(journal_key, anchor_key)
        number = _epoch(epoch)
        with closing(latch._open(path)) as db:
            db.execute("BEGIN")
            snapshot, events = _collect(db, journal)
            return _checkpoint(snapshot, events, anchor, number)
    except Exception:
        raise AttestedLatchDenied(
            "Offline attested latch recovery unavailable") from None


def verify_synthetic_checkpoint(path, *, journal_key, anchor_key, pinned):
    """Reject a missing, modified, wrong-key, or older whole-fixture snapshot.

    The caller must supply its *latest* independently held trusted pin.
    An attacker able to roll back both that pin and the SQLite file wins.
    """
    try:
        journal, anchor = _keys(journal_key, anchor_key)
        with closing(latch._open(path)) as db:
            db.execute("BEGIN")
            snapshot, events, epoch = _verify_pinned(
                db, journal, anchor, pinned)
            return {"paperOnly": True, "executionEnabled": False,
                    "checkpointVerified": True, "epoch": epoch,
                    "accounts": len(snapshot), "events": events}
    except Exception:
        raise AttestedLatchDenied(
            "Offline attested latch recovery unavailable") from None


def rotate_synthetic_journal_key(
        path, *, old_journal_key, new_journal_key, anchor_key, pinned,
        new_epoch, _fail_before_commit=False):
    """Re-MAC ALL synthetic policy/event chains in one SQLite transaction.

    The signed old checkpoint is a prerequisite. New pin publication is
    OUTSIDE this transaction. A crash after commit but before independent
    publication must fail closed and require manual operator reconciliation.
    Rotation does not revoke a compromised key at the storage/system level.
    """
    try:
        old, anchor = _keys(
            old_journal_key, anchor_key, replacement=new_journal_key)
        new = latch._key(new_journal_key)
        target_epoch = _epoch(new_epoch)
        with closing(latch._open(path)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                snapshot, _, current_epoch = _verify_pinned(
                    db, old, anchor, pinned)
                if target_epoch != current_epoch + 1:
                    _fail()
                for state in snapshot:
                    user, account, limit = state[:3]
                    previous = latch._GENESIS
                    rows = db.execute("""SELECT * FROM offline_latch_journal
                        WHERE user_id=? AND account_id=? ORDER BY seq""",
                        (user, account)).fetchall()
                    for row in rows:
                        new_mac = latch._mac(
                            new, "EVENT", user, account, row["seq"],
                            row["request_id"], row["kind"],
                            row["delta_cents"], row["accepted"],
                            row["current_after"], row["worst_after"],
                            row["latched_after"], previous)
                        db.execute("""UPDATE offline_latch_journal
                            SET previous_mac=?, entry_mac=?
                            WHERE user_id=? AND account_id=? AND seq=?""",
                            (previous, new_mac, user, account, row["seq"]))
                        previous = new_mac
                    db.execute("""UPDATE offline_latch_policies
                        SET policy_mac=?, last_mac=?
                        WHERE user_id=? AND account_id=?""",
                        (latch._mac(new, "POLICY", user, account, limit),
                         previous, user, account))
                verified, new_total = _collect(db, new)
                fresh_pin = _checkpoint(
                    verified, new_total, anchor, target_epoch)
                if _fail_before_commit:
                    _fail()
                db.commit()
                return fresh_pin
            except Exception:
                db.rollback()
                raise
    except Exception:
        raise AttestedLatchDenied(
            "Offline attested latch recovery unavailable") from None
