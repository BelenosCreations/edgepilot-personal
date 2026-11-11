"""Read-only paired forward-research audit; not a proof of profitable trading.

Compares chronologically issued, independently validated binary forecasts
on the SAME verified outcomes. Assesses calibration quality and attributable
measured optional-AI costs without a broker, AI request, portfolio, order,
subscription, user secret, networking or automatic investment decisions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping

from . import research_intelligence as research

MAX_MATCHED_EVENTS = 5000
MIN_EVENTS_FOR_DESCRIPTIVE_REVIEW = 30
MIN_DISTINCT_DAYS = 7
_KEYS = frozenset({
    "eventId", "assetClass", "outcomeDefinition", "source",
    "observedAt", "baselineIssuedAt", "assistedIssuedAt",
    "baselineValidationEndAt", "assistedValidationEndAt", "settledAt",
    "verifiedOutcome", "outcomeVerified", "baselineProbability",
    "assistedProbability", "baselineValidationSamples",
    "assistedValidationSamples", "baselineValidationMethod",
    "assistedValidationMethod", "aiActualCostMicroUsd",
    "aiCostMeasured", "independentModelValidation",
})


class AuditUnavailable(ValueError):
    """Reject unverified outcomes, leakage and unknown AI costs."""


def _utc(value, label):
    try:
        return research.utc_time(value, label)
    except research.ResearchUnavailable:
        raise AuditUnavailable("Explicit verified UTC timestamps required") from None


def _probability(value, label):
    try:
        p = research.decimal(value, label)
    except research.ResearchUnavailable:
        raise AuditUnavailable("Finite calibrated probability required") from None
    if p > 1:
        raise AuditUnavailable("Calibrated probability outside unit interval")
    return p


def _counter(value, label, maximum=10**12):
    if type(value) is not int or not 0 <= value <= maximum:
        raise AuditUnavailable(label + " must be a bounded integer")
    return value


def evaluate_matched_forward(records, *, now):
    """Compare a single, strictly separated research cohort.

    Caller must provide provider-confirmed outcomes, precommitted event
    definitions and independent validation. Those external assertions are
    NOT verified by this pure function: do not wire it to a client route.
    No trained model or AI output is trusted to supply verified outcomes.
    """
    current = _utc(now, "now")
    if (type(records) is not list or not 1 <= len(records) <= MAX_MATCHED_EVENTS):
        raise AuditUnavailable("A bounded nonempty forward cohort is required")
    seen = set()
    dates = set()
    scores_baseline = []
    scores_assisted = []
    costs = 0
    class_name = None
    definition = None
    source = None

    for item in records:
        if not isinstance(item, Mapping) or set(item) != _KEYS:
            raise AuditUnavailable("Unexpected cohort fields or private member data")
        try:
            event = research._text(item["eventId"], "eventId", 96)
            item_source = research._text(item["source"], "source", 128)
            item_definition = research._text(
                item["outcomeDefinition"], "outcomeDefinition", 120)
        except research.ResearchUnavailable:
            raise AuditUnavailable("Unverified cohort provenance") from None
        asset = item["assetClass"]
        if type(asset) is not str or asset not in research.ASSET_CLASSES:
            raise AuditUnavailable("Unverified research category")
        if (class_name is None):
            class_name, definition, source = asset, item_definition, item_source
        if (asset, item_definition, item_source) != (class_name, definition, source):
            raise AuditUnavailable("Do not mix asset, event meaning or source")
        if event in seen:
            raise AuditUnavailable("Duplicated settlement identifier")
        seen.add(event)
        if type(item["outcomeVerified"]) is not bool or item["outcomeVerified"] is not True:
            raise AuditUnavailable("Independent outcome verification required")
        if type(item["independentModelValidation"]) is not bool or (
                item["independentModelValidation"] is not True):
            raise AuditUnavailable("AI prose cannot certify probabilities")
        if type(item["aiCostMeasured"]) is not bool or item["aiCostMeasured"] is not True:
            raise AuditUnavailable("Actual attributable AI usage cost required")
        if type(item["verifiedOutcome"]) is not int or item["verifiedOutcome"] not in (0, 1):
            raise AuditUnavailable("Binary verified outcome required")
        for name in ("baselineValidationSamples", "assistedValidationSamples"):
            if _counter(item[name], name, MAX_MATCHED_EVENTS) < 30:
                raise AuditUnavailable("Independent held-out calibration samples required")
        if (item["baselineValidationMethod"] != "chronological-held-out" or
                item["assistedValidationMethod"] != "chronological-held-out"):
            raise AuditUnavailable("Validation must be chronological and held out")
        observed = _utc(item["observedAt"], "observedAt")
        base_at = _utc(item["baselineIssuedAt"], "baselineIssuedAt")
        assist_at = _utc(item["assistedIssuedAt"], "assistedIssuedAt")
        base_valid = _utc(item["baselineValidationEndAt"], "baselineValidationEndAt")
        assist_valid = _utc(item["assistedValidationEndAt"], "assistedValidationEndAt")
        settled = _utc(item["settledAt"], "settledAt")
        if not (base_valid < observed and assist_valid < observed and
                observed <= base_at < settled and
                observed <= assist_at < settled <= current):
            raise AuditUnavailable("Future leakage or unsettled forward evidence")
        baseline = _probability(item["baselineProbability"], "baselineProbability")
        assisted = _probability(item["assistedProbability"], "assistedProbability")
        outcome = Decimal(item["verifiedOutcome"])
        scores_baseline.append((baseline - outcome) ** 2)
        scores_assisted.append((assisted - outcome) ** 2)
        costs += _counter(item["aiActualCostMicroUsd"], "aiActualCostMicroUsd")
        dates.add(observed.date().isoformat())

    n = len(records)
    base = sum(scores_baseline, Decimal(0)) / n
    assist = sum(scores_assisted, Decimal(0)) / n
    difference = base - assist
    enough = n >= MIN_EVENTS_FOR_DESCRIPTIVE_REVIEW and (
        len(dates) >= MIN_DISTINCT_DAYS)
    return {
        "status": ("descriptive_pairing_available" if enough else
                   "insufficient_forward_sample"),
        "assetClass": class_name,
        "outcomeDefinition": definition,
        "providerSource": source,
        "matchedForwardEvents": n,
        "distinctObservationDays": len(dates),
        "baselineMeanBrier": str(base),
        "assistedMeanBrier": str(assist),
        "descriptiveBrierImprovement": str(difference),
        "assistedCalibrationImprovedDescriptively": difference > 0,
        "measuredAiCostMicroUsd": costs,
        "measuredAiCostUsd": str(Decimal(costs) / 1000000),
        "baselinePaidAiCostMicroUsd": 0,
        "evidenceOfProfitableTrading": False,
        "causalValueOfAiEstablished": False,
        "riskAdjustedAfterTradeCostAlphaEstablished": False,
        "eligibleForAutomatedTrading": False,
        "ordersPlaced": 0,
        "brokerRequestsMade": 0,
        "aiRequestsMade": 0,
        "limitations": [
            "Brier score measures binary forecast quality, not investment return.",
            "Synthetic or self-declared source verification does not establish real data quality.",
            "Matched forecasts and independently settled outcomes need external auditing.",
            "Multiple correlated events, regime changes and selection bias can invalidate comparisons.",
            "Provider spending is not a direct return-on-investment calculation.",
            "Actual net return, drawdown, fillability, and risk remain unverified.",
        ],
    }
