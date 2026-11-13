"""Dormant fractional-Decimal paper/realized-stop SQLite transaction research.

OFFLINE FIXTURES ONLY. Numeric observations are invented unit-test assumptions,
NOT market-data rights, broker quotes or production paper fills. Never imported
by the Flask app. The separate new 0600 /dev/shm database has no tenant records.
The identity UUID inputs here do NOT authenticate a real principal.
"""
from __future__ import annotations

from contextlib import closing
from decimal import Decimal, ROUND_UP
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote as url_quote

from . import shadow_storage
from . import tenant_paper_atomic_rehearsal as base
from . import tenant_paper_ledger as decimal_ledger

_MAGIC = "EDGEPILOT-OFFLINE-DECIMAL-ATOMIC-v1"
_PIN = "EDGEPILOT-OFFLINE-DECIMAL-ATOMIC-PIN-v1"
_GENESIS = "0" * 64
_MAX_CENTS = 100_000_000_000
_ASSETS = frozenset(("stock", "etf", "crypto"))
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,19}$")
_TABLES = frozenset(("decimal_marker", "decimal_wallets", "decimal_positions", "decimal_events"))
_EVENT_FIELDS = ("user_id", "account_id", "seq", "request_id", "request_hash",
                 "side", "asset_class", "symbol", "quantity", "price", "fee",
                 "slippage", "change_cents", "cash_after_cents",
                 "realized_after_cents", "worst_after_cents", "stopped_after",
                 "position_qty_after", "position_basis_after", "position_realized_after",
                 "previous_mac")


class DecimalAtomicDenied(ValueError):
    """Sanitized refusal; never includes a secret, identity or filename."""


def _fail():
    raise DecimalAtomicDenied("Offline Decimal paper rehearsal unavailable")


def _mac(key, *values):
    return base._mac(key, *values)


def _key(value):
    return base._keys(value)


def _identity(user, account):
    return base._identity(user, account)


def _int(value, *, lower=0):
    return base._integer(value, lower=lower, upper=_MAX_CENTS)


def _decimal(value, name, *, positive=False):
    # Reuse the dormant writer's exact Decimal boundary and -18 scale limit.
    number = decimal_ledger._number(value, name, positive=positive)
    return format(number.normalize(), "f")


def _inputs(side, asset, symbol, quantity, price, fee, slippage):
    if (side not in ("BUY", "SELL") or asset not in _ASSETS
            or type(symbol) is not str or not _SYMBOL.fullmatch(symbol)):
        _fail()
    return (_decimal(quantity, "quantity", positive=True),
            _decimal(price, "assumed synthetic price", positive=True),
            _decimal(fee, "assumed fee"), _decimal(slippage, "assumed slippage"))


def _open(path):
    source = base._file(path)  # Verified /dev/shm, 0600, owner, no links.
    uri = "file:" + url_quote(str(source), safe="/") + "?mode=rw"
    db = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=15)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys=ON")
        marker = db.execute("SELECT label FROM decimal_marker WHERE id=1").fetchone()
        tables = db.execute("""SELECT name,type FROM sqlite_master
            WHERE type IN ('table','view','trigger')""").fetchall()
        if (marker is None or marker["label"] != _MAGIC
                or frozenset(r["name"] for r in tables) != _TABLES
                or any(r["type"] != "table" for r in tables)
                or db.execute("PRAGMA journal_mode").fetchone()[0].lower() != "delete"):
            _fail()
        return db
    except Exception:
        db.close()
        raise


