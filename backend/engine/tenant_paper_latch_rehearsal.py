"""Synthetic-only atomic paper loss-stop latch protocol rehearsal.

Not imported by app.py or the fill writer. Only new, 0600 SQLite fixtures
under verified Linux /dev/shm are eligible. A caller-held HMAC key authenticates
the policy, journal and state. This does NOT authorize real or paper execution.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import stat
from urllib.parse import quote as url_quote
import uuid

from . import shadow_storage

_MAGIC = "EDGEPILOT-OFFLINE-SYNTHETIC-LATCH-v1"
_GENESIS = "0" * 64
_MAX_CENTS = 100_000_000_000


class PaperLatchDenied(ValueError):
    """Fixed, nonsecret refusal for isolated rehearsal failures."""


def _uuid(value):
    if not isinstance(value, str):
        raise PaperLatchDenied("Offline latch integrity unavailable")
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise PaperLatchDenied("Offline latch integrity unavailable") from None
    return value


def _key(value):
    if not isinstance(value, bytes) or not 32 <= len(value) <= 128:
        raise PaperLatchDenied("Offline latch integrity unavailable")
    return value


def _mac(key, *parts):
    payload = json.dumps(parts, separators=(",", ":"), ensure_ascii=True)
    return hmac.new(key, payload.encode("ascii"), hashlib.sha256).hexdigest()


def _cents(value, *, positive=False):
    if type(value) is not int or abs(value) > _MAX_CENTS or (
            positive and value <= 0):
        raise PaperLatchDenied("Offline latch integrity unavailable")
    return value


def _file(path):
    root = shadow_storage.memory_root()
    raw = Path(path)
    if raw.is_symlink():
        raise PaperLatchDenied("Offline latch integrity unavailable")
    resolved = raw.resolve(strict=True)
    info = resolved.stat()
    if (root not in resolved.parents or not stat.S_ISREG(info.st_mode)
            or info.st_dev != root.stat().st_dev
            or info.st_uid != os.getuid() or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600):
        raise PaperLatchDenied("Offline latch integrity unavailable")
    return resolved


def _open(path):
    source = _file(path)
    uri = "file:" + url_quote(str(source), safe="/") + "?mode=rw"
    db = sqlite3.connect(uri, uri=True, timeout=5, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        row = db.execute("SELECT label FROM offline_latch_marker WHERE id=1").fetchone()
        if row is None or row["label"] != _MAGIC:
            raise PaperLatchDenied("Offline latch integrity unavailable")
        return db
    except Exception:
        db.close()
        raise


def create_synthetic_fixture(path):
    """Create a NEW, non-overwriting isolated scratch database; never migrate."""
    created = False
    try:
        root = shadow_storage.memory_root()
        target = Path(path)
        parent = target.parent.resolve(strict=True)
        if (parent != root and root not in parent.parents) or target.name in (
                "", ".", ".."):
            raise PaperLatchDenied("Offline latch integrity unavailable")
        fd = os.open(str(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                     0o600)
        os.close(fd)
        created = True
        with closing(sqlite3.connect(str(target), isolation_level=None)) as db:
            db.executescript("""
                PRAGMA journal_mode=DELETE;
                CREATE TABLE offline_latch_marker (
                    id INTEGER PRIMARY KEY CHECK(id=1), label TEXT NOT NULL);
                CREATE TABLE offline_latch_policies (
                    user_id TEXT NOT NULL, account_id TEXT NOT NULL,
                    max_loss_cents INTEGER NOT NULL,
                    current_cents INTEGER NOT NULL, worst_cents INTEGER NOT NULL,
                    latched INTEGER NOT NULL, seq INTEGER NOT NULL,
                    last_mac TEXT NOT NULL, policy_mac TEXT NOT NULL,
                    PRIMARY KEY(user_id,account_id));
                CREATE TABLE offline_latch_journal (
                    user_id TEXT NOT NULL, account_id TEXT NOT NULL,
                    seq INTEGER NOT NULL, request_id TEXT NOT NULL,
                    kind TEXT NOT NULL, delta_cents INTEGER NOT NULL,
                    accepted INTEGER NOT NULL, current_after INTEGER NOT NULL,
                    worst_after INTEGER NOT NULL, latched_after INTEGER NOT NULL,
                    previous_mac TEXT NOT NULL, entry_mac TEXT NOT NULL,
                    PRIMARY KEY(user_id,account_id,seq),
                    UNIQUE(user_id,account_id,request_id));
            """)
            db.execute("INSERT INTO offline_latch_marker VALUES(1,?)", (_MAGIC,))
        return target
    except Exception:
        if created:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass
        raise PaperLatchDenied("Offline latch integrity unavailable") from None


def _replay(db, key, user, account, policy):
    limit = policy["max_loss_cents"]
    _cents(limit, positive=True)
    if not hmac.compare_digest(
            str(policy["policy_mac"]), _mac(key, "POLICY", user, account, limit)):
        raise PaperLatchDenied("Offline latch integrity unavailable")
    current = worst = latched = 0
    previous = _GENESIS
    rows = db.execute("""SELECT * FROM offline_latch_journal
        WHERE user_id=? AND account_id=? ORDER BY seq""", (user, account))
    count = 0
    for row in rows:
        count += 1
        seq, request_id, kind = row["seq"], row["request_id"], row["kind"]
        delta, allowed = row["delta_cents"], row["accepted"]
        if (type(seq) is not int or seq != count
                or _uuid(request_id) != request_id
                or kind not in ("OPEN", "REALIZE")
                or row["previous_mac"] != previous):
            raise PaperLatchDenied("Offline latch integrity unavailable")
        _cents(delta)
        if kind == "OPEN":
            if delta != 0:
                raise PaperLatchDenied("Offline latch integrity unavailable")
            accepted = int(not latched)
        else:
            accepted = 1  # Record simulated realized losses even if latched.
            current = _cents(current + delta)
            worst = min(worst, current)
            if worst <= -limit:
                latched = 1
        expected_mac = _mac(key, "EVENT", user, account, seq,
                            request_id, kind, delta, accepted, current,
                            worst, latched, previous)
        if (allowed != accepted or row["current_after"] != current
                or row["worst_after"] != worst
                or row["latched_after"] != latched
                or not isinstance(row["entry_mac"], str)
                or not hmac.compare_digest(row["entry_mac"], expected_mac)):
            raise PaperLatchDenied("Offline latch integrity unavailable")
        previous = expected_mac
    if (policy["seq"] != count or policy["current_cents"] != current
            or policy["worst_cents"] != worst or policy["latched"] != latched
            or policy["last_mac"] != previous):
        raise PaperLatchDenied("Offline latch integrity unavailable")
    return count, current, worst, latched, previous


def register_synthetic_policy(path, *, hmac_key, principal_user_id,
                              account_id, max_loss_cents):
    """No policy resets or threshold changes; external test identities only."""
    key = _key(hmac_key)
    user, account = _uuid(principal_user_id), _uuid(account_id)
    limit = _cents(max_loss_cents, positive=True)
    try:
        with closing(_open(path)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                policy = db.execute("""SELECT * FROM offline_latch_policies
                    WHERE user_id=? AND account_id=?""", (user, account)).fetchone()
                if policy:
                    _replay(db, key, user, account, policy)
                    if policy["max_loss_cents"] != limit:
                        raise PaperLatchDenied("Offline latch integrity unavailable")
                    duplicate = True
                else:
                    db.execute("""INSERT INTO offline_latch_policies
                        VALUES(?,?,?,?,?,?,?,?,?)""",
                        (user, account, limit, 0, 0, 0, 0, _GENESIS,
                         _mac(key, "POLICY", user, account, limit)))
                    duplicate = False
                db.commit()
                return {"paperOnly": True, "registered": not duplicate}
            except Exception:
                db.rollback()
                raise
    except Exception:
        raise PaperLatchDenied("Offline latch integrity unavailable") from None


def inspect_synthetic_policy(path, *, hmac_key, principal_user_id, account_id):
    key = _key(hmac_key)
    user, account = _uuid(principal_user_id), _uuid(account_id)
    try:
        with closing(_open(path)) as db:
            db.execute("BEGIN")
            policy = db.execute("""SELECT * FROM offline_latch_policies
                WHERE user_id=? AND account_id=?""", (user, account)).fetchone()
            if policy is None:
                raise PaperLatchDenied("Offline latch integrity unavailable")
            count, current, worst, latched, _ = _replay(
                db, key, user, account, policy)
            return {"paperOnly": True, "executionEnabled": False,
                    "atomicFillEnforcementActive": False,
                    "journalEntries": count, "maxLossCents": policy["max_loss_cents"],
                    "currentRealizedCents": current,
                    "worstHistoricalRealizedCents": worst,
                    "durableSyntheticLatch": bool(latched)}
    except Exception:
        raise PaperLatchDenied("Offline latch integrity unavailable") from None


def rehearse_atomic_request(path, *, hmac_key, principal_user_id, account_id,
                            request_id, kind, realized_delta_cents=0,
                            _fail_before_commit=False):
    """Atomically journal an advisory OPEN or simulated REALIZE update.

    OPEN is only a simulated decision, never a fill. REALIZE represents
    an externally assumed close/result, not a trade or market-data event.
    This is intentionally NOT wired to tenant_paper_ledger.record_paper_fill.
    """
    key = _key(hmac_key)
    user, account, req = (_uuid(principal_user_id), _uuid(account_id),
                          _uuid(request_id))
    if kind not in ("OPEN", "REALIZE"):
        raise PaperLatchDenied("Offline latch integrity unavailable")
    delta = _cents(realized_delta_cents)
    if kind == "OPEN" and delta != 0:
        raise PaperLatchDenied("Offline latch integrity unavailable")
    try:
        with closing(_open(path)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                policy = db.execute("""SELECT * FROM offline_latch_policies
                    WHERE user_id=? AND account_id=?""", (user, account)).fetchone()
                if policy is None:
                    raise PaperLatchDenied("Offline latch integrity unavailable")
                count, current, worst, latched, previous = _replay(
                    db, key, user, account, policy)
                prior = db.execute("""SELECT kind,delta_cents,accepted
                    FROM offline_latch_journal WHERE user_id=? AND account_id=?
                    AND request_id=?""", (user, account, req)).fetchone()
                if prior:
                    if prior["kind"] != kind or prior["delta_cents"] != delta:
                        raise PaperLatchDenied("Offline latch integrity unavailable")
                    db.commit()
                    return {"paperOnly": True, "executionEnabled": False,
                            "duplicate": True, "simulatedAccepted": bool(prior["accepted"]),
                            "durableSyntheticLatch": bool(latched)}
                accepted = 1
                if kind == "OPEN":
                    accepted = int(not latched)
                else:
                    current = _cents(current + delta)
                    worst = min(worst, current)
                    if worst <= -policy["max_loss_cents"]:
                        latched = 1
                seq = count + 1
                digest = _mac(key, "EVENT", user, account, seq, req, kind,
                              delta, accepted, current, worst, latched, previous)
                db.execute("""INSERT INTO offline_latch_journal
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (user, account, seq, req, kind, delta, accepted,
                     current, worst, latched, previous, digest))
                db.execute("""UPDATE offline_latch_policies SET
                    current_cents=?, worst_cents=?, latched=?, seq=?, last_mac=?
                    WHERE user_id=? AND account_id=?""",
                    (current, worst, latched, seq, digest, user, account))
                if _fail_before_commit:
                    raise RuntimeError("Injected offline crash boundary")
                db.commit()
                return {"paperOnly": True, "executionEnabled": False,
                        "duplicate": False, "simulatedAccepted": bool(accepted),
                        "durableSyntheticLatch": bool(latched)}
            except Exception:
                db.rollback()
                raise
    except Exception:
        raise PaperLatchDenied("Offline latch integrity unavailable") from None
