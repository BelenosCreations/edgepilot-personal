"""Dormant tenant/account-isolated paper-only accounting.

Not imported by app.py: there is NO HTTP route, broker adapter, automatic job,
live order, transfer, or production schema migration. The future caller MUST
derive principal_user_id from a verified server session, NEVER from a form.
Market rights assertions must be verified by an authorized provider adapter
before passing them here. No actual broker fills enter these tables.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP

from . import tenant_foundation
from .research_intelligence import Observation, ResearchUnavailable

CENT = Decimal("0.01")
MAX = Decimal("1000000000")


class PaperLedgerDenied(ValueError):
    """Sanitized paper-only accounting or account-scope refusal."""


def _number(value, label, *, positive=False):
    if isinstance(value, (bool, float)) or not isinstance(value, (str, int, Decimal)):
        raise PaperLedgerDenied("Invalid " + label)
    try:
        result = Decimal(str(value))
    except (ValueError, InvalidOperation, TypeError):
        raise PaperLedgerDenied("Invalid " + label) from None
    if (not result.is_finite() or result < 0 or result > MAX
            or (positive and result == 0) or result.as_tuple().exponent < -18):
        raise PaperLedgerDenied("Invalid " + label)
    return result


def _cents(amount, rounding=ROUND_DOWN):
    return int((amount * 100).to_integral_value(rounding=rounding))


def _money(cents):
    return str((Decimal(int(cents)) / 100).quantize(CENT))


def _uuid(value):
    if not isinstance(value, str):
        raise PaperLedgerDenied("Paper identity unavailable")
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        raise PaperLedgerDenied("Paper identity unavailable") from None
    return value


def _scope(db, principal_user_id, account_id):
    user = _uuid(principal_user_id)
    account = _uuid(account_id)
    # Existing disabled, revoked and cross-member safeguards apply. Do not
    # infer authority from knowing another member's UUID.
    row = db.execute("""SELECT a.account_id FROM tenant_accounts a
        JOIN tenant_users u ON u.user_id=a.user_id
        JOIN tenant_connections c
          ON c.connection_id=a.connection_id AND c.user_id=a.user_id
        WHERE a.user_id=? AND a.account_id=? AND a.disabled_at IS NULL
          AND u.disabled_at IS NULL AND c.revoked_at IS NULL""",
        (user, account)).fetchone()
    if row is None:
        raise PaperLedgerDenied("Paper account unavailable")
    return user, account


def prepare(path):
    """Additive, explicitly called schema on an existing tenant database only."""
    with tenant_foundation._open(path) as db:
        # SQLite permits declarations referencing nonexistent tables. Refuse
        # an accidental legacy/global database before adding ANY paper table.
        try:
            version = db.execute(
                "SELECT schema_version FROM tenant_schema_meta WHERE id=1"
            ).fetchone()
            db.execute("SELECT account_id FROM tenant_accounts LIMIT 0")
        except sqlite3.DatabaseError:
            raise PaperLedgerDenied("Prepared private tenant schema required") from None
        if version is None or version["schema_version"] != 1:
            raise PaperLedgerDenied("Prepared private tenant schema required")
        # FK references existing tenant_accounts and cannot be substituted for
        # the legacy global-token account database or its broker-fill ledger.
        db.executescript("""
        CREATE TABLE IF NOT EXISTS tenant_paper_wallets (
            user_id TEXT NOT NULL, account_id TEXT NOT NULL,
            seeded_cents INTEGER NOT NULL CHECK(seeded_cents>0),
            cash_cents INTEGER NOT NULL CHECK(cash_cents>=0),
            opened_at TEXT NOT NULL,
            PRIMARY KEY(user_id,account_id),
            FOREIGN KEY(account_id,user_id)
              REFERENCES tenant_accounts(account_id,user_id)
        );
        CREATE TABLE IF NOT EXISTS tenant_paper_positions (
            user_id TEXT NOT NULL, account_id TEXT NOT NULL,
            asset_class TEXT NOT NULL CHECK(asset_class IN ('stock','etf','crypto')),
            symbol TEXT NOT NULL, quantity TEXT NOT NULL,
            cost_basis_cents INTEGER NOT NULL CHECK(cost_basis_cents>=0),
            realized_cents INTEGER NOT NULL,
            PRIMARY KEY(user_id,account_id,asset_class,symbol),
            FOREIGN KEY(user_id,account_id)
              REFERENCES tenant_paper_wallets(user_id,account_id)
        );
        CREATE TABLE IF NOT EXISTS tenant_paper_events (
            user_id TEXT NOT NULL, account_id TEXT NOT NULL,
            request_id TEXT NOT NULL, request_sha256 TEXT NOT NULL,
            side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
            asset_class TEXT NOT NULL, symbol TEXT NOT NULL,
            quantity TEXT NOT NULL, quote_price TEXT NOT NULL,
            estimated_friction TEXT NOT NULL,
            signed_cash_change_cents INTEGER NOT NULL,
            cash_after_cents INTEGER NOT NULL,
            provider TEXT NOT NULL, observed_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(user_id,account_id,request_id),
            FOREIGN KEY(user_id,account_id)
              REFERENCES tenant_paper_wallets(user_id,account_id)
        );
        CREATE INDEX IF NOT EXISTS idx_tenant_paper_events_scope
          ON tenant_paper_events(user_id,account_id,created_at);
        """)


def open_wallet(path, *, principal_user_id, account_id, initial_paper_cash):
    """Only an explicit internal action can seed a paper wallet; never fund it."""
    seed = _number(initial_paper_cash, "initial paper cash", positive=True)
    if seed != seed.quantize(CENT):
        raise PaperLedgerDenied("Seed paper funds must be whole cents")
    seed_cents = _cents(seed)
    with tenant_foundation._open(path) as db:
        db.execute("BEGIN IMMEDIATE")
        user, account = _scope(db, principal_user_id, account_id)
        row = db.execute("""SELECT seeded_cents FROM tenant_paper_wallets
            WHERE user_id=? AND account_id=?""", (user, account)).fetchone()
        if row:
            if row["seeded_cents"] != seed_cents:
                raise PaperLedgerDenied("Existing paper wallet cannot be reseeded")
            return {"created": False, "paperOnly": True}
        db.execute("""INSERT INTO tenant_paper_wallets
            (user_id,account_id,seeded_cents,cash_cents,opened_at)
            VALUES(?,?,?,?,?)""",
            (user,account,seed_cents,seed_cents,
             datetime.now(timezone.utc).isoformat()))
        return {"created": True, "paperOnly": True}


def _prepare_fill(request_id, side, observation, now, quantity, fee_per_unit,
                  slippage_per_unit, protected_pct, spend_cap, per_trade_cap):
    """Validate source evidence and compute the existing ledger request digest."""
    key = _uuid(request_id)
    if side not in ("BUY", "SELL"):
        raise PaperLedgerDenied("Unsupported paper side")
    try:
        quote = Observation.validate(observation, now=now)
    except ResearchUnavailable:
        raise PaperLedgerDenied("Verified fresh market evidence required") from None
    if quote.asset_class not in ("stock", "etf", "crypto"):
        raise PaperLedgerDenied("Separate prediction contract model required")
    # Unlike an ephemeral estimate, a durable simulated fill retains a
    # source, observation time and quote reference. Refuse when the provider
    # has not explicitly permitted caching/persistent evidence.
    if not quote.rights.allowed_cache:
        raise PaperLedgerDenied("Persistent market evidence rights unavailable")
    qty = _number(quantity, "paper quantity", positive=True)
    fee = _number(fee_per_unit, "fee assumption")
    slip = _number(slippage_per_unit, "slippage assumption")
    pct = _number(protected_pct, "protected percentage")
    spending = _number(spend_cap, "paper spend cap")
    per_trade = _number(per_trade_cap, "paper per-trade cap")
    if pct > 99:
        raise PaperLedgerDenied("Protected balance must be 0–99%")
    if side == "BUY":
        change = -_cents((quote.ask + fee + slip) * qty, ROUND_UP)
    else:
        net_unit = quote.bid - fee - slip
        if net_unit <= 0:
            raise PaperLedgerDenied("Nonpositive paper sale proceeds")
        change = _cents(net_unit * qty, ROUND_DOWN)
    if change == 0 or abs(change) > _cents(MAX):
        raise PaperLedgerDenied("Paper fill notional outside safe accounting bounds")
    request_record = {
        "requestId": key, "side": side, "asset": quote.asset_class,
        "symbol": quote.symbol, "provider": quote.rights.provider,
        "observedAt": quote.observed_at.isoformat(),
        "receivedAt": quote.received_at.isoformat(),
        "bid": str(quote.bid), "ask": str(quote.ask), "quantity": str(qty),
        "fee": str(fee), "slippage": str(slip),
        "protectedPct": str(pct), "spendCap": str(spending),
        "perTradeCap": str(per_trade),
    }
    digest = hashlib.sha256(json.dumps(
        request_record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return key, quote, qty, fee, slip, pct, spending, per_trade, change, digest


def record_paper_fill(path, *, principal_user_id, account_id, request_id,
                      side, observation, now, quantity, fee_per_unit,
                      slippage_per_unit, protected_pct, spend_cap, per_trade_cap):
    """Atomically record an assumed paper fill, NEVER an order or actual fill.

    Quotes are checked again at the time of the simulation. BUY uses the ask
    plus adverse slippage and fees, rounded UP. SELL uses bid minus friction,
    rounded DOWN. Cost basis is released conservatively on partial sells.
    No short selling, leverage, open orders, actual brokerage cash, or
    fabricated unrealized performance is modelled.
    """
    key, quote, qty, fee, slip, pct, spending, per_trade, change, digest = _prepare_fill(
        request_id, side, observation, now, quantity, fee_per_unit,
        slippage_per_unit, protected_pct, spend_cap, per_trade_cap)
    quote_price = quote.ask if side == "BUY" else quote.bid
    with tenant_foundation._open(path) as db:
        db.execute("BEGIN IMMEDIATE")
        user, account = _scope(db, principal_user_id, account_id)
        wallet = db.execute("""SELECT seeded_cents,cash_cents FROM tenant_paper_wallets
            WHERE user_id=? AND account_id=?""", (user, account)).fetchone()
        if not wallet:
            raise PaperLedgerDenied("Paper wallet not initialized")
        prev = db.execute("""SELECT request_sha256,cash_after_cents
            FROM tenant_paper_events
            WHERE user_id=? AND account_id=? AND request_id=?""",
            (user,account,key)).fetchone()
        if prev:
            if prev["request_sha256"] != digest:
                raise PaperLedgerDenied("Conflicting paper request replay")
            # The old event's balance is historical; a retry must not
            # mislabel it as current after subsequent paper fills.
            return {"duplicate": True, "paperOnly": True,
                    "paperCash": _money(wallet["cash_cents"]),
                    "originalPaperCashAfter": _money(prev["cash_after_cents"])}
        position = db.execute("""SELECT quantity,cost_basis_cents,realized_cents
            FROM tenant_paper_positions
            WHERE user_id=? AND account_id=? AND asset_class=? AND symbol=?""",
            (user,account,quote.asset_class,quote.symbol)).fetchone()
        existing_qty = Decimal(position["quantity"]) if position else Decimal(0)
        existing_basis = position["cost_basis_cents"] if position else 0
        realized = position["realized_cents"] if position else 0
        if side == "BUY":
            exposures = db.execute("""SELECT COALESCE(SUM(cost_basis_cents),0) AS used
                FROM tenant_paper_positions WHERE user_id=? AND account_id=?""",
                (user,account)).fetchone()["used"]
            budget = min(_cents(Decimal(wallet["seeded_cents"]) / 100 *
                                (100-pct)/100), _cents(spending))
            available = min(max(0,budget-exposures),wallet["cash_cents"],
                            _cents(per_trade))
            if -change > available:
                raise PaperLedgerDenied("Paper cash or protected risk budget insufficient")
            new_qty = existing_qty + qty
            basis = existing_basis - change
        else:
            if qty > existing_qty or existing_qty <= 0:
                raise PaperLedgerDenied("Paper sale exceeds paper holdings")
            released = existing_basis if qty == existing_qty else int(
                (Decimal(existing_basis) * qty / existing_qty).to_integral_value(
                    rounding=ROUND_UP))
            new_qty = existing_qty - qty
            basis = existing_basis - released
            realized += change - released
        new_cash = wallet["cash_cents"] + change
        if new_cash < 0:
            raise PaperLedgerDenied("Paper cash insufficient")
        db.execute("""UPDATE tenant_paper_wallets SET cash_cents=?
            WHERE user_id=? AND account_id=?""",(new_cash,user,account))
        db.execute("""INSERT INTO tenant_paper_positions
            (user_id,account_id,asset_class,symbol,quantity,cost_basis_cents,realized_cents)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(user_id,account_id,asset_class,symbol) DO UPDATE SET
              quantity=excluded.quantity, cost_basis_cents=excluded.cost_basis_cents,
              realized_cents=excluded.realized_cents""",
            (user,account,quote.asset_class,quote.symbol,str(new_qty),basis,realized))
        db.execute("""INSERT INTO tenant_paper_events
            (user_id,account_id,request_id,request_sha256,side,asset_class,
             symbol,quantity,quote_price,estimated_friction,
             signed_cash_change_cents,cash_after_cents,provider,observed_at,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user,account,key,digest,side,quote.asset_class,quote.symbol,
             str(qty),str(quote_price),str(fee+slip),change,new_cash,
             quote.rights.provider,quote.observed_at.isoformat(),
             datetime.now(timezone.utc).isoformat()))
        return {"duplicate": False, "paperOnly": True,
                "paperCash": _money(new_cash),
                "recordedAssumedFill": True,
                "liveOrderSubmitted": False,
                "realizedPaperPnL": _money(realized)}