def create_decimal_fixture(path):
    """Exclusive creation on verified tmpfs; never migrate/overwrite a file."""
    created = False
    try:
        root = shadow_storage.memory_root()
        target = Path(path)
        parent = target.parent.resolve(strict=True)
        if (target.name in ("", ".", "..") or parent != target.parent
                or (parent != root and root not in parent.parents)):
            _fail()
        fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        created = True
        with closing(sqlite3.connect(str(target), isolation_level=None)) as db:
            db.executescript("""
                PRAGMA journal_mode=DELETE;
                PRAGMA foreign_keys=ON;
                CREATE TABLE decimal_marker (
                    id INTEGER PRIMARY KEY CHECK(id=1), label TEXT NOT NULL);
                CREATE TABLE decimal_wallets (
                    user_id TEXT NOT NULL, account_id TEXT NOT NULL,
                    seed INTEGER NOT NULL CHECK(seed>0),
                    cash INTEGER NOT NULL CHECK(cash>=0),
                    protected INTEGER NOT NULL CHECK(protected BETWEEN 0 AND 99),
                    spend INTEGER NOT NULL CHECK(spend>0),
                    trade INTEGER NOT NULL CHECK(trade>0),
                    loss INTEGER NOT NULL CHECK(loss>0),
                    realized INTEGER NOT NULL, worst INTEGER NOT NULL CHECK(worst<=0),
                    stopped INTEGER NOT NULL CHECK(stopped IN (0,1)),
                    seq INTEGER NOT NULL CHECK(seq>=0), last_mac TEXT NOT NULL,
                    policy_mac TEXT NOT NULL, state_mac TEXT NOT NULL,
                    PRIMARY KEY(user_id,account_id));
                CREATE TABLE decimal_positions (
                    user_id TEXT NOT NULL, account_id TEXT NOT NULL,
                    asset_class TEXT NOT NULL, symbol TEXT NOT NULL,
                    quantity TEXT NOT NULL, basis INTEGER NOT NULL CHECK(basis>=0),
                    realized INTEGER NOT NULL,
                    PRIMARY KEY(user_id,account_id,asset_class,symbol),
                    FOREIGN KEY(user_id,account_id)
                      REFERENCES decimal_wallets(user_id,account_id));
                CREATE TABLE decimal_events (
                    user_id TEXT NOT NULL, account_id TEXT NOT NULL,
                    seq INTEGER NOT NULL, request_id TEXT NOT NULL,
                    request_hash TEXT NOT NULL, side TEXT NOT NULL,
                    asset_class TEXT NOT NULL, symbol TEXT NOT NULL,
                    quantity TEXT NOT NULL, price TEXT NOT NULL,
                    fee TEXT NOT NULL, slippage TEXT NOT NULL,
                    change_cents INTEGER NOT NULL, cash_after_cents INTEGER NOT NULL,
                    realized_after_cents INTEGER NOT NULL,
                    worst_after_cents INTEGER NOT NULL,
                    stopped_after INTEGER NOT NULL,
                    position_qty_after TEXT NOT NULL,
                    position_basis_after INTEGER NOT NULL,
                    position_realized_after INTEGER NOT NULL,
                    previous_mac TEXT NOT NULL, entry_mac TEXT NOT NULL,
                    PRIMARY KEY(user_id,account_id,seq),
                    UNIQUE(user_id,account_id,request_id),
                    FOREIGN KEY(user_id,account_id)
                      REFERENCES decimal_wallets(user_id,account_id));
                INSERT INTO decimal_marker VALUES
                    (1,'EDGEPILOT-OFFLINE-DECIMAL-ATOMIC-v1');
            """)
        return target
    except Exception:
        if created:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass
        _fail()


def _policy_mac(key, row):
    return _mac(key, "POLICY", *(row[k] for k in (
        "user_id", "account_id", "seed", "protected", "spend", "trade", "loss")))


def _positions(db, user, account):
    return [[r["asset_class"],r["symbol"],r["quantity"],r["basis"],r["realized"]]
            for r in db.execute("""SELECT * FROM decimal_positions
                WHERE user_id=? AND account_id=? ORDER BY asset_class,symbol""",
                (user, account))]


def _state_mac(key, row, positions):
    return _mac(key, "STATE", *(row[k] for k in (
        "user_id", "account_id", "cash", "realized", "worst", "stopped",
        "seq", "last_mac", "policy_mac")), positions)


def _request_hash(request, side, asset, symbol, qty, price, fee, slip):
    payload = ["FABRICATED-DECIMAL-FILL", request, side, asset, symbol,
               qty, price, fee, slip]
    return hashlib.sha256(base._canonical(payload)).hexdigest()


