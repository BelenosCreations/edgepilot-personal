"""Synthetic, read-only paper BUY cost preview. Never stores orders or money.

Inputs are independently supplied paper funds, explicit estimated friction, and
provider-rights-verified market evidence. This boundary is NOT a broker adapter,
execution engine, signal, or persistent paper portfolio.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP
from collections.abc import Mapping

from .research_intelligence import Observation, ResearchUnavailable
from .risk import buying_capacity, RiskBlocked

CENT = Decimal("0.01")
MAX = Decimal("1000000000000")
RISK_KEYS = frozenset({
    "public_equity", "independent_equity", "balance_source", "protected_pct",
    "spend_cap", "per_trade_cap", "broker_buying_power", "attributed_exposure",
    "other_exposure", "open_orders", "unreconciled_orders", "fresh",
    "reconciled", "pending_external_sale",
})


class PaperPreviewUnavailable(ValueError):
    """Unsafe or unverified hypothetical preview; no side effect took place."""


def _number(value, name, *, positive=False):
    # Do not introduce floating point rounding into paper cash or risk amounts.
    if isinstance(value, (bool, float)) or not isinstance(value, (str, int, Decimal)):
        raise PaperPreviewUnavailable("Invalid " + name)
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise PaperPreviewUnavailable("Invalid " + name) from None
    if (not amount.is_finite() or amount < 0 or amount > MAX
            or (positive and amount == 0)):
        raise PaperPreviewUnavailable("Invalid " + name)
    return amount


def preview_paper_buy(*, observation, now, quantity, fee_per_unit,
                      slippage_per_unit, paper_cash, risk_inputs):
    """Return an explicitly non-executable, single-leg paper BUY cost scenario.

    The quote is validated at *preview time*, including provider analysis
    rights, exact observed/received timestamps, market state and staleness.
    All fees/slippage and paper funds must be supplied explicitly. It is not
    possible to turn this result into an order through this module.
    """
    if not isinstance(observation, Mapping):
        raise PaperPreviewUnavailable("Structured source evidence required")
    try:
        quote = Observation.validate(observation, now=now)
    except ResearchUnavailable as exc:
        raise PaperPreviewUnavailable("Market evidence unavailable: " + str(exc)) from None
    if quote.asset_class not in ("stock", "etf", "crypto"):
        # Prediction contracts need separate settlement, liquidity and payout
        # modelling, not generic share-price cost math.
        raise PaperPreviewUnavailable("This asset requires a separate paper model")
    qty = _number(quantity, "quantity", positive=True)
    if qty.as_tuple().exponent < -18:
        raise PaperPreviewUnavailable("Quantity precision exceeds supported units")
    fees = _number(fee_per_unit, "estimated fee per unit")
    slip = _number(slippage_per_unit, "assumed slippage per unit")
    cash = _number(paper_cash, "independent paper cash")
    if not isinstance(risk_inputs, Mapping) or set(risk_inputs) != RISK_KEYS:
        raise PaperPreviewUnavailable("Complete independent risk inputs required")
    try:
        limits = buying_capacity(**risk_inputs)
    except (RiskBlocked, ValueError, TypeError, InvalidOperation):
        raise PaperPreviewUnavailable("Risk policy unavailable or unreconciled") from None
    try:
        # The ask is a reference observation, NOT a fill price. Explicit
        # nonnegative adverse price movement and fee assumptions are required.
        unit_cost = quote.ask + slip + fees
        total = (qty * unit_cost).quantize(CENT, rounding=ROUND_UP)
        limit = _number(limits["singleTradeLimit"], "single-trade limit")
        if total <= 0 or total > cash or total > limit:
            raise PaperPreviewUnavailable("Paper cash or risk cap insufficient")
        return {
            "mode": "PAPER_PREVIEW_ONLY",
            "recorded": False,
            "orderSubmitted": False,
            "tradeAllowed": False,
            "assetClass": quote.asset_class,
            "symbol": quote.symbol,
            "source": quote.rights.provider,
            "observedAt": quote.observed_at.isoformat(),
            "receivedAt": quote.received_at.isoformat(),
            "quotedAsk": str(quote.ask),
            "quantity": str(qty),
            "feePerUnitAssumption": str(fees),
            "slippagePerUnitAssumption": str(slip),
            "estimatedTotalCost": str(total),
            "paperCashAfter": str((cash - total).quantize(CENT, rounding=ROUND_DOWN)),
            "singleTradeRiskLimit": str(limit),
            "warning": ("Hypothetical BUY cost only. Bid/ask may not be "
                        "executable; fees, slippage and future prices are "
                        "uncertain. No order, broker call, ledger entry or "
                        "bank transfer was made."),
        }
    except (InvalidOperation, OverflowError):
        raise PaperPreviewUnavailable("Paper preview arithmetic unavailable") from None
