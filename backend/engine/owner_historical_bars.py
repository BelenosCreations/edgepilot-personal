"""Validate Public historical-bar payload structure and observed timestamps.

Source authentication and linked-account verification belong to the caller.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re


class HistoryUnavailable(ValueError):
    """A source payload is incomplete or unsuitable for trusted display."""


_SYMBOL = re.compile(r"[A-Z0-9.^_-]{1,30}", re.ASCII)
_PRICE = re.compile(r"(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,12})?", re.ASCII)
_VOLUME = re.compile(r"(?:0|[1-9][0-9]{0,18})", re.ASCII)
_CRYPTO_VOLUME = re.compile(r"(?:0|[1-9][0-9]{0,18})(?:\.[0-9]{1,18})?", re.ASCII)
_TYPES = frozenset(("EQUITY", "CRYPTO"))
_PERIODS = frozenset(("DAY", "WEEK", "MONTH", "QUARTER", "HALF_YEAR",
                      "YEAR", "FIVE_YEARS", "TEN_YEARS", "ALL", "YTD",
                      "SINCE_PURCHASE"))
_MAX_BARS = 5000


def _utc(raw, name):
    if not isinstance(raw, datetime) or raw.tzinfo is None:
        raise HistoryUnavailable(name + " must be an aware UTC datetime")
    if raw.utcoffset().total_seconds() != 0:
        raise HistoryUnavailable(name + " must be UTC")
    return raw.astimezone(timezone.utc)


def _timestamp(value, received):
    if not isinstance(value, str) or len(value) > 40 or "T" not in value:
        raise HistoryUnavailable("Historical timestamp unavailable")
    try:
        time = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if time.tzinfo is None:
            raise ValueError("Missing timezone")
        time = time.astimezone(timezone.utc)
    except (ValueError, OverflowError, TypeError):
        raise HistoryUnavailable("Historical timestamp unavailable") from None
    if time > received:
        raise HistoryUnavailable("Future historical bar refused")
    return time


def _price(value):
    if not isinstance(value, str) or _PRICE.fullmatch(value) is None:
        raise HistoryUnavailable("Source OHLC price unavailable")
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise HistoryUnavailable("Source OHLC price unavailable") from None
    if not amount.is_finite() or amount <= 0:
        raise HistoryUnavailable("Source OHLC price unavailable")
    return amount


def _volume(value, *, crypto=False):
    if isinstance(value, bool):
        raise HistoryUnavailable("Source volume unavailable")
    if isinstance(value, int):
        if value < 0 or value > 9999999999999999999:
            raise HistoryUnavailable("Source volume unavailable")
        return str(value)
    if crypto and isinstance(value, Decimal):
        if not value.is_finite() or not -18 <= value.as_tuple().exponent <= 18:
            raise HistoryUnavailable("Source volume unavailable")
        value = format(value, "f")
    pattern = _CRYPTO_VOLUME if crypto else _VOLUME
    if isinstance(value, str) and pattern.fullmatch(value):
        return value
    raise HistoryUnavailable("Source volume unavailable")


def normalize_bars(payload, *, symbol, instrument_type, period, received_at):
    """Validate synthetic/externally supplied bars; never certify actual origin.

    Any future live adapter must authenticate identity, account ownership,
    provider request/response and licensing BEFORE this output may be used.
    No calendar-fill, imputed bar, P&L or percent return is ever generated.
    """
    received = _utc(received_at, "Receipt time")
    if (not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol)
            or not isinstance(instrument_type, str) or instrument_type not in _TYPES
            or not isinstance(period, str) or period not in _PERIODS):
        raise HistoryUnavailable("Unrecognized request context")
    if (not isinstance(payload, dict) or payload.get("symbol") != symbol
            or payload.get("period") != period):
        raise HistoryUnavailable("Source symbol or period mismatch")
    regular = payload.get("regularMarket")
    if not isinstance(regular, dict):
        raise HistoryUnavailable("Regular-market source section unavailable")
    rows = regular.get("bars")
    if not isinstance(rows, list) or not 1 <= len(rows) <= _MAX_BARS:
        raise HistoryUnavailable("Historical source bars unavailable")
    leading = payload.get("leadingFill")
    leading_end = None
    if leading is not None:
        if not isinstance(leading, dict):
            raise HistoryUnavailable("Malformed chart lead-in")
        leading_start = _timestamp(leading.get("startTimestamp"), received)
        leading_end = _timestamp(leading.get("endTimestamp"), received)
        if leading_start > leading_end:
            raise HistoryUnavailable("Malformed chart lead-in")
    out = []
    previous = None
    for row in rows:
        if not isinstance(row, dict):
            raise HistoryUnavailable("Malformed source bar")
        when = _timestamp(row.get("timestamp"), received)
        if previous is not None and when <= previous:
            raise HistoryUnavailable("Historical bars duplicated or out of order")
        prices = {key: _price(row.get(key))
                  for key in ("open", "high", "low", "close")}
        if (prices["high"] < max(prices["open"], prices["close"])
                or prices["low"] > min(prices["open"], prices["close"])
                or prices["low"] > prices["high"]):
            raise HistoryUnavailable("Source OHLC relationships invalid")
        volume = _volume(row.get("volume"), crypto=instrument_type == "CRYPTO")
        previous = when
        if leading_end is not None and when <= leading_end:
            continue
        out.append({
            "timestamp": when.isoformat(),
            **{key: row[key] for key in ("open", "high", "low", "close")},
            "volume": volume,
        })
    if not out:
        raise HistoryUnavailable("Historical source bars unavailable")
    return {
        "providerLabel": "Public API (unverified source payload)",
        "expectedSourcePath": "historicdata v2",
        "symbol": symbol, "assetClass": instrument_type, "period": period,
        "observedAt": received.isoformat(), "bars": out, "barCount": len(out),
        # The adapter is not wired to a verified source or a specific owner.
        "providerRequestAuthenticated": False,
        "accountScopeVerified": False,
        "dataRightsVerified": False,
        "cacheRightsVerified": False,
        "redistributionAllowed": False,
        "paperFillEligible": False,
        "productionEligible": False,
        "performanceVerified": False,
        "dataPersisted": False,
        "calendarCompletenessVerified": False,
        "leadingFillExcluded": True,
        "warning": "Validated supplied bar structure only; origin, entitlement, "
                   "coverage, adjusted prices and use rights remain unverified.",
    }
