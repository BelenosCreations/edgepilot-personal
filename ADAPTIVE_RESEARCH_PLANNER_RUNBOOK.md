# EdgePilot v0.2.47 — Offline adaptive market-research planning

## What this achieves without market data or AI fees

An internal provider-neutral policy engine now computes a **proposal** for
how a future verified worker could sample research data efficiently. It is
not a schedule, active service, market-data acquisition, API entitlement
check, subscription or order system. It accepts synthetic trusted inputs
and makes **zero provider, brokerage, OpenAI or bank requests**.

The proposal honors bounded requests and individual or centrally licensed
quotas; it refuses stale or absent quota observations (older than 5
minutes), insufficient analysis/coverage rights, unknown market sessions,
future/still-fresh observations and provider backoffs. It uses strict
asset-class staleness defaults already established in
`research_intelligence.py`. Stock/ETF require an externally verified
open session; crypto needs separately verified continuous entitlement;
prediction contracts need verified open/settlement status and sufficient
time until expiry. It never infers coverage from the name of an asset.

A trusted adapter may propose a single centrally fetched feature for
several users **only** if central fetch, analysis, caching,
redistribution and coverage rights are independently verified. Otherwise
the planner creates member-isolated tasks solely if that individual has
verified per-member fetch authorization and remaining quota. It
round-robins per-member proposals to prevent the first member from
monopolizing a limited cycle. The planner does not silently fall back
to another user's Public credential or consume any user's tokens.
All member references in its return value are INTERNAL and must not
be exposed to a different user or to a public API route.

The proposal is constrained by explicit request/cycle bounds and actual
verified quotas, not guessed Starter-plan limits or assumed free access.
If provider permissions, quotas or market status cannot be verified,
**no fetch is proposed**. This deliberately favors missed opportunities
over unlicensed requests, privacy leakage or hidden charges.

## Operations, tests and limits

From `backend/`:

    python -m unittest tests.test_adaptive_research_planner_v0247 -v

Tests use synthetic ten-member requests, one licensed shared sample,
per-member nonredistributable quota paths, bounded cycles, fairness,
stale or missing quota assertions, provider backoff, unknown sessions,
crypto and 15-minute prediction expiry gating, unverified entitlements,
out-of-order/future data and unexpected/private input fields.

**Not delivered by this milestone:** provider-authoritative quotas or
contracts, verified data-market entitlements, market-hours calendars,
running scans, user subscriptions, price-feed acquisition, prediction
markets execution, AI billing, real performance claims, service load
measurements or physical two-device acceptance. No production flags,
Android APK, Render settings, paid services or bank/broker accounts
are changed. Deployment is not implied by merging tests.

Future trusted worker integration must document separately:
which central and member-specific credentials are authorized, how
provider quotas are measured, how data licensing changes invalidate
cached derived research, per-provider rate limits, distributed leases,
user privacy, accounts/entitlements, operational monitoring, session
calendars and permission to share licensed data.

Read `AI_ANALYSIS_COST_STRATEGY.md`, `SHARED_RESEARCH_CACHE_RUNBOOK.md`
and `MULTIUSER_PLATFORM_ACCEPTANCE.md` before turning these
offline proposals into any live data-acquisition behavior.
