"""Dormant, offline, quota-aware research sampling proposal for trusted workers.

No actual scheduling, provider calls, market subscriptions, orders or AI.
Quota, permission and account-entitlement assertions MUST come from trusted,
independent provider/tenant adapters. Never use user-supplied quota claims
or share member references in HTTP responses. All unknown state fails closed.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Mapping
import uuid

from . import research_intelligence as research

MAX_DEMANDS = 1000
MAX_CYCLE_REQUESTS = 250


class PlanningUnavailable(ValueError):
    """Unknown market data permission, stale quota or untrusted input."""


def _now(value):
    current = (datetime.now(timezone.utc) if value is None else
               research.utc_time(value, "now") if isinstance(value, str) else value)
    if (not isinstance(current, datetime) or current.tzinfo is None or
            current.utcoffset().total_seconds() != 0):
        raise PlanningUnavailable("Explicit UTC current time required")
    return current


def _stamp(value, label):
    if value is None:
        return None
    try:
        return research.utc_time(value, label)
    except research.ResearchUnavailable:
        raise PlanningUnavailable("Verified UTC timestamp required") from None


def _int(value, label, maximum=100000):
    if type(value) is not int or not 0 <= value <= maximum:
        raise PlanningUnavailable(label + " must be a bounded nonnegative integer")
    return value


def _member_id(value):
    if not isinstance(value, str):
        raise PlanningUnavailable("Trusted member reference required")
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError("Noncanonical UUID")
    except ValueError:
        raise PlanningUnavailable("Trusted member reference required") from None
    return value


def _policy(policy, current):
    if not isinstance(policy, Mapping) or set(policy) != {
            "rights", "centralFetchVerified", "perMemberFetchVerified",
            "centralRequestsRemaining", "memberRequestsRemaining",
            "cycleRequestLimit", "quotaObservedAt", "backoffUntil"}:
        raise PlanningUnavailable("Explicit provider policy and quotas required")
    try:
        rights = research.ProviderRights.from_mapping(policy["rights"])
    except research.ResearchUnavailable:
        raise PlanningUnavailable("Provider analysis rights not verified") from None
    if (type(policy["centralFetchVerified"]) is not bool or
            type(policy["perMemberFetchVerified"]) is not bool):
        raise PlanningUnavailable("Provider fetch permissions must be explicit")
    central = _int(policy["centralRequestsRemaining"], "Central quota")
    limit = _int(policy["cycleRequestLimit"], "Cycle limit", MAX_CYCLE_REQUESTS)
    member = policy["memberRequestsRemaining"]
    if not isinstance(member, Mapping) or len(member) > MAX_DEMANDS:
        raise PlanningUnavailable("Trusted per-member quota map required")
    per_member = {_member_id(k): _int(v, "Member quota") for k, v in member.items()}
    observed = _stamp(policy["quotaObservedAt"], "quotaObservedAt")
    if observed is None or not 0 <= (current - observed).total_seconds() <= 300:
        raise PlanningUnavailable("Provider quota observation missing or stale")
    backoff = _stamp(policy["backoffUntil"], "backoffUntil")
    return rights, central, limit, per_member, backoff


def _validate_demands(demands, current, provider):
    if not isinstance(demands, list) or len(demands) > MAX_DEMANDS:
        raise PlanningUnavailable("Invalid bounded research demand batch")
    eligible = []
    reasons = Counter()
    seen = set()
    for demand in demands:
        if not isinstance(demand, Mapping) or set(demand) != {
                "memberRef", "provider", "assetClass", "symbol", "session",
                "entitlementVerified", "lastObservedAt", "expiresAt",
                "settlementVerified"}:
            raise PlanningUnavailable("Unrecognized or private demand fields")
        uid = _member_id(demand["memberRef"])
        try:
            source = research._text(demand["provider"], "provider")
            sym = research._text(demand["symbol"], "symbol", 96)
        except research.ResearchUnavailable:
            raise PlanningUnavailable("Invalid research provider or symbol") from None
        asset = demand["assetClass"]
        if type(asset) is not str or asset not in research.ASSET_CLASSES:
            raise PlanningUnavailable("Unsupported research asset class")
        if source != provider:
            raise PlanningUnavailable("Demand belongs to another provider")
        identifier = (uid, asset, sym)
        if identifier in seen:
            raise PlanningUnavailable("Duplicate member research demand")
        seen.add(identifier)
        if (type(demand["entitlementVerified"]) is not bool or
                type(demand["settlementVerified"]) is not bool):
            raise PlanningUnavailable("Individual coverage and settlement flags required")
        if not demand["entitlementVerified"]:
            reasons["unverified_entitlement"] += 1
            continue
        session = demand["session"]
        expected = "continuous" if asset == "crypto" else "open"
        if session != expected:
            reasons["market_unavailable"] += 1
            continue
        last = _stamp(demand["lastObservedAt"], "lastObservedAt")
        if last is not None:
            age = (current - last).total_seconds()
            if age < 0:
                raise PlanningUnavailable("Future market sample is invalid")
            if age < research.DEFAULT_STALENESS_SECONDS[asset]:
                reasons["recent_sample"] += 1
                continue
        expiry = _stamp(demand["expiresAt"], "expiresAt")
        if asset == "prediction":
            if (expiry is None or not demand["settlementVerified"] or
                    (expiry - current).total_seconds() < 60):
                reasons["settlement_or_expiry_unverified"] += 1
                continue
        elif expiry is not None or demand["settlementVerified"]:
            raise PlanningUnavailable("Unexpected settlement metadata")
        eligible.append((uid, asset, sym, last))
    return eligible, reasons


def propose_cycle(demands, *, policy, now):
    """Produce a pure read-only sampling plan, NEVER schedule/execute it.

    Internal return values include trusted member identifiers. They must never
    be returned directly to Android clients or other tenants. Central grouping
    is allowed only with verified central fetch AND analysis, cache,
    redistribution and covered-instrument rights. Otherwise per-member work
    needs independently verified per-member fetch authority and quota.
    """
    current = _now(now)
    rights, central_remaining, cycle_limit, member_quotas, backoff = _policy(
        policy, current)
    due, reasons = _validate_demands(demands, current, rights.provider)
    if backoff is not None and backoff > current:
        reasons["provider_backoff"] += len(due)
        due = []
    central_allowed = (policy["centralFetchVerified"] and
                       rights.allowed_analysis and rights.allowed_cache and
                       rights.allowed_redistribution and rights.verified_coverage)
    isolated_allowed = policy["perMemberFetchVerified"]
    # Prefer shared work when its legal rights and quota exist. Never silently
    # spend a different member's provider entitlement for a shared request.
    shared = defaultdict(list)
    isolated = []
    for uid, asset, sym, last in due:
        if central_allowed:
            shared[(asset, sym)].append(uid)
        elif isolated_allowed and uid in member_quotas:
            isolated.append((uid, asset, sym, last))
        else:
            reasons["fetch_authorization_unavailable"] += 1

    tasks = []
    slots = cycle_limit
    # One eligible licensed symbol requires one central fetch, no matter how
    # many members are subscribed to it. Stable order supports reproducibility.
    for (asset, sym), members in sorted(shared.items()):
        if slots <= 0 or central_remaining <= 0:
            reasons["central_quota_or_cycle_exhausted"] += len(members)
            continue
        tasks.append({"provider": rights.provider, "assetClass": asset,
                      "symbol": sym, "scope": "licensed-public-shared",
                      "internalMemberRefs": sorted(members),
                      "readOnly": True, "aiCalls": 0})
        central_remaining -= 1
        slots -= 1

    # For provider credentials which cannot be shared, allocate in rounds by
    # member rather than exhausting the first person's quota before the next.
    buckets = defaultdict(list)
    for uid, asset, sym, last in isolated:
        buckets[uid].append((asset, sym, last))
    for uid in buckets:
        buckets[uid].sort(key=lambda item: (
            item[2].timestamp() if item[2] is not None else -1,
            item[0], item[1]))
    while any(buckets.values()):
        progressed = False
        for uid in sorted(buckets):
            if not buckets[uid]:
                continue
            asset, sym, _ = buckets[uid].pop(0)
            if slots <= 0 or member_quotas.get(uid, 0) <= 0:
                reasons["member_quota_or_cycle_exhausted"] += 1
                continue
            tasks.append({"provider": rights.provider, "assetClass": asset,
                          "symbol": sym, "scope": "member-isolated",
                          "internalMemberRefs": [uid],
                          "readOnly": True, "aiCalls": 0})
            member_quotas[uid] -= 1
            slots -= 1
            progressed = True
        if not progressed:
            break
    return {
        "mode": "offline-proposal-only",
        "provider": rights.provider,
        "proposedTasks": tasks,
        "proposedProviderCalls": len(tasks),
        "skippedReasonCounts": dict(sorted(reasons.items())),
        "nonAI": True,
        "actualProviderCalls": 0,
        "accountCredentialsAccessed": False,
        "tradingAllowed": False,
        "bankTransfersAllowed": False,
        "userIdentityInformationInternalOnly": True,
        "quotaNotProviderEnforced": True,
    }
