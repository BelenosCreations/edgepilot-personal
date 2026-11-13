"""Pure, fail-closed exposure calculation for a FUTURE risk-control preview.

This module performs no broker calls, account mutations, orders, transfers or
automation. Inputs must come from a fresh, separately reconciled snapshot; the
caller must not infer buying power from the portfolio total alone.
"""
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP
from .ledger import dec

class RiskBlocked(ValueError):
    pass

LIMIT = Decimal("1000000000000000000")
CENT = Decimal("0.01")


def _nonnegative(value, label):
    # Avoid converting booleans to 0/1, accepting NaN/Infinity, or relying on
    # floats in the output. Decimal itself guards finite values.
    if isinstance(value, bool):
        raise RiskBlocked("Invalid " + label)
    try:
        number = dec(value)
    except (ValueError, TypeError, InvalidOperation, OverflowError):
        raise RiskBlocked("Invalid " + label) from None
    if number < 0 or number > LIMIT:
        raise RiskBlocked("Invalid " + label)
    return number


def _floor_money(number):
    """Never round up the stated amount available to put at risk."""
    return str(number.quantize(CENT, rounding=ROUND_DOWN))


def _ceiling_money(number):
    """Never round down the amount intended to remain protected."""
    return str(number.quantize(CENT, rounding=ROUND_UP))


def buying_capacity(*, public_equity, independent_equity=None,
                    balance_source="public", protected_pct,
                    spend_cap, per_trade_cap, broker_buying_power,
                    attributed_exposure, other_exposure, open_orders,
                    unreconciled_orders, fresh, reconciled,
                    pending_external_sale=False):
    """Calculate conservative *potential* capacity, not trading permission.

    Protected percentage contract: 0–99 inclusive. A 100% setting is
    intentionally unavailable; it would eliminate the trading allocation.
    None of the returned amounts authorize orders, funding or transfers.
    """
    if fresh is not True or reconciled is not True:
        raise RiskBlocked("Broker data stale or not reconciled")
    if pending_external_sale:
        raise RiskBlocked("Manual sale needs repurchase policy decision")
    if balance_source not in ("public", "independent"):
        raise RiskBlocked("Invalid balance source")

    public = _nonnegative(public_equity, "Public account equity")
    basis = public if balance_source == "public" else (
        _nonnegative(independent_equity, "independent EdgePilot allocation"))
    if independent_equity is not None:
        _nonnegative(independent_equity, "independent EdgePilot allocation")
    pct = _nonnegative(protected_pct, "protected balance percentage")
    if pct > Decimal("99"):
        raise RiskBlocked("Protected percentage must be between 0 and 99")
    spending = _nonnegative(spend_cap, "spend cap")
    trade_cap = _nonnegative(per_trade_cap, "per-trade cap")
    buying_power = _nonnegative(broker_buying_power, "broker buying power")
    attributions = _nonnegative(attributed_exposure, "EdgePilot attributed exposure")
    other = _nonnegative(other_exposure, "other exposure")
    orders = _nonnegative(open_orders, "open orders")
    unreconciled = _nonnegative(unreconciled_orders, "unreconciled orders")
    if public <= 0 or basis <= 0 or basis > public:
        raise RiskBlocked("Allocation exceeds available Public account equity")

    # All types of exposure are counted together; changing strategies or a
    # selected balance cannot hide already committed account-level risk.
    allowance = min(spending, basis * (Decimal("100") - pct) / Decimal("100"))
    outstanding = attributions + other + orders + unreconciled
    remaining = max(Decimal("0"), min(allowance - outstanding, buying_power))
    maximum_trade = min(remaining, trade_cap)
    return {
        "riskBudget": _floor_money(allowance),
        "remainingToRisk": _floor_money(remaining),
        "singleTradeLimit": _floor_money(maximum_trade),
        "protectedValue": _ceiling_money(basis * pct / Decimal("100")),
        "warning": ("Limits reduce potential exposure but cannot guarantee "
                    "against market losses. This is not trading authorization.")
    }
