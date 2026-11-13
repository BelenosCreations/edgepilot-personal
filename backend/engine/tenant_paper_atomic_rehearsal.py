"""Offline-only atomic synthetic paper accounting + sticky loss-stop rehearsal.

UNLICENSED SYNTHETIC NUMBERS ONLY: all prices and unit counts are supplied by
unit tests. This module never imports a broker, Flask app, real tenant
database or dormant production paper-fill writer. It deliberately models
WHOLE UNITS, not the production Decimal/fractional-quantity contract.
Every cash, position, realized-P&L, idempotency and stop update occurs in
one BEGIN IMMEDIATE transaction in a NEW verified /dev/shm SQLite fixture.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote as url_quote

from . import shadow_storage
from . import tenant_paper_latch_rehearsal as isolated

_MAGIC = "EDGEPILOT-OFFLINE-ATOMIC-PAPER-v1"
_GENESIS = "0" * 64
_MAX_CENTS = 100_000_000_000
_MAX_QTY = 10_000_000
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,19}$")
_HEX = re.compile(r"^[0-9a-f]{64}$")
_ASSETS = frozenset(("stock", "etf", "crypto"))
_TABLES = frozenset(("offline_atomic_marker", "offline_atomic_wallets",
                    "offline_atomic_positions", "offline_atomic_events"))
_EVENT_FIELDS = ("user_id", "account_id", "seq", "request_id",
                 "request_sha256", "side", "asset_class", "symbol",
                 "qty_units", "unit_price_cents", "fee_cents",
                 "cash_after_cents", "realized_after_cents",
                 "worst_after_cents", "stopped_after", "position_qty_after",
                 "position_basis_after", "position_realized_after",
                 "previous_mac")
_PIN_PROTOCOL = "EDGEPILOT-OFFLINE-ATOMIC-PAPER-PIN-v1"
_PIN_FIELDS = frozenset(("protocol", "epoch", "accounts", "events",
                         "stateSha256", "anchorMac"))


class AtomicPaperDenied(ValueError):
    """Nonsecret refusal; never includes a filename, account, or key."""


def _fail():
    raise AtomicPaperDenied("Offline atomic paper rehearsal unavailable")


def _canonical(value):
    return json.dumps(value, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def _mac(key, *parts):
    return hmac.new(key, _canonical(parts), hashlib.sha256).hexdigest()


def _integer(value, *, lower=0, upper=_MAX_CENTS):
    if type(value) is not int or not lower <= value <= upper:
        _fail()
    return value


def _keys(journal_key, anchor_key=None):
    journal = isolated._key(journal_key)
    if anchor_key is None:
        return journal
    anchor = isolated._key(anchor_key)
    if hmac.compare_digest(journal, anchor):
        _fail()
    return journal, anchor


def _identity(user, account):
    return isolated._uuid(user), isolated._uuid(account)


def _file(path):
    return isolated._file(path)


def _open(path):
    source = _file(path)
    uri = "file:" + url_quote(str(source), safe="/") + "?mode=rw"
    db = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys=ON")
        marker = db.execute(
            "SELECT label FROM offline_atomic_marker WHERE id=1").fetchone()
        if marker is None or marker["label"] != _MAGIC:
            _fail()
        entries = db.execute("""SELECT name,type FROM sqlite_master
            WHERE type IN ('table','view','trigger')""").fetchall()
        if (frozenset(row["name"] for row in entries) != _TABLES
                or any(row["type"] != "table" for row in entries)
                or db.execute("PRAGMA journal_mode").fetchone()[0].lower()
                != "delete"):
            _fail()
        return db
    except Exception:
        db.close()
        raise


def create_synthetic_atomic_fixture(path):
    """Never opens, migrates, overwrites or modifies a real tenant database."""
    created = False
    try:
        root = shadow_storage.memory_root()
        target = Path(path)
        parent = target.parent.resolve(strict=True)
        if (target.name in ("", ".", "..") or parent != target.parent
                or (parent != root and root not in parent.parents)):
            _fail()
        fd = os.open(str(target),
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600)
        os.close(fd)
        created = True
        with closing(sqlite3.connect(str(target), isolation_level=None)) as db:
            db.executescript("""
                PRAGMA journal_mode=DELETE;
                PRAGMA foreign_keys=ON;
                CREATE TABLE offline_atomic_marker (
                    id INTEGER PRIMARY KEY CHECK(id=1), label TEXT NOT NULL);
                CREATE TABLE offline_atomic_wallets (
                    user_id TEXT NOT NULL, account_id TEXT NOT NULL,
                    seeded_cents INTEGER NOT NULL CHECK(seeded_cents>0),
                    cash_cents INTEGER NOT NULL CHECK(cash_cents>=0),
                    protected_pct INTEGER NOT NULL
                      CHECK(protected_pct BETWEEN 0 AND 99),
                    spend_cap_cents INTEGER NOT NULL CHECK(spend_cap_cents>0),
                    per_trade_cap_cents INTEGER NOT NULL CHECK(per_trade_cap_cents>0),
                    max_loss_cents INTEGER NOT NULL CHECK(max_loss_cents>0),
                    realized_cents INTEGER NOT NULL,
                    worst_cents INTEGER NOT NULL CHECK(worst_cents<=0),
                    stopped INTEGER NOT NULL CHECK(stopped IN (0,1)),
                    seq INTEGER NOT NULL CHECK(seq>=0),
                    last_mac TEXT NOT NULL, policy_mac TEXT NOT NULL,
                    state_mac TEXT NOT NULL,
                    PRIMARY KEY(user_id,account_id));
                CREATE TABLE offline_atomic_positions (
                    user_id TEXT NOT NULL, account_id TEXT NOT NULL,
                    asset_class TEXT NOT NULL, symbol TEXT NOT NULL,
                    qty_units INTEGER NOT NULL CHECK(qty_units>=0),
                    basis_cents INTEGER NOT NULL CHECK(basis_cents>=0),
                    realized_cents INTEGER NOT NULL,
                    PRIMARY KEY(user_id,account_id,asset_class,symbol),
                    FOREIGN KEY(user_id,account_id)
                      REFERENCES offline_atomic_wallets(user_id,account_id));
                CREATE TABLE offline_atomic_events (
                    user_id TEXT NOT NULL, account_id TEXT NOT NULL,
                    seq INTEGER NOT NULL, request_id TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL, side TEXT NOT NULL,
                    asset_class TEXT NOT NULL, symbol TEXT NOT NULL,
                    qty_units INTEGER NOT NULL, unit_price_cents INTEGER NOT NULL,
                    fee_cents INTEGER NOT NULL, cash_after_cents INTEGER NOT NULL,
                    realized_after_cents INTEGER NOT NULL,
                    worst_after_cents INTEGER NOT NULL,
                    stopped_after INTEGER NOT NULL,
                    position_qty_after INTEGER NOT NULL,
                    position_basis_after INTEGER NOT NULL,
                    position_realized_after INTEGER NOT NULL,
                    previous_mac TEXT NOT NULL, entry_mac TEXT NOT NULL,
                    PRIMARY KEY(user_id,account_id,seq),
                    UNIQUE(user_id,account_id,request_id),
                    FOREIGN KEY(user_id,account_id)
                      REFERENCES offline_atomic_wallets(user_id,account_id));
                INSERT INTO offline_atomic_marker VALUES
                    (1,'EDGEPILOT-OFFLINE-ATOMIC-PAPER-v1');
            """)
        return target
    except Exception:
        if created:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass
        _fail()


def _policy_mac(key, wallet):
    return _mac(key, "POLICY", wallet["user_id"], wallet["account_id"],
                wallet["seeded_cents"], wallet["protected_pct"],
                wallet["spend_cap_cents"], wallet["per_trade_cap_cents"],
                wallet["max_loss_cents"])


def _state_mac(key, wallet, position_list):
    return _mac(key, "STATE", wallet["user_id"], wallet["account_id"],
                wallet["cash_cents"], wallet["realized_cents"],
                wallet["worst_cents"], wallet["stopped"], wallet["seq"],
                wallet["last_mac"], position_list)


def _position_list(db, user, account):
    return [[r["asset_class"], r["symbol"], r["qty_units"],
             r["basis_cents"], r["realized_cents"]]
            for r in db.execute("""SELECT * FROM offline_atomic_positions
                WHERE user_id=? AND account_id=?
                ORDER BY asset_class,symbol""", (user, account))]


def _request_hash(request_id, side, asset, symbol, qty, price, fee):
    return hashlib.sha256(_canonical([
        "ASSUMED-SYNTHETIC-FILL", request_id, side, asset,
        symbol, qty, price, fee])).hexdigest()


def _inputs(side, asset, symbol, quantity, price, fee):
    if (side not in ("BUY", "SELL") or asset not in _ASSETS
            or type(symbol) is not str or not _SYMBOL.fullmatch(symbol)):
        _fail()
    qty = _integer(quantity, lower=1, upper=_MAX_QTY)
    unit = _integer(price, lower=1)
    friction = _integer(fee)
    if qty * unit + friction > _MAX_CENTS:
        _fail()
    return qty, unit, friction


def _transition(policy, positions, cash, realized, worst, stopped,
                side, asset, symbol, qty, price, fee):
    """Deterministic exact-integer state transition; no broker price or fill."""
    old = positions.get((asset, symbol), [0, 0, 0])
    own_qty, basis, own_realized = old
    if side == "BUY":
        if stopped:
            _fail()
        cost = qty * price + fee
        exposure = sum(p[1] for p in positions.values())
        allowed_exposure = min(
            policy["seeded_cents"] * (100-policy["protected_pct"]) // 100,
            policy["spend_cap_cents"])
        if (cost > policy["per_trade_cap_cents"] or cost > cash
                or exposure + cost > allowed_exposure
                or basis + cost > _MAX_CENTS or own_qty + qty > _MAX_QTY):
            _fail()
        cash -= cost
        new_position = [own_qty + qty, basis + cost, own_realized]
        delta = 0
    else:
        if qty > own_qty or own_qty <= 0:
            _fail()
        proceeds = qty * price - fee
        if proceeds <= 0 or cash + proceeds > _MAX_CENTS:
            _fail()
        released = (basis if qty == own_qty else
                    (basis * qty + own_qty - 1) // own_qty)
        delta = proceeds - released
        realized += delta
        if abs(realized) > _MAX_CENTS:
            _fail()
        worst = min(worst, realized)
        if worst <= -policy["max_loss_cents"]:
            stopped = 1
        cash += proceeds
        new_position = [own_qty - qty, basis - released, own_realized + delta]
    if abs(worst) > _MAX_CENTS or abs(new_position[2]) > _MAX_CENTS:
        _fail()
    positions[(asset, symbol)] = new_position
    return cash, realized, worst, stopped, new_position, delta


def _audit_scope(db, key, user, account):
    wallet = db.execute("""SELECT * FROM offline_atomic_wallets
        WHERE user_id=? AND account_id=?""", (user, account)).fetchone()
    if wallet is None:
        _fail()
    if (_identity(wallet["user_id"], wallet["account_id"]) != (user, account)
            or not hmac.compare_digest(str(wallet["policy_mac"]),
                                       _policy_mac(key, wallet))):
        _fail()
    _integer(wallet["seeded_cents"], lower=1)
    _integer(wallet["protected_pct"], upper=99)
    _integer(wallet["spend_cap_cents"], lower=1)
    _integer(wallet["per_trade_cap_cents"], lower=1)
    _integer(wallet["max_loss_cents"], lower=1)
    positions = {}
    cash, realized, worst, stopped = wallet["seeded_cents"], 0, 0, 0
    previous, count = _GENESIS, 0
    for event in db.execute("""SELECT * FROM offline_atomic_events
        WHERE user_id=? AND account_id=? ORDER BY seq""", (user, account)):
        count += 1
        if (type(event["seq"]) is not int or event["seq"] != count
                or _identity(event["user_id"], event["account_id"])
                    != (user, account)
                or isolated._uuid(event["request_id"]) != event["request_id"]
                or event["previous_mac"] != previous):
            _fail()
        qty, price, fee = _inputs(
            event["side"], event["asset_class"], event["symbol"],
            event["qty_units"], event["unit_price_cents"], event["fee_cents"])
        expected_request = _request_hash(
            event["request_id"], event["side"], event["asset_class"],
            event["symbol"], qty, price, fee)
        if not hmac.compare_digest(str(event["request_sha256"]),
                                   expected_request):
            _fail()
        expected_mac = _mac(key, "EVENT", *[event[k] for k in _EVENT_FIELDS])
        if (not isinstance(event["entry_mac"], str)
                or not hmac.compare_digest(event["entry_mac"], expected_mac)):
            _fail()
        cash, realized, worst, stopped, position, _ = _transition(
            wallet, positions, cash, realized, worst, stopped,
            event["side"], event["asset_class"], event["symbol"],
            qty, price, fee)
        if (event["cash_after_cents"] != cash
                or event["realized_after_cents"] != realized
                or event["worst_after_cents"] != worst
                or event["stopped_after"] != stopped
                or event["position_qty_after"] != position[0]
                or event["position_basis_after"] != position[1]
                or event["position_realized_after"] != position[2]):
            _fail()
        previous = expected_mac
    signed = [*wallet.keys()]
    if (wallet["cash_cents"] != cash
            or wallet["realized_cents"] != realized
            or wallet["worst_cents"] != worst
            or wallet["stopped"] != stopped
            or wallet["seq"] != count or wallet["last_mac"] != previous):
        _fail()
    expected_positions = [
        [asset, symbol, *positions[(asset,symbol)]]
        for asset,symbol in sorted(positions)]
    actual_positions = _position_list(db, user, account)
    if expected_positions != actual_positions:
        _fail()
    if not hmac.compare_digest(str(wallet["state_mac"]),
                               _state_mac(key, wallet, actual_positions)):
        _fail()
    return wallet, positions, cash, realized, worst, stopped, count, previous


def register_synthetic_atomic_account(
        path, *, hmac_key, principal_user_id, account_id,
        initial_cash_cents, protected_pct, spend_cap_cents,
        per_trade_cap_cents, max_loss_cents):
    """One immutable policy per identity/account; never funds real accounts."""
    try:
        key = _keys(hmac_key)
        user, account = _identity(principal_user_id, account_id)
        seed = _integer(initial_cash_cents, lower=1)
        protected = _integer(protected_pct, upper=99)
        spend = _integer(spend_cap_cents, lower=1)
        cap = _integer(per_trade_cap_cents, lower=1)
        limit = _integer(max_loss_cents, lower=1)
        with closing(_open(path)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                old = db.execute("""SELECT * FROM offline_atomic_wallets
                    WHERE user_id=? AND account_id=?""",
                    (user, account)).fetchone()
                if old is not None:
                    _audit_scope(db, key, user, account)
                    if any((old[name] != val) for name,val in (
                            ("seeded_cents", seed), ("protected_pct", protected),
                            ("spend_cap_cents", spend),
                            ("per_trade_cap_cents", cap),
                            ("max_loss_cents", limit))):
                        _fail()
                    created = False
                else:
                    row = {"user_id":user,"account_id":account,
                           "seeded_cents":seed,"cash_cents":seed,
                           "protected_pct":protected,"spend_cap_cents":spend,
                           "per_trade_cap_cents":cap,"max_loss_cents":limit,
                           "realized_cents":0,"worst_cents":0,"stopped":0,
                           "seq":0,"last_mac":_GENESIS}
                    db.execute("""INSERT INTO offline_atomic_wallets VALUES
                        (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (user,account,seed,seed,protected,spend,cap,limit,0,0,0,
                         0,_GENESIS,_policy_mac(key,row),
                         _state_mac(key,row,[])))
                    created = True
                db.commit()
                return {"paperOnly":True, "executionEnabled":False,
                        "registered":created}
            except Exception:
                db.rollback()
                raise
    except Exception:
        _fail()