def snapshot(path, *, principal_user_id, account_id):
    """Owner-scoped PAPER book only. Never blend with Public real positions."""
    with tenant_foundation._open(path) as db:
        user, account = _scope(db, principal_user_id, account_id)
        wallet = db.execute("""SELECT seeded_cents,cash_cents FROM tenant_paper_wallets
            WHERE user_id=? AND account_id=?""", (user,account)).fetchone()
        if not wallet:
            raise PaperLedgerDenied("Paper wallet not initialized")
        positions = db.execute("""SELECT asset_class,symbol,quantity,
            cost_basis_cents,realized_cents FROM tenant_paper_positions
            WHERE user_id=? AND account_id=? ORDER BY asset_class,symbol""",
            (user,account)).fetchall()
        count = db.execute("""SELECT COUNT(*) AS n FROM tenant_paper_events
            WHERE user_id=? AND account_id=?""",(user,account)).fetchone()["n"]
        return {
            "paperOnly": True, "orderExecutionEnabled": False,
            "initialPaperCash": _money(wallet["seeded_cents"]),
            "remainingPaperCash": _money(wallet["cash_cents"]),
            "assumedFills": count,
            "positions": [{"assetClass":p["asset_class"],"symbol":p["symbol"],
                           "quantity":p["quantity"],
                           "costBasis":_money(p["cost_basis_cents"]),
                           "realizedPaperPnL":_money(p["realized_cents"])}
                          for p in positions],
            "warning": ("Synthetic assumed fills, not verified broker executions. "
                        "No price marking, unrealized returns, real account "
                        "balance or actual trade was recorded."),
        }
