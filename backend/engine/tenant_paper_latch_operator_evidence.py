"""Offline-only, externally pinned synthetic latch recovery operator evidence.

Never imported by Flask, a paper-fill writer, or brokerage clients. These
signed records are proposals for INDEPENDENT durable operator publication,
not a durable store or a production authorization. A missing/stale external
latest-tip MUST fail closed. No automatic ambiguous-old-state promotion.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import hmac
import json
import re

from . import tenant_paper_latch_rehearsal as latch
from . import tenant_paper_latch_attestation as attest
from . import tenant_paper_latch_rotation_ticket as rotation

_PROTOCOL = "EDGEPILOT-SYNTHETIC-OPERATOR-EVIDENCE-v1"
_GENESIS = "0" * 64
_MAX_RECORDS = 256
_HEX = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = frozenset(("protocol", "sequence", "status", "epoch",
    "checkpoint", "journalKeyId", "nextJournalKeyId", "targetCheckpoint",
    "rotationTicketMac", "revokedKeyIds", "quarantineReason",
    "previousMac", "recordMac"))
_STATUSES = frozenset(("ACTIVE", "ROTATION_PENDING", "QUARANTINED"))
_REASONS = frozenset(("NONE", "AMBIGUOUS_OLD_STATE", "COMPROMISED_KEY",
                      "INTEGRITY_FAILURE", "OPERATOR_HOLD"))


class OperatorRecoveryDenied(ValueError):
    """Constant, nonsecret refusal for unauthenticated operator evidence."""


def _fail():
    raise OperatorRecoveryDenied("Offline recovery operator evidence unavailable")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def _operator_key(value, anchor_key):
    operator = latch._key(value)
    anchor = latch._key(anchor_key)
    if hmac.compare_digest(operator, anchor):
        _fail()
    return operator


def journal_key_id(key):
    """Nonsecret stable identifier, NOT a substitute for key revocation."""
    try:
        return hashlib.sha256(
            b"EDGEPILOT-SYNTHETIC-JOURNAL-KEY-ID-v1:" +
            latch._key(key)).hexdigest()
    except Exception:
        _fail()


def _pin(pin, anchor):
    if (type(pin) is not dict or frozenset(pin) != attest._FIELDS
            or pin.get("protocol") != attest._PROTOCOL
            or type(pin.get("accounts")) is not int
            or type(pin.get("events")) is not int
            or pin["accounts"] < 1 or pin["events"] < 0
            or not isinstance(pin.get("stateSha256"), str)
            or not isinstance(pin.get("anchorMac"), str)
            or not _HEX.fullmatch(pin["stateSha256"])
            or not _HEX.fullmatch(pin["anchorMac"])):
        _fail()
    attest._epoch(pin.get("epoch"))
    signed = hmac.new(anchor, attest._canonical([
        attest._PROTOCOL, pin["epoch"], pin["accounts"],
        pin["events"], pin["stateSha256"]]), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signed, pin["anchorMac"]):
        _fail()


def _mac(operator, record):
    return hmac.new(operator, _canonical({
        k: v for k, v in record.items() if k != "recordMac"
    }), hashlib.sha256).hexdigest()


def _tip(record):
    return {"sequence": record["sequence"], "recordMac": record["recordMac"]}


def genesis_tip():
    """Only appropriate BEFORE the operator publishes its first evidence."""
    return {"sequence": 0, "recordMac": _GENESIS}


def _review(records, *, externally_trusted_tip, operator_key, anchor_key):
    operator = _operator_key(operator_key, anchor_key)
    anchor = latch._key(anchor_key)
    if (type(records) not in (tuple, list) or not records
            or len(records) > _MAX_RECORDS):
        _fail()
    previous = None
    for position, record in enumerate(records, start=1):
        if (type(record) is not dict or frozenset(record) != _FIELDS
                or record.get("protocol") != _PROTOCOL
                or type(record.get("sequence")) is not int
                or record["sequence"] != position
                or record.get("status") not in _STATUSES
                or type(record.get("epoch")) is not int
                or not isinstance(record.get("journalKeyId"), str)
                or not _HEX.fullmatch(record["journalKeyId"])
                or not isinstance(record.get("nextJournalKeyId"), str)
                or not isinstance(record.get("rotationTicketMac"), str)
                or not isinstance(record.get("previousMac"), str)
                or not isinstance(record.get("recordMac"), str)
                or not _HEX.fullmatch(record["previousMac"])
                or not _HEX.fullmatch(record["recordMac"])
                or record["previousMac"] != (
                    previous["recordMac"] if previous else _GENESIS)
                or not hmac.compare_digest(record["recordMac"],
                                          _mac(operator, record))):
            _fail()
        _pin(record["checkpoint"], anchor)
        if record["epoch"] != record["checkpoint"]["epoch"]:
            _fail()
        revoked = record.get("revokedKeyIds")
        if (type(revoked) is not list or len(revoked) > 32
                or any(type(k) is not str or not _HEX.fullmatch(k)
                       for k in revoked)
                or revoked != sorted(set(revoked))):
            _fail()
        if record["status"] == "ROTATION_PENDING":
            if (not _HEX.fullmatch(record["nextJournalKeyId"])
                    or record["nextJournalKeyId"] == record["journalKeyId"]
                    or not _HEX.fullmatch(record["rotationTicketMac"])
                    or type(record["targetCheckpoint"]) is not dict):
                _fail()
            _pin(record["targetCheckpoint"], anchor)
            if record["targetCheckpoint"]["epoch"] != record["epoch"] + 1:
                _fail()
        elif (record["nextJournalKeyId"] != ""
              or record["rotationTicketMac"] != ""
              or record["targetCheckpoint"] is not None):
            _fail()
        if record["status"] == "QUARANTINED":
            if record.get("quarantineReason") not in _REASONS - {"NONE"}:
                _fail()
        elif record.get("quarantineReason") != "NONE":
            _fail()
        if record["status"] != "QUARANTINED" and (
                record["journalKeyId"] in revoked or
                record["nextJournalKeyId"] in revoked):
            _fail()
        if previous is None:
            if record["status"] != "ACTIVE" or record["epoch"] != 1 or revoked:
                _fail()
        else:
            if (previous["status"] == "QUARANTINED"
                    or not set(previous["revokedKeyIds"]).issubset(revoked)):
                _fail()
            old = previous["checkpoint"]
            if record["status"] == "QUARANTINED":
                if (record["checkpoint"] != old
                        or record["journalKeyId"] != previous["journalKeyId"]
                        or record["epoch"] != previous["epoch"]):
                    _fail()
            elif previous["status"] == "ACTIVE":
                if (record["journalKeyId"] != previous["journalKeyId"]
                        or record["epoch"] != previous["epoch"]
                        or revoked != previous["revokedKeyIds"]):
                    _fail()
                if record["status"] == "ROTATION_PENDING":
                    if record["checkpoint"] != old:
                        _fail()
                elif record["status"] == "ACTIVE":
                    current = record["checkpoint"]
                    if (current["accounts"] != old["accounts"]
                            or current["events"] < old["events"]
                            or (current["events"] == old["events"]
                                and current != old)):
                        _fail()
                else:
                    _fail()
            elif previous["status"] == "ROTATION_PENDING":
                if (record["status"] != "ACTIVE"
                        or record["checkpoint"] != previous["targetCheckpoint"]
                        or record["journalKeyId"] != previous["nextJournalKeyId"]
                        or record["epoch"] != previous["epoch"] + 1
                        or record["checkpoint"]["events"]
                            != old["events"]
                        or record["checkpoint"]["accounts"]
                            != old["accounts"]
                        or revoked != previous["revokedKeyIds"]):
                    _fail()
            else:
                _fail()
        previous = record
    if (type(externally_trusted_tip) is not dict
            or frozenset(externally_trusted_tip) !=
                frozenset(("sequence", "recordMac"))
            or externally_trusted_tip != _tip(previous)):
        _fail()
    return previous


def verify_synthetic_operator_evidence(
        records, *, externally_trusted_tip, operator_key, anchor_key):
    """Authenticate the COMPLETE chain against a separately held latest tip.

    This only attests the records, not a fixture or independent publication.
    """
    try:
        final = _review(
            records, externally_trusted_tip=externally_trusted_tip,
            operator_key=operator_key, anchor_key=anchor_key)
        return {"paperOnly": True, "executionEnabled": False,
                "evidenceVerified": True, "sequence": final["sequence"],
                "epoch": final["epoch"], "status": final["status"],
                "operatorApprovalRequired": True}
    except Exception:
        _fail()


def propose_synthetic_operator_record(
        path, *, records, externally_trusted_tip, operator_key, anchor_key,
        journal_key, checkpoint, status, rotation_ticket=None,
        next_journal_key=None, newly_revoked_key_ids=(),
        quarantine_reason="NONE"):
    """Return a signed PROPOSAL. Caller must publish/pin it independently.

    A pending->active proposal requires the exactly predicted new checkpoint
    and independently verifiable NEW database. An ambiguous OLD database
    cannot be promoted, even if a prepared ticket authenticates it.
    """
    try:
        operator = _operator_key(operator_key, anchor_key)
        journal, anchor = attest._keys(journal_key, anchor_key)
        if hmac.compare_digest(operator, journal):
            _fail()
        _pin(checkpoint, anchor)
        prior = None
        if records:
            prior = _review(records, externally_trusted_tip=externally_trusted_tip,
                            operator_key=operator, anchor_key=anchor)
        elif records != [] or externally_trusted_tip != genesis_tip():
            _fail()
        if status not in _STATUSES:
            _fail()
        current_id = journal_key_id(journal)
        key_id = current_id
        next_id, target, ticket_mac = "", None, ""
        revoked = list(prior["revokedKeyIds"]) if prior else []
        if (type(newly_revoked_key_ids) not in (tuple, list)
                or any(type(k) is not str or not _HEX.fullmatch(k)
                       for k in newly_revoked_key_ids)):
            _fail()
        revoked = sorted(set(revoked) | set(newly_revoked_key_ids))
        if status == "QUARANTINED":
            if not prior or checkpoint != prior["checkpoint"]:
                _fail()
            key_id = prior["journalKeyId"]
        elif status == "ACTIVE":
            if newly_revoked_key_ids or quarantine_reason != "NONE":
                _fail()
            if prior and prior["status"] == "ROTATION_PENDING":
                if (rotation_ticket is None
                        or rotation_ticket.get("intentMac")
                            != prior["rotationTicketMac"]
                        or rotation_ticket.get("before")
                            != prior["checkpoint"]
                        or rotation_ticket.get("after")
                            != prior["targetCheckpoint"]
                        or checkpoint != prior["targetCheckpoint"]
                        or current_id != prior["nextJournalKeyId"]):
                    _fail()
                rotation._validate_ticket(rotation_ticket, anchor)
            elif rotation_ticket is not None or next_journal_key is not None:
                _fail()
            attest.verify_synthetic_checkpoint(
                path, journal_key=journal, anchor_key=anchor,
                pinned=checkpoint)
        elif status == "ROTATION_PENDING":
            if (not prior or prior["status"] != "ACTIVE"
                    or checkpoint != prior["checkpoint"]
                    or current_id != prior["journalKeyId"]
                    or next_journal_key is None
                    or rotation_ticket is None
                    or newly_revoked_key_ids
                    or quarantine_reason != "NONE"):
                _fail()
            old, after = rotation._validate_ticket(rotation_ticket, anchor)
            if old != checkpoint:
                _fail()
            new = latch._key(next_journal_key)
            if any(hmac.compare_digest(new, k)
                   for k in (journal, anchor, operator)):
                _fail()
            attest.verify_synthetic_checkpoint(
                path, journal_key=journal, anchor_key=anchor,
                pinned=checkpoint)
            next_id = journal_key_id(new)
            target, ticket_mac = after, rotation_ticket["intentMac"]
        record = {
            "protocol": _PROTOCOL, "sequence": len(records) + 1,
            "status": status, "epoch": checkpoint["epoch"],
            "checkpoint": checkpoint, "journalKeyId": key_id,
            "nextJournalKeyId": next_id, "targetCheckpoint": target,
            "rotationTicketMac": ticket_mac, "revokedKeyIds": revoked,
            "quarantineReason": quarantine_reason,
            "previousMac": (prior["recordMac"] if prior else _GENESIS)}
        record["recordMac"] = _mac(operator, record)
        trial = list(records) + [record]
        _review(trial, externally_trusted_tip=_tip(record),
                operator_key=operator, anchor_key=anchor)
        return {"record": record, "proposedLatestTip": _tip(record),
                "operatorMustPublishIndependently": True,
                "executionEnabled": False}
    except Exception:
        _fail()


def inspect_synthetic_recovery_candidate(
        path, *, records, externally_trusted_tip, operator_key, anchor_key,
        journal_key, rotation_ticket=None, next_journal_key=None):
    """Read-only disposition; NEVER approval for paper fills or trading."""
    try:
        current = _review(records, externally_trusted_tip=externally_trusted_tip,
                          operator_key=operator_key, anchor_key=anchor_key)
        journal, anchor = attest._keys(journal_key, anchor_key)
        operator = _operator_key(operator_key, anchor)
        if hmac.compare_digest(operator, journal):
            _fail()
        disposition = None
        if current["status"] == "QUARANTINED":
            disposition = "QUARANTINED_NO_RESTORE"
        elif (journal_key_id(journal) != current["journalKeyId"]
              or current["journalKeyId"] in current["revokedKeyIds"]):
            _fail()
        elif current["status"] == "ACTIVE":
            if rotation_ticket is not None or next_journal_key is not None:
                _fail()
            attest.verify_synthetic_checkpoint(
                path, journal_key=journal, anchor_key=anchor,
                pinned=current["checkpoint"])
            disposition = "PINNED_STATE_VERIFIED_NO_ACTIVATION"
        else:
            if rotation_ticket is None or next_journal_key is None:
                _fail()
            if (rotation_ticket.get("intentMac")
                    != current["rotationTicketMac"]
                    or rotation_ticket.get("before")
                    != current["checkpoint"]
                    or rotation_ticket.get("after")
                    != current["targetCheckpoint"]
                    or journal_key_id(next_journal_key)
                    != current["nextJournalKeyId"]):
                _fail()
            result = rotation.inspect_synthetic_rotation_outcome(
                path, old_journal_key=journal,
                new_journal_key=next_journal_key, anchor_key=anchor,
                ticket=rotation_ticket)
            disposition = (
                "NEW_STATE_NEEDS_INDEPENDENT_PROMOTION"
                if result["outcome"] == "NEW_STATE_VERIFIED"
                else "OLD_STATE_AMBIGUOUS_QUARANTINE")
        return {"paperOnly": True, "executionEnabled": False,
                "productionPaperFillsEnabled": False,
                "operatorApprovalRequired": True,
                "evidenceSequence": current["sequence"],
                "epoch": current["epoch"], "disposition": disposition}
    except Exception:
        _fail()
