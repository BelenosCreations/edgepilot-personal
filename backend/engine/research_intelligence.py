"""Free-first provider-neutral research boundary. No network or trade execution.

A market observation is not an executable quote. Every input must explicitly
carry provider, timestamp, category, verified instrument coverage and data
permissions. Fail closed when inputs are missing/stale or fees are unknown.
No LLM, brokerage credentials, persistent accounts or jobs are used here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from statistics import mean
from typing import Mapping

ASSET_CLASSES = frozenset({"stock", "etf", "crypto", "prediction"})
STATES = frozenset({"open", "halted", "closed", "expired"})
DEFAULT_STALENESS_SECONDS = {"stock": 120, "etf": 120, "crypto": 45, "prediction": 30}
MAX_INPUT_BARS = 5000


class ResearchUnavailable(ValueError):
    """No qualifying evidence or valid source for a research computation."""


def decimal(value, label, *, positive=False, zero_ok=True):
    if isinstance(value, bool) or value is None or isinstance(value, (list, dict)):
        raise ResearchUnavailable(label + " must be a finite number")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ResearchUnavailable(label + " must be a finite number") from None
    if not number.is_finite() or (positive and number <= 0) or (
            not zero_ok and number == 0) or number < 0:
        raise ResearchUnavailable(label + " is outside the supported range")
    return number


def utc_time(value, label):
    if not isinstance(value, str) or len(value) > 40:
        raise ResearchUnavailable(label + " must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ResearchUnavailable(label + " must be an ISO-8601 UTC timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ResearchUnavailable(label + " must explicitly be in UTC")
    return parsed.astimezone(timezone.utc)


def _text(value, label, limit=128):
    if not isinstance(value, str) or not 1 <= len(value) <= limit or value.strip() != value:
        raise ResearchUnavailable(label + " is missing or malformed")
    if not all(x.isalnum() or x in "._:-" for x in value):
        raise ResearchUnavailable(label + " is malformed")
    return value


@dataclass(frozen=True)
class ProviderRights:
    """Explicit permission assertions verified elsewhere by a provider adapter."""

    provider: str
    allowed_analysis: bool
    allowed_cache: bool
    allowed_redistribution: bool
    verified_coverage: bool

    @classmethod
    def from_mapping(cls, value):
        if not isinstance(value, Mapping) or set(value) != {
                "provider", "analysis", "cache", "redistribute", "coverageVerified"}:
            raise ResearchUnavailable("Provider licensing and coverage status required")
        provider = _text(value["provider"], "provider")
        for key in ("analysis", "cache", "redistribute", "coverageVerified"):
            if type(value[key]) is not bool:
                raise ResearchUnavailable("Provider rights must be explicit booleans")
        if not value["analysis"] or not value["coverageVerified"]:
            raise ResearchUnavailable("Provider analysis rights or asset coverage unverified")
        return cls(provider, value["analysis"], value["cache"],
                   value["redistribute"], value["coverageVerified"])


@dataclass(frozen=True)
class Observation:
    """Immutable, provenance-bearing market-data sample; no order semantics."""

    asset_class: str
    symbol: str
    rights: ProviderRights
    observed_at: datetime
    received_at: datetime
    bid: Decimal
    ask: Decimal
    last: Decimal
    volume: Decimal
    state: str
    book_depth: Decimal | None
    expires_at: datetime | None
    settlement_rules: str | None

    @classmethod
    def validate(cls, payload, *, now, staleness_seconds=None):
        if not isinstance(payload, Mapping):
            raise ResearchUnavailable("Observation must be structured market data")
        required = {"assetClass", "symbol", "rights", "observedAt", "receivedAt",
                    "bid", "ask", "last", "volume", "state"}
        optional = {"bookDepth", "expiresAt", "settlementRules"}
        if not required.issubset(payload) or set(payload) - (required | optional):
            raise ResearchUnavailable("Observation fields are missing or unrecognized")
        asset = payload["assetClass"]
        if asset not in ASSET_CLASSES:
            raise ResearchUnavailable("Unsupported or unverified market category")
        rights = ProviderRights.from_mapping(payload["rights"])
        symbol = _text(payload["symbol"], "symbol", 96)
        when = utc_time(payload["observedAt"], "observedAt")
        received = utc_time(payload["receivedAt"], "receivedAt")
        current = utc_time(now, "now") if isinstance(now, str) else now
        if not isinstance(current, datetime) or current.tzinfo is None or (
                current.utcoffset().total_seconds() != 0):
            raise ResearchUnavailable("Explicit current UTC time required")
        maximum = (DEFAULT_STALENESS_SECONDS[asset] if staleness_seconds is None
                   else staleness_seconds)
        if type(maximum) is not int or not 1 <= maximum <= 3600:
            raise ResearchUnavailable("Invalid staleness policy")
        # Never accept stale book data or a future-dated observation.
        if not 0 <= (current - when).total_seconds() <= maximum:
            raise ResearchUnavailable("Missing, future-dated or stale market evidence")
        if not 0 <= (current - received).total_seconds() <= maximum:
            raise ResearchUnavailable("Received market data is stale or future-dated")
        if received < when:
            raise ResearchUnavailable("Market observation timestamps inconsistent")
        bid = decimal(payload["bid"], "bid", positive=True)
        ask = decimal(payload["ask"], "ask", positive=True)
        last = decimal(payload["last"], "last", positive=True)
        volume = decimal(payload["volume"], "volume")
        if bid > ask:
            raise ResearchUnavailable("Crossed or inconsistent market book")
        state = payload["state"]
        if state not in STATES or state != "open":
            raise ResearchUnavailable("Trading status unverified or market unavailable")
        depth = payload.get("bookDepth")
        depth = None if depth is None else decimal(depth, "bookDepth", positive=True)
        expires = payload.get("expiresAt")
        expiry = utc_time(expires, "expiresAt") if expires is not None else None
        rules = payload.get("settlementRules")
        if asset == "prediction":
            if not expiry or expiry <= current or not isinstance(rules, str) or (
                    not 8 <= len(rules.strip()) <= 1024) or depth is None:
                raise ResearchUnavailable("Prediction settlement, expiry and book depth required")
            if not Decimal("0") < bid <= ask <= Decimal("1"):
                raise ResearchUnavailable("Prediction shares require prices between zero and one")
        elif expiry is not None or rules is not None:
            raise ResearchUnavailable("Non-contract observation has settlement metadata")
        return cls(asset, symbol, rights, when, received, bid, ask, last,
                   volume, state, depth, expiry, rules)

    def summary(self):
        """Research only: use the bid/ask, never claim a midpoint is fillable."""
        return {"assetClass": self.asset_class, "symbol": self.symbol,
                "provider": self.rights.provider,
                "observedAt": self.observed_at.isoformat(),
                "bid": str(self.bid), "ask": str(self.ask),
                "spread": str(self.ask - self.bid),
                "midpointReferenceOnly": str((self.ask + self.bid) / 2),
                "volume": str(self.volume),
                "executableQuote": False, "tradeAllowed": False,
                "cacheAllowed": self.rights.allowed_cache,
                "redistributionAllowed": self.rights.allowed_redistribution,
                "settlementVerified": self.asset_class != "prediction" or bool(
                    self.settlement_rules)}


def prediction_yes_scenario(observation, *, calibrated_probability,
                            commission, exchange_fee, settlement_fee,
                            slippage, quantity):
    """Conservative read-only scenario on actual ask price, not on a midpoint.

    The claimed probability must come with independent calibration evidence;
    the model never supplies or guesses it. Break-even ignores uncertain
    fills and is not a recommendation.
    """
    if not isinstance(observation, Observation) or observation.asset_class != "prediction":
        raise ResearchUnavailable("Verified prediction quote required")
    if not isinstance(calibrated_probability, Mapping) or set(calibrated_probability) != {
            "probability", "basis", "heldOutSamples", "validatedAt"}:
        raise ResearchUnavailable("Out-of-sample probability evidence required")
    p = decimal(calibrated_probability["probability"], "probability")
    if p > 1 or not isinstance(calibrated_probability["basis"], str) or (
            calibrated_probability["basis"] != "chronological-held-out") or (
            type(calibrated_probability["heldOutSamples"]) is not int or
            calibrated_probability["heldOutSamples"] < 30):
        raise ResearchUnavailable("Calibrated probability requires held-out evidence")
    validated = utc_time(calibrated_probability["validatedAt"], "validatedAt")
    if validated > observation.observed_at:
        raise ResearchUnavailable("Probability validation cannot postdate observation")
    qty = decimal(quantity, "quantity", positive=True)
    if observation.book_depth is None or qty > observation.book_depth:
        raise ResearchUnavailable("Order book depth is insufficient for scenario")
    fees = tuple(decimal(v, k) for k, v in (
        ("commission", commission), ("exchangeFee", exchange_fee),
        ("settlementFee", settlement_fee), ("slippage", slippage)))
    total_fees = sum(fees)
    ask = observation.ask
    total_cost_per_share = ask + total_fees
    if total_cost_per_share >= 1:
        return {"eligible": False, "reason": "Conservative costs exceed possible payout",
                "tradeAllowed": False}
    net_ev_per_share = p - total_cost_per_share
    return {"eligible": net_ev_per_share > 0,
            "netExpectedValueTotal": str(qty * net_ev_per_share),
            "breakEvenProbability": str(total_cost_per_share),
            "entryReference": str(ask),
            "expectedValueIsForecastNotFact": True,
            "calibratedEvidenceSamples": calibrated_probability["heldOutSamples"],
            "tradeAllowed": False,
            "warning": "Fill, payout, fees and calibrated probability are uncertain; no order submitted."}


def chronological_momentum(bars, *, lookback=5, min_bars=20):
    """Deterministic, no-AI baseline; timestamps must be increasing, no future bars.

    Not a calibrated probability, order instruction or assertion of alpha.
    """
    if (type(lookback) is not int or not 2 <= lookback <= 60 or
            type(min_bars) is not int or not 10 <= min_bars <= 500 or
            not isinstance(bars, list) or not min_bars <= len(bars) <= MAX_INPUT_BARS or
            len(bars) < lookback + 1):
        raise ResearchUnavailable("Insufficient or invalid chronological history")
    times, closes = [], []
    for row in bars:
        if not isinstance(row, Mapping) or set(row) != {"at", "close"}:
            raise ResearchUnavailable("Historical bars must include exact timestamps and close")
        at = utc_time(row["at"], "at")
        close = decimal(row["close"], "close", positive=True)
        if times and at <= times[-1]:
            raise ResearchUnavailable("History is duplicated or not chronological")
        times.append(at)
        closes.append(close)
    reference = closes[-(lookback + 1)]
    change = closes[-1] / reference - 1
    returns = [float(closes[i] / closes[i - 1] - 1)
               for i in range(len(closes) - lookback, len(closes))]
    # Sample volatility is a descriptive statistic, not a forecast or annualized claim.
    avg = mean(returns)
    variation = mean((r - avg) ** 2 for r in returns)
    return {"signal": "positive-momentum" if change > 0 else (
                "negative-momentum" if change < 0 else "flat"),
            "lookbackBars": lookback, "observedChange": str(change),
            "realizedStdDevPerBar": str(variation ** 0.5),
            "latestAt": times[-1].isoformat(),
            "predictiveProbability": None,
            "tradeAllowed": False,
            "aiCalls": 0}