def _step(policy, holdings, cash, realized, worst, stopped,
          side, asset, symbol, qty, price, fee, slip):
    qty_d, price_d, fee_d, slip_d = map(Decimal, (qty, price, fee, slip))
    old = holdings.get((asset,symbol), ["0", 0, 0])
    old_qty, basis, asset_realized = Decimal(old[0]), old[1], old[2]
    if side == "BUY":
        if stopped:
            _fail()
        cost = decimal_ledger._cents((price_d + fee_d + slip_d)*qty_d, ROUND_UP)
        exposure = sum(p[1] for p in holdings.values())
        budget = min(policy["seed"]*(100-policy["protected"])//100, policy["spend"])
        if (cost <= 0 or cost > policy["trade"] or cost > cash
                or exposure + cost > budget or basis + cost > _MAX_CENTS
                or old_qty + qty_d > decimal_ledger.MAX):
            _fail()
        new_qty = old_qty+qty_d
        new_basis = basis+cost
        delta = 0
        cash -= cost
        change = -cost
    else:
        if qty_d > old_qty or old_qty <= 0:
            _fail()
        net = price_d-fee_d-slip_d
        if net <= 0:
            _fail()
        proceeds = decimal_ledger._cents(net*qty_d)
        if proceeds <= 0 or cash+proceeds > _MAX_CENTS:
            _fail()
        released = basis if qty_d == old_qty else int(
            (Decimal(basis)*qty_d/old_qty).to_integral_value(rounding=ROUND_UP))
        delta = proceeds-released
        realized += delta
        if abs(realized) > _MAX_CENTS:
            _fail()
        worst = min(worst, realized)
        stopped = int(stopped or worst <= -policy["loss"])
        cash += proceeds
        new_qty = old_qty-qty_d
        new_basis = basis-released
        change = proceeds
    own_realized = asset_realized+delta
    if (new_basis < 0 or abs(own_realized) > _MAX_CENTS
            or abs(worst) > _MAX_CENTS):
        _fail()
    position = [format(new_qty.normalize(),"f"), new_basis, own_realized]
    holdings[(asset,symbol)] = position
    return cash, realized, worst, stopped, position, change, delta


def _audit(db, key, user, account):
    wallet = db.execute("""SELECT * FROM decimal_wallets WHERE user_id=?
        AND account_id=?""",(user,account)).fetchone()
    if wallet is None or wallet["user_id"] != user or wallet["account_id"] != account:
        _fail()
    if not hmac.compare_digest(str(wallet["policy_mac"]), _policy_mac(key,wallet)):
        _fail()
    _int(wallet["seed"],lower=1)
    _int(wallet["protected"])
    if wallet["protected"] > 99:
        _fail()
    for k in ("spend", "trade", "loss"):
        _int(wallet[k],lower=1)
    holdings, cash, realized, worst, stopped = {}, wallet["seed"], 0, 0, 0
    previous, count = _GENESIS, 0
    for event in db.execute("""SELECT * FROM decimal_events
            WHERE user_id=? AND account_id=? ORDER BY seq""",(user,account)):
        count += 1
        if (type(event["seq"]) is not int or event["seq"] != count
                or (event["user_id"],event["account_id"]) != (user,account)
                or base._identity(user, event["account_id"]) != (user,account)
                or event["previous_mac"] != previous):
            _fail()
        request = base.isolated._uuid(event["request_id"])
        values = _inputs(event["side"],event["asset_class"],event["symbol"],
                         event["quantity"],event["price"],event["fee"],event["slippage"])
        if values != tuple(event[k] for k in ("quantity", "price", "fee", "slippage")):
            _fail()  # canonical decimal representation is part of the journal
        expected_hash = _request_hash(request,event["side"],event["asset_class"],
                                      event["symbol"],*values)
        if not hmac.compare_digest(str(event["request_hash"]), expected_hash):
            _fail()
        expected_mac = _mac(key,"EVENT",*(event[k] for k in _EVENT_FIELDS))
        if not hmac.compare_digest(str(event["entry_mac"]),expected_mac):
            _fail()
        cash, realized, worst, stopped, position, change, _ = _step(
            wallet,holdings,cash,realized,worst,stopped,event["side"],
            event["asset_class"],event["symbol"],*values)
        if (event["change_cents"] != change
                or event["cash_after_cents"] != cash
                or event["realized_after_cents"] != realized
                or event["worst_after_cents"] != worst
                or event["stopped_after"] != stopped
                or event["position_qty_after"] != position[0]
                or event["position_basis_after"] != position[1]
                or event["position_realized_after"] != position[2]):
            _fail()
        previous = expected_mac
    expected = [[a,s,*holdings[(a,s)]] for a,s in sorted(holdings)]
    actual = _positions(db,user,account)
    if expected != actual or any((wallet[k] != val) for k,val in (
            ("cash",cash),("realized",realized),("worst",worst),
            ("stopped",stopped),("seq",count),("last_mac",previous))):
        _fail()
    if not hmac.compare_digest(str(wallet["state_mac"]),_state_mac(key,wallet,actual)):
        _fail()
    return wallet, holdings, cash, realized, worst, stopped, count, previous


def register_decimal_account(path, *, hmac_key, principal_user_id, account_id,
                             initial_cash_cents, protected_pct, spend_cap_cents,
                             per_trade_cap_cents, max_loss_cents):
    """Synthetic account label only; never trusts these UUIDs for real access."""
    try:
        key = _key(hmac_key)
        user, account = _identity(principal_user_id,account_id)
        seed = _int(initial_cash_cents,lower=1)
        protected = _int(protected_pct)
        spend = _int(spend_cap_cents,lower=1)
        trade = _int(per_trade_cap_cents,lower=1)
        loss = _int(max_loss_cents,lower=1)
        if protected > 99:
            _fail()
        with closing(_open(path)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                old=db.execute("""SELECT * FROM decimal_wallets WHERE user_id=?
                    AND account_id=?""",(user,account)).fetchone()
                if old is not None:
                    _audit(db,key,user,account)
                    if any(old[k] != val for k,val in (
                            ("seed",seed),("protected",protected),("spend",spend),
                            ("trade",trade),("loss",loss))):
                        _fail()
                    created=False
                else:
                    row=dict(user_id=user,account_id=account,seed=seed,cash=seed,
                             protected=protected,spend=spend,trade=trade,loss=loss,
                             realized=0,worst=0,stopped=0,seq=0,last_mac=_GENESIS)
                    row["policy_mac"] = _policy_mac(key,row)
                    row["state_mac"] = _state_mac(key,row,[])
                    db.execute("""INSERT INTO decimal_wallets VALUES
                        (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        tuple(row[k] for k in ("user_id","account_id","seed","cash",
                            "protected","spend","trade","loss","realized","worst",
                            "stopped","seq","last_mac","policy_mac","state_mac")))
                    created=True
                db.commit()
                return {"paperOnly":True,"executionEnabled":False,"created":created}
            except Exception:
                db.rollback()
                raise
    except Exception:
        _fail()


def decimal_fill(path, *, hmac_key, principal_user_id, account_id,
                 request_id, side, asset_class, symbol, quantity,
                 assumed_unit_price, fee_per_unit="0", slippage_per_unit="0",
                 _fail_before_commit=False):
    """Fabricated numbers, not even an alleged licensed Observation object."""
    try:
        key=_key(hmac_key)
        user,account=_identity(principal_user_id,account_id)
        request=base.isolated._uuid(request_id)
        vals=_inputs(side,asset_class,symbol,quantity,assumed_unit_price,
                     fee_per_unit,slippage_per_unit)
        digest=_request_hash(request,side,asset_class,symbol,*vals)
        with closing(_open(path)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                wallet,holdings,cash,realized,worst,stopped,seq,previous=(
                    _audit(db,key,user,account))
                old=db.execute("""SELECT request_hash,cash_after_cents
                    FROM decimal_events WHERE user_id=? AND account_id=?
                    AND request_id=?""",(user,account,request)).fetchone()
                if old is not None:
                    if not hmac.compare_digest(str(old["request_hash"]),digest):
                        _fail()
                    db.commit()
                    return {"paperOnly":True,"executionEnabled":False,
                            "duplicate":True,"cashCents":cash,
                            "originalCashAfterCents":old["cash_after_cents"],
                            "stopped":bool(stopped)}
                cash,realized,worst,stopped,position,change,delta=_step(
                    wallet,holdings,cash,realized,worst,stopped,side,
                    asset_class,symbol,*vals)
                seq+=1
                fields=[user,account,seq,request,digest,side,asset_class,symbol,
                        *vals,change,cash,realized,worst,stopped,*position,previous]
                event_mac=_mac(key,"EVENT",*fields)
                db.execute("""INSERT INTO decimal_events VALUES
                    (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (*fields,event_mac))
                db.execute("""INSERT INTO decimal_positions VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(user_id,account_id,asset_class,symbol)
                    DO UPDATE SET quantity=excluded.quantity,basis=excluded.basis,
                    realized=excluded.realized""",
                    (user,account,asset_class,symbol,*position))
                row=dict(wallet)
                row.update(cash=cash,realized=realized,worst=worst,stopped=stopped,
                           seq=seq,last_mac=event_mac)
                db.execute("""UPDATE decimal_wallets SET cash=?,realized=?,worst=?,
                    stopped=?,seq=?,last_mac=?,state_mac=?
                    WHERE user_id=? AND account_id=?""",
                    (cash,realized,worst,stopped,seq,event_mac,
                     _state_mac(key,row,_positions(db,user,account)),user,account))
                if _fail_before_commit:
                    _fail()
                db.commit()
                return {"paperOnly":True,"executionEnabled":False,
                        "duplicate":False,"cashCents":cash,
                        "realizedCents":realized,"worstRealizedCents":worst,
                        "realizedDeltaCents":delta,"stopped":bool(stopped)}
            except Exception:
                db.rollback()
                raise
    except Exception:
        _fail()


def inspect_decimal_account(path, *, hmac_key, principal_user_id, account_id):
    try:
        key=_key(hmac_key)
        user,account=_identity(principal_user_id,account_id)
        with closing(_open(path)) as db:
            db.execute("BEGIN")
            wallet,holdings,cash,realized,worst,stopped,count,_=(
                _audit(db,key,user,account))
            return {"paperOnly":True,"executionEnabled":False,
                    "cashCents":cash,"realizedCents":realized,
                    "worstRealizedCents":worst,"stopped":bool(stopped),
                    "fillCount":count,"positions":_positions(db,user,account)}
    except Exception:
        _fail()


def _checkpoint_data(db, key):
    result=[]
    for row in db.execute("""SELECT user_id,account_id FROM decimal_wallets
            ORDER BY user_id,account_id"""):
        wallet,*_= _audit(db,key,row["user_id"],row["account_id"])
        result.append([wallet["user_id"],wallet["account_id"],wallet["seq"],
                       wallet["state_mac"],wallet["last_mac"]])
    return result


def make_decimal_checkpoint(path, *, hmac_key, anchor_key, epoch):
    """Return a candidate; external operator MUST durably retain latest pin."""
    try:
        key,anchor=base._keys(hmac_key,anchor_key)
        if type(epoch) is not int or epoch<1 or epoch>_MAX_CENTS:
            _fail()
        with closing(_open(path)) as db:
            db.execute("BEGIN")
            data=_checkpoint_data(db,key)
            payload={"protocol":_PIN,"epoch":epoch,"accounts":data}
            payload["anchorMac"]=_mac(anchor,"CHECKPOINT",payload["protocol"],epoch,data)
            return payload
    except Exception:
        _fail()


def verify_decimal_checkpoint(path, *, hmac_key, anchor_key,
                              externally_trusted_latest_checkpoint):
    """Never automatically promotes an older fixture or old operator pin."""
    try:
        pin=externally_trusted_latest_checkpoint
        if (not isinstance(pin,dict) or set(pin)!={"protocol","epoch","accounts","anchorMac"}
                or pin["protocol"]!=_PIN):
            _fail()
        key,anchor=base._keys(hmac_key,anchor_key)
        if not hmac.compare_digest(str(pin["anchorMac"]),
                _mac(anchor,"CHECKPOINT",pin["protocol"],pin["epoch"],pin["accounts"])):
            _fail()
        actual=make_decimal_checkpoint(path,hmac_key=key,anchor_key=anchor,
                                       epoch=pin["epoch"])
        if not hmac.compare_digest(str(actual["anchorMac"]),str(pin["anchorMac"])):
            _fail()
        return {"checkpointVerified":True,"epoch":pin["epoch"],"paperOnly":True}
    except Exception:
        _fail()
