"""Offline-only, read-only, per-account historical realized paper loss stop.

This is a risk research primitive, NOT an executable fill guard. It reads only
verified /dev/shm synthetic fixtures and never imports into the HTTP app.
It cannot mark open paper positions, prove market-data rights, or authorize a
trade. A real paper writer needs an atomic, durable, authenticated stop latch.
"""
from __future__ import annotations

from contextlib import closing
from decimal import Decimal, InvalidOperation, ROUND_UP
from urllib.parse import quote as url_quote
import sqlite3

from . import shadow_storage
from . import tenant_paper_ledger
from . import tenant_paper_recovery_audit

CENT = Decimal("0.01")
MAX = Decimal("1000000000")


class PaperLossStopDenied(ValueError):
    """Sanitized offline integrity, scope, or risk-boundary refusal."""


def _stop_cents(value):
    if isinstance(value, (bool, float)) or not isinstance(value, (str, int, Decimal)):
        raise PaperLossStopDenied("Synthetic paper loss-stop policy unavailable")
    try:
        amount = Decimal(str(value))
        if (not amount.is_finite() or amount < CENT or amount > MAX
                or amount != amount.quantize(CENT)):
            raise PaperLossStopDenied("Synthetic paper loss-stop policy unavailable")
        return int(amount * 100)
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        raise PaperLossStopDenied("Synthetic paper loss-stop policy unavailable") from None


def _money(cents):
    return str((Decimal(cents) / 100).quantize(CENT))


def inspect_realized_paper_loss_stop(
        path, *, principal_user_id, account_id, max_realized_loss):
    """Inspect historical per-account assumed-fill P&L, never place a fill.

    Every event is first audited in a consistent read transaction. The worst
    cumulative *realized* P&L (including estimated assumed-fill friction) is
    reconstructed from durable append-order events; a later gain cannot erase
    a previously breached stop. No quote is fetched or marked to market.
    The caller still must derive principal identity from a trusted session
    before considering any future API integration.
    """
    limit = _stop_cents(max_realized_loss)
    deny = "Synthetic paper loss-stop integrity unavailable"
    try:
        source, _ = shadow_storage.require_isolated_source(path)
        uri = "file:" + url_quote(str(source), safe="/") + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=5)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN")
            verified = tenant_paper_recovery_audit.audit_tenant_paper_ledger(db)
            if verified["paperSchemaPresent"] is not True:
                raise PaperLossStopDenied(deny)
            user, account = tenant_paper_ledger._scope(
                db, principal_user_id, account_id)
            events = db.execute("""SELECT side,asset_class,symbol,quantity,
                signed_cash_change_cents FROM tenant_paper_events
                WHERE user_id=? AND account_id=? ORDER BY rowid""",
                (user, account)).fetchall()
            positions = {}
            cumulative = 0
            worst = 0
            assumed_sales = 0
            for side, asset, symbol, raw_qty, delta in events:
                units = Decimal(raw_qty)  # validated in the complete audit
                key = (asset, symbol)
                position = positions.setdefault(
                    key, {"qty": Decimal(0), "basis": 0})
                if side == "BUY":
                    position["qty"] += units
                    position["basis"] -= delta
                else:
                    held = position["qty"]
                    release = (position["basis"] if units == held else int(
                        (Decimal(position["basis"]) * units / held)
                        .to_integral_value(rounding=ROUND_UP)))
                    position["qty"] -= units
                    position["basis"] -= release
                    cumulative += delta - release
                    worst = min(worst, cumulative)
                    assumed_sales += 1
            return {
                "paperOnly": True,
                "actualTradeAllowed": False,
                "assumedFillAuthorized": False,
                "maxRealizedLoss": _money(limit),
                "currentCumulativeRealizedPnL": _money(cumulative),
                "worstHistoricalCumulativeRealizedPnL": _money(worst),
                "historicalStopBreached": worst <= -limit,
                "wouldBlockNewAssumedFills": worst <= -limit,
                "assumedFillsReviewed": len(events),
                "assumedSalesReviewed": assumed_sales,
                "warning": (
                    "Offline historical realized paper P&L only. Open-position "
                    "losses, future prices and external execution are NOT assessed. "
                    "This inspection cannot block an active paper writer; production "
                    "fills, real trading and transfers remain disabled."),
            }
    except PaperLossStopDenied:
        raise
    except (shadow_storage.MemoryStorageError, tenant_paper_ledger.PaperLedgerDenied,
            tenant_paper_recovery_audit.PaperRecoveryDenied, sqlite3.Error,
            OSError, InvalidOperation, ValueError, TypeError, ZeroDivisionError):
        raise PaperLossStopDenied(deny) from None