def rehearse_synthetic_atomic_fill(
        path, *, hmac_key, principal_user_id, account_id, request_id,
        side, asset_class, symbol, quantity_units, unit_price_cents,
        fee_cents=0, _fail_before_commit=False):
    """Exactly one SQLite transaction for cash, basis, P&L, stop, and replay.

    Inputs are assumed synthetic data, never actual quotes or broker fills.
    A refused new request is rolled back; only successful requests acquire
    durable idempotency. Caller cannot regard an accepted paper request as
    a production fill authorization.
    """
    try:
        key = _keys(hmac_key)
        user, account = _identity(principal_user_id, account_id)
        request = isolated._uuid(request_id)
        qty, price, fee = _inputs(
            side, asset_class, symbol, quantity_units, unit_price_cents,
            fee_cents)
        digest = _request_hash(request, side, asset_class, symbol,
                               qty, price, fee)
        with closing(_open(path)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                wallet, positions, cash, realized, worst, stopped, seq, prev = (
                    _audit_scope(db, key, user, account))
                old = db.execute("""SELECT request_sha256,cash_after_cents
                    FROM offline_atomic_events WHERE user_id=? AND account_id=?
                    AND request_id=?""", (user, account, request)).fetchone()
                if old:
                    if not hmac.compare_digest(old["request_sha256"], digest):
                        _fail()
                    db.commit()
                    return {"paperOnly":True, "executionEnabled":False,
                            "duplicate":True, "cashCents":cash,
                            "originalCashAfterCents":old["cash_after_cents"],
                            "stopped":bool(stopped)}
                cash, realized, worst, stopped, position, delta = (
                    _transition(wallet, positions, cash, realized, worst,
                                stopped, side, asset_class, symbol,
                                qty, price, fee))
                seq += 1
                values = [user, account, seq, request, digest, side,
                          asset_class, symbol, qty, price, fee, cash,
                          realized, worst, stopped, position[0],
                          position[1], position[2], prev]
                signed = _mac(key, "EVENT", *values)
                db.execute("""INSERT INTO offline_atomic_events VALUES
                    (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (*values, signed))
                db.execute("""INSERT INTO offline_atomic_positions VALUES
                    (?,?,?,?,?,?,?)
                    ON CONFLICT(user_id,account_id,asset_class,symbol)
                    DO UPDATE SET qty_units=excluded.qty_units,
                    basis_cents=excluded.basis_cents,
                    realized_cents=excluded.realized_cents""",
                    (user, account, asset_class, symbol, *position))
                row = dict(wallet)
                row.update(cash_cents=cash,realized_cents=realized,
                           worst_cents=worst,stopped=stopped,
                           seq=seq,last_mac=signed)
                position_list = _position_list(db,user,account)
                db.execute("""UPDATE offline_atomic_wallets SET
                    cash_cents=?,realized_cents=?,worst_cents=?,stopped=?,
                    seq=?,last_mac=?,state_mac=?
                    WHERE user_id=? AND account_id=?""",
                    (cash,realized,worst,stopped,seq,signed,
                     _state_mac(key,row,position_list),user,account))
                if _fail_before_commit:
                    _fail()
                db.commit()
                return {"paperOnly":True,"executionEnabled":False,
                        "duplicate":False,"cashCents":cash,
                        "realizedCents":realized, "worstRealizedCents":worst,
                        "realizedDeltaCents":delta, "stopped":bool(stopped)}
            except Exception:
                db.rollback()
                raise
    except Exception:
        _fail()


def inspect_synthetic_atomic_account(
        path, *, hmac_key, principal_user_id, account_id):
    """Authenticated scoped state only; no real account balance is returned."""
    try:
        key = _keys(hmac_key)
        user, account = _identity(principal_user_id, account_id)
        with closing(_open(path)) as db:
            db.execute("BEGIN")
            wallet, positions, cash, realized, worst, stopped, count, _ = (
                _audit_scope(db, key, user, account))
            return {"paperOnly":True, "executionEnabled":False,
                    "cashCents":cash,"initialCashCents":wallet["seeded_cents"],
                    "realizedCents":realized,"worstRealizedCents":worst,
                    "stopped":bool(stopped),"assumedFillCount":count,
                    "positions":[[a,s,*positions[a,s]]
                                 for a,s in sorted(positions)]}
    except Exception:
        _fail()


def _audit_all(db, key):
    if (db.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            or db.execute("PRAGMA foreign_key_check").fetchone() is not None):
        _fail()
    for table in ("offline_atomic_positions", "offline_atomic_events"):
        if db.execute(f"""SELECT 1 FROM {table} x WHERE NOT EXISTS
                (SELECT 1 FROM offline_atomic_wallets w
                 WHERE w.user_id=x.user_id AND w.account_id=x.account_id)
                LIMIT 1""").fetchone():
            _fail()
    wallets = db.execute("""SELECT user_id,account_id FROM
        offline_atomic_wallets ORDER BY user_id,account_id""").fetchall()
    if not wallets or len(wallets) > 100:
        _fail()
    result, count = [], 0
    for w in wallets:
        u,a = _identity(w["user_id"],w["account_id"])
        row, pos, cash, realized, worst, stopped, events, last = (
            _audit_scope(db,key,u,a))
        result.append([u,a,row["policy_mac"],row["state_mac"],events,
                       cash,realized,worst,stopped,last])
        count += events
    return result,count


def make_synthetic_atomic_checkpoint(
        path, *, hmac_key, anchor_key, epoch):
    """Caller must independently preserve CURRENT checkpoint after each fill."""
    try:
        journal, anchor = _keys(hmac_key,anchor_key)
        number = _integer(epoch,lower=1,upper=2_147_483_647)
        with closing(_open(path)) as db:
            db.execute("BEGIN")
            states,events = _audit_all(db,journal)
            digest = hashlib.sha256(_canonical(states)).hexdigest()
            return {"protocol":_PIN_PROTOCOL,"epoch":number,
                    "accounts":len(states),"events":events,
                    "stateSha256":digest,
                    "anchorMac":_mac(anchor,_PIN_PROTOCOL,number,
                                     len(states),events,digest)}
    except Exception:
        _fail()


def verify_synthetic_atomic_checkpoint(
        path, *, hmac_key, anchor_key, externally_trusted_checkpoint):
    """Fail closed unless the fixture matches an independent LATEST pin.

    An old snapshot and a rolled-back old pin can agree. There is no
    independent monotonic store or atomic pin promotion in this module.
    """
    try:
        pin = externally_trusted_checkpoint
        if (type(pin) is not dict or frozenset(pin) != _PIN_FIELDS
                or pin.get("protocol") != _PIN_PROTOCOL
                or type(pin.get("accounts")) is not int
                or type(pin.get("events")) is not int
                or not isinstance(pin.get("stateSha256"),str)
                or not isinstance(pin.get("anchorMac"),str)
                or not _HEX.fullmatch(pin["stateSha256"])
                or not _HEX.fullmatch(pin["anchorMac"])):
            _fail()
        journal,anchor = _keys(hmac_key,anchor_key)
        expected = _mac(anchor,_PIN_PROTOCOL,
                        _integer(pin["epoch"],lower=1,upper=2_147_483_647),
                        _integer(pin["accounts"],lower=1,upper=100),
                        _integer(pin["events"]),pin["stateSha256"])
        if not hmac.compare_digest(expected,pin["anchorMac"]):
            _fail()
        with closing(_open(path)) as db:
            db.execute("BEGIN")
            states,events = _audit_all(db,journal)
            digest = hashlib.sha256(_canonical(states)).hexdigest()
            if (len(states) != pin["accounts"] or events != pin["events"]
                    or not hmac.compare_digest(digest,pin["stateSha256"])):
                _fail()
        return {"paperOnly":True, "executionEnabled":False,
                "checkpointVerified":True,"epoch":pin["epoch"],
                "accounts":pin["accounts"],"events":events}
    except Exception:
        _fail()
