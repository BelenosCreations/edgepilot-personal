"""Disposable, staging-only operator invitation bootstrap.

A high-entropy secret is entered into a same-origin form, never sent in a URL,
stored in JavaScript storage, printed to logs, or committed to source. Render
stores only its SHA-256 digest. Exactly two one-use tenant invitations can be
minted per ephemeral staging database; no brokerage, admin or trading role.
This is not a production member provisioning service.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import sqlite3
import time
from pathlib import Path

from . import tenant_registration

_TOKEN_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{43}$")
_DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_MAX_FAILS = 6
_ATTEMPT_WINDOW = 900


class StagingOperatorDenied(PermissionError):
    pass


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def setup(path):
    db_path = Path(path)
    with sqlite3.connect(str(db_path), timeout=20) as db:
        db.execute("PRAGMA busy_timeout=20000")
        # Fail closed if invitation-only registration was not prepared.
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                          "AND name='tenant_signup_invites'").fetchone():
            raise StagingOperatorDenied("Staging operator is unavailable")
        db.execute("""CREATE TABLE IF NOT EXISTS staging_operator_issued(
            slot INTEGER PRIMARY KEY CHECK(slot IN (1,2)),
            issued_at INTEGER NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS staging_operator_failed(
            source_hash TEXT NOT NULL,
            at_seconds INTEGER NOT NULL
        )""")
        db.execute("""CREATE INDEX IF NOT EXISTS idx_staging_failed_window
            ON staging_operator_failed(source_hash,at_seconds)""")


def issue_two(path, provided_token, expected_digest, *, source, now=None):
    """Mint two *member* invites only after 256-bit token verification.

    Invalid tokens consume an attempt budget. Successful issuance consumes
    both available slots; a repeated request cannot mint more invitations.
    The 1-hour invitations are returned once for temporary device testing.
    """
    if (not isinstance(expected_digest, str)
            or _DIGEST_PATTERN.fullmatch(expected_digest) is None):
        raise StagingOperatorDenied("Staging operator is unavailable")
    moment = int(time.time()) if now is None else now
    if type(moment) is not int or not 0 <= moment <= 253402300799:
        raise StagingOperatorDenied("Staging operator is unavailable")
    setup(path)
    allowed = (isinstance(provided_token, str)
               and _TOKEN_PATTERN.fullmatch(provided_token) is not None
               and hmac.compare_digest(_hash(provided_token), expected_digest))
    source_digest = _hash(str(source)[:120] or "unknown")
    with sqlite3.connect(str(path), timeout=20) as db:
        db.execute("PRAGMA busy_timeout=20000")
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM staging_operator_failed WHERE at_seconds<?",
                   (moment - _ATTEMPT_WINDOW,))
        attempts = db.execute("""SELECT COUNT(*) FROM staging_operator_failed
            WHERE source_hash=? AND at_seconds>=?""",
            (source_digest, moment - _ATTEMPT_WINDOW)).fetchone()[0]
        if attempts >= _MAX_FAILS:
            failed = True
        elif not allowed:
            db.execute("""INSERT INTO staging_operator_failed(source_hash,at_seconds)
                VALUES(?,?)""", (source_digest, moment))
            failed = True
        else:
            failed = False
            issued = db.execute(
                "SELECT COUNT(*) FROM staging_operator_issued").fetchone()[0]
            if issued != 0:
                failed = True
            else:
                db.executemany(
                    "INSERT INTO staging_operator_issued(slot,issued_at) VALUES(?,?)",
                    ((1, moment), (2, moment)),
                )
    if failed:
        raise StagingOperatorDenied("Staging operator is unavailable")
    # Slots were reserved atomically in the same DB, so concurrent bootstrap
    # calls cannot exceed the fixed test-only cap. A rare error burns a slot
    # rather than issuing unlimited invitations (fail-closed by design).
    register = tenant_registration.TenantRegistration(str(path))
    try:
        invitations = [
            register.issue_invitation(ttl_seconds=3600, now=moment)["invitation"]
            for _ in range(2)
        ]
    except (RuntimeError, sqlite3.Error, tenant_registration.RegistrationDenied):
        raise StagingOperatorDenied("Staging operator is unavailable") from None
    return {"invitations": invitations, "expiresInSeconds": 3600,
            "maxTestUsers": 2, "syntheticOnly": True,
            "publicBrokerageEnabled": False, "tradingEnabled": False}
