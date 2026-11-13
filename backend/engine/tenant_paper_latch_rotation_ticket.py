"""Offline-only precommitted synthetic latch rotation recovery ticket.

This module MUST NOT be imported by Flask or a paper-fill writer. A ticket
is useful only after an operator independently preserves it BEFORE rotation.
No automatic safe/unsafe rollback decision or production migration exists.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import hmac
import json
import re

from . import tenant_paper_latch_rehearsal as latch
from . import tenant_paper_latch_attestation as attest

_PROTOCOL = "EDGEPILOT-SYNTHETIC-ROTATION-TICKET-v1"
_FIELDS = frozenset(("protocol", "before", "after", "intentMac"))
_SHA64 = re.compile(r"^[0-9a-f]{64}$")


class RotationTicketDenied(ValueError):
    """Fixed nonsecret refusal for offline rotation ticket failures."""


def _fail():
    raise RotationTicketDenied("Offline rotation ticket unavailable")


def _canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def _auth(anchor, before, after):
    return hmac.new(anchor, _canonical(
        [_PROTOCOL, before, after]), hashlib.sha256).hexdigest()


def _validate_ticket(ticket, anchor):
    if (not isinstance(ticket, dict)
            or frozenset(ticket) != _FIELDS
            or ticket.get("protocol") != _PROTOCOL
            or not isinstance(ticket.get("before"), dict)
            or not isinstance(ticket.get("after"), dict)
            or not isinstance(ticket.get("intentMac"), str)
            or not _SHA64.fullmatch(ticket["intentMac"])):
        _fail()
    before, after = ticket["before"], ticket["after"]
    # A ticket cannot approve a skipped or downgraded key epoch.
    start = attest._epoch(before.get("epoch"))
    end = attest._epoch(after.get("epoch"))
    if end != start + 1:
        _fail()
    if not hmac.compare_digest(
            ticket["intentMac"], _auth(anchor, before, after)):
        _fail()
    return before, after


def _predict_after(db, previous, journal, anchor, epoch):
    """Compute future MACs from already-validated rows without writing."""
    states = []
    total = 0
    for scope in previous:
        user, account, limit, current, worst, latched, count = scope[:7]
        last = latch._GENESIS
        rows = db.execute("""SELECT * FROM offline_latch_journal
            WHERE user_id=? AND account_id=? ORDER BY seq""",
            (user, account)).fetchall()
        if len(rows) != count:
            _fail()
        for row in rows:
            last = latch._mac(
                journal, "EVENT", user, account, row["seq"],
                row["request_id"], row["kind"], row["delta_cents"],
                row["accepted"], row["current_after"], row["worst_after"],
                row["latched_after"], last)
        states.append([user, account, limit, current, worst, latched,
                       count, last,
                       latch._mac(journal, "POLICY", user, account, limit)])
        total += count
    return attest._checkpoint(states, total, anchor, epoch)


def prepare_synthetic_rotation_ticket(
        path, *, old_journal_key, new_journal_key, anchor_key, pinned,
        new_epoch):
    """Return an authenticated *proposed* before/after intent, no mutation.

    The returned ticket MUST be durably pinned outside the fixture before
    execute_synthetic_prepared_rotation is called. This function does not
    attest that such publication happened.
    """
    try:
        old, anchor = attest._keys(
            old_journal_key, anchor_key, replacement=new_journal_key)
        new = latch._key(new_journal_key)
        target = attest._epoch(new_epoch)
        with closing(latch._open(path)) as db:
            db.execute("BEGIN")
            snapshot, _, start = attest._verify_pinned(
                db, old, anchor, pinned)
            if target != start + 1:
                _fail()
            after = _predict_after(db, snapshot, new, anchor, target)
            return {"protocol": _PROTOCOL, "before": pinned,
                    "after": after, "intentMac": _auth(anchor, pinned, after)}
    except Exception:
        raise RotationTicketDenied("Offline rotation ticket unavailable") from None


def execute_synthetic_prepared_rotation(
        path, *, old_journal_key, new_journal_key, anchor_key, ticket,
        _fail_before_commit=False):
    """Execute only the exactly preauthenticated synthetic transition.

    The previously saved ticket is the external operator's responsibility.
    Failed SQLite transactions return a refusal, never half-signed journals.
    """
    try:
        old, anchor = attest._keys(
            old_journal_key, anchor_key, replacement=new_journal_key)
        before, after = _validate_ticket(ticket, anchor)
        planned = prepare_synthetic_rotation_ticket(
            path, old_journal_key=old, new_journal_key=new_journal_key,
            anchor_key=anchor, pinned=before, new_epoch=after["epoch"])
        if planned != ticket:
            _fail()
        result = attest.rotate_synthetic_journal_key(
            path, old_journal_key=old, new_journal_key=new_journal_key,
            anchor_key=anchor, pinned=before, new_epoch=after["epoch"],
            _fail_before_commit=_fail_before_commit)
        if result != after:
            _fail()
        return {"paperOnly": True, "executionEnabled": False,
                "syntheticRotationCommitted": True,
                "checkpointAwaitingExternalPromotion": after}
    except Exception:
        raise RotationTicketDenied("Offline rotation ticket unavailable") from None


def inspect_synthetic_rotation_outcome(
        path, *, old_journal_key, new_journal_key, anchor_key, ticket):
    """Reconcile a crash using an EXTERNALLY pinned rotation ticket.

    If the *new* chain verifies, it has committed. If only the old chain
    verifies, it may be a pre-commit crash OR a malicious rollback after
    commit. Never classify that old case as safe or retry automatically.
    """
    try:
        old, anchor = attest._keys(
            old_journal_key, anchor_key, replacement=new_journal_key)
        new = latch._key(new_journal_key)
        before, after = _validate_ticket(ticket, anchor)
        try:
            attest.verify_synthetic_checkpoint(
                path, journal_key=new, anchor_key=anchor, pinned=after)
            return {"paperOnly": True, "executionEnabled": False,
                    "outcome": "NEW_STATE_VERIFIED",
                    "operatorApprovalRequired": True}
        except attest.AttestedLatchDenied:
            pass
        try:
            attest.verify_synthetic_checkpoint(
                path, journal_key=old, anchor_key=anchor, pinned=before)
            return {"paperOnly": True, "executionEnabled": False,
                    "outcome": "OLD_STATE_AMBIGUOUS",
                    "operatorApprovalRequired": True}
        except attest.AttestedLatchDenied:
            _fail()
    except Exception:
        raise RotationTicketDenied("Offline rotation ticket unavailable") from None
