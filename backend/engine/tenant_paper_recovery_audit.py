"""Offline, synthetic-only structural audit of dormant tenant paper accounting.

Called by the isolated /dev/shm backup rehearsal, NEVER by the web server.
This verifies arithmetic and per-account continuity, NOT provider authenticity,
market licensing, broker transactions, or production restore readiness.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP
import re
import sqlite3
import uuid

PAPER_TABLES = frozenset({
    "tenant_paper_wallets", "tenant_paper_positions", "tenant_paper_events",
})
_ASSETS = frozenset({"stock", "etf", "crypto"})
_MAX = Decimal("1000000000")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_UTC_EVENT_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$"
)


class PaperRecoveryDenied(ValueError):
    """Never expose private user, account, event, or SQL content."""


def _decimal(raw, *, positive=False):
    if not isinstance(raw, (str, int, Decimal)) or isinstance(raw, bool):
        raise PaperRecoveryDenied("Synthetic paper ledger integrity unavailable")
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        raise PaperRecoveryDenied("Synthetic paper ledger integrity unavailable") from None
    if (not value.is_finite() or value < 0 or value > _MAX
            or (positive and not value)
            or value.as_tuple().exponent < -18):
        raise PaperRecoveryDenied("Synthetic paper ledger integrity unavailable")
    return value


def _cents(amount, rounding):
    return int((amount * 100).to_integral_value(rounding=rounding))


def _canonical_uuid(raw):
    try:
        return isinstance(raw, str) and str(uuid.UUID(raw)) == raw
    except (ValueError, TypeError, AttributeError):
        return False


def _event_time(value):
    """Check chronology of synthetic events; does not authenticate a source."""
    if (not isinstance(value, str) or len(value) > 40
            or not _UTC_EVENT_TIME.fullmatch(value)):
        raise PaperRecoveryDenied("Synthetic paper ledger integrity unavailable")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() != timedelta(0):
            raise ValueError
        return result
    except (ValueError, TypeError, OverflowError):
        raise PaperRecoveryDenied(
            "Synthetic paper ledger integrity unavailable"
        ) from None


def audit_tenant_paper_ledger(db):
    """Fail closed on missing/mixed schema, inconsistent rows or cash arithmetic.

    Uses rowid insertion order for this append-only prototype's event replay.
    The historical synthetic quote rights are NOT cryptographically attested.
    """
    deny = "Synthetic paper ledger integrity unavailable"
    try:
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        existing = tables & PAPER_TABLES
        if not existing:
            return {"paperSchemaPresent": False, "verifiedWallets": 0,
                    "verifiedAssumedFills": 0}
        if existing != PAPER_TABLES:
            raise PaperRecoveryDenied(deny)

        wallets = db.execute("""SELECT user_id, account_id, seeded_cents,
            cash_cents FROM tenant_paper_wallets""").fetchall()
        if len(wallets) > 10000:
            raise PaperRecoveryDenied(deny)
        expected = {}
        for user, account, seed, cash in wallets:
            if (not _canonical_uuid(user) or not _canonical_uuid(account)
                    or type(seed) is not int or type(cash) is not int
                    or not 0 < seed <= 100000000000
                    or not 0 <= cash <= 100000000000):
                raise PaperRecoveryDenied(deny)
            expected[(user, account)] = {
                "cash": seed, "actualCash": cash, "positions": {},
            }
        events = db.execute("""SELECT user_id,account_id,request_id,
            request_sha256,side,asset_class,symbol,quantity,quote_price,
            estimated_friction,signed_cash_change_cents,cash_after_cents,
            provider,observed_at,created_at FROM tenant_paper_events ORDER BY rowid"""
        ).fetchall()
        if len(events) > 50000:
            raise PaperRecoveryDenied(deny)
        for row in events:
            (user, account, request_id, digest, side, asset, symbol,
             quantity, price, friction, delta, after, provider, observed,
             created) = row
            wallet = expected.get((user, account))
            if (wallet is None or not _canonical_uuid(request_id)
                    or not isinstance(digest, str) or not _SHA.fullmatch(digest)
                    or side not in ("BUY", "SELL") or asset not in _ASSETS
                    or not isinstance(symbol, str) or not 0 < len(symbol) <= 96
                    or symbol.strip() != symbol
                    or not all(c.isalnum() or c in "._:-" for c in symbol)
                    or not isinstance(provider, str) or not provider.strip()
                    or not isinstance(observed, str) or not observed.strip()
                    or type(delta) is not int or type(after) is not int):
                raise PaperRecoveryDenied(deny)
            # Both the source observation and local paper event must be
            # independently parseable UTC timestamps. A recovered event
            # cannot predate the observation it purports to have used.
            if _event_time(observed) > _event_time(created):
                raise PaperRecoveryDenied(deny)
            qty = _decimal(quantity, positive=True)
            px = _decimal(price, positive=True)
            costs = _decimal(friction)
            if side == "BUY":
                required = -_cents((px + costs) * qty, ROUND_UP)
            else:
                if px <= costs:
                    raise PaperRecoveryDenied(deny)
                required = _cents((px - costs) * qty, ROUND_DOWN)
            if (required != delta or not required
                    or abs(delta) > 100000000000):
                raise PaperRecoveryDenied(deny)
            wallet["cash"] += delta
            if wallet["cash"] < 0 or wallet["cash"] != after:
                raise PaperRecoveryDenied(deny)
            key = (asset, symbol)
            position = wallet["positions"].setdefault(
                key, {"qty": Decimal(0), "basis": 0, "realized": 0})
            if side == "BUY":
                position["qty"] += qty
                position["basis"] += -delta
            else:
                held = position["qty"]
                if held <= 0 or qty > held:
                    raise PaperRecoveryDenied(deny)
                released = position["basis"] if qty == held else int(
                    (Decimal(position["basis"]) * qty / held)
                    .to_integral_value(rounding=ROUND_UP))
                position["qty"] -= qty
                position["basis"] -= released
                position["realized"] += delta - released
        if any(w["cash"] != w["actualCash"] for w in expected.values()):
            raise PaperRecoveryDenied(deny)

        positions = db.execute("""SELECT user_id,account_id,asset_class,
            symbol,quantity,cost_basis_cents,realized_cents
            FROM tenant_paper_positions""").fetchall()
        if len(positions) > 50000:
            raise PaperRecoveryDenied(deny)
        seen = set()
        for user, account, asset, symbol, quantity, basis, realized in positions:
            wallet = expected.get((user, account))
            key = (asset, symbol)
            record = wallet["positions"].get(key) if wallet else None
            if (record is None or (user, account, asset, symbol) in seen
                    or type(basis) is not int or type(realized) is not int
                    or basis < 0 or _decimal(quantity) != record["qty"]
                    or basis != record["basis"]
                    or realized != record["realized"]):
                raise PaperRecoveryDenied(deny)
            seen.add((user, account, asset, symbol))
        if sum(len(w["positions"]) for w in expected.values()) != len(seen):
            raise PaperRecoveryDenied(deny)
        return {"paperSchemaPresent": True, "verifiedWallets": len(wallets),
                "verifiedAssumedFills": len(events)}
    except PaperRecoveryDenied:
        raise
    except (sqlite3.Error, KeyError, IndexError, ArithmeticError, TypeError,
            ValueError, InvalidOperation):
        raise PaperRecoveryDenied(deny) from None
