# EdgePilot v0.2.46 — Licensed shared public-research feature cache

## Scope and safety

Adds a **dormant** reusable derived-market-feature cache in
`backend/engine/shared_research_cache.py`. There are no new HTTP routes,
workers, provider requests, key transfers, AI calls, trades or payment code.
Nothing is initialized on the existing Render service or owner Android app.
It is a research-only, internal-only building block for the approved
`AI_ANALYSIS_COST_STRATEGY.md` and future independently owned tenant accounts.

A trusted provider adapter must independently verify the rights to **analyze**,
**cache**, **redistribute** and use a specifically **covered instrument**, before
it calls `publish`. Boolean flags supplied by an untrusted phone or HTTP
caller are not legal/technical verification. This milestone proves application
policy enforcement with synthetic fixtures; it **does not** certify that
Public or any other provider grants these permissions.

`Observation.validate` rejects stale/future, crossed, closed, unsupported,
unverified or inconsistent market records. The cache accepts exactly the
required provider-neutral observation keys; user IDs, account IDs, holdings,
brokerage tokens and other personal fields are rejected. It saves only
one non-executable, zero-AI public feature per provider/asset/symbol:
quoted spread in basis points, with provenance and a short expiry.
A live quote, a fillable order-book price, a market-wide signal and a
profitability prediction are **not** established by this one feature.

The cache is bounded to 500 entries and expires entries based on their
asset-class staleness policy; older samples cannot overwrite newer samples.
A trusted internal invalidation method can purge a provider's entries
when permissions change. Every read requires *newly asserted* coverage,
analysis, cache and redistribution rights from a trusted adapter.
Existing entries do not by themselves prove currently valid rights.

## Per-account read boundary

For now, only **stock and ETF** watchlist previews have the required
account-specific authorization path. The tenant must present an active
independent EdgePilot identity session and matching CSRF. The account must
be linked to that user through a non-revoked Public connection; its own
watchlist must contain the symbol. The identity, account, watchlist and
inactive runtime state are checked together inside one SQLite
`BEGIN IMMEDIATE` transaction.

Two people can reuse the identical eligible, public, licensable feature;
they cannot read it under the other's account identity, and user-specific
settings, portfolio snapshots, keys, budgets and research never enter the
shared feature table. There is **no** personal risk ranking, paper portfolio
execution or account-specific alert in this release. Crypto and prediction
instruments cannot be assumed to have per-user entitlements based on a
Public stock account; corresponding account previews are refused.

Even for stock/ETF, this module is **not an HTTP authentication endpoint**.
Its internal methods must never be mounted on public routes or fed client
assertions of provider rights. Future use requires verified provider
adapters, grant revocation management, rate/entitlement controls and
multi-device acceptance. The locally counted feature says nothing about
license fees, trade eligibility or future returns.

## Test, negative paths and deployment state

From `backend/` with pinned dependencies installed, run:

    python -m unittest tests.test_shared_research_cache_v0246 -v

The test uses synthetic providers and credentials, denies all outbound
HTTP, and covers licensing combinations, forbidden personal fields,
stale/future/crossed/closed quotes, account watchlist and session
isolation, foreign account denial, provider invalidation, out-of-order
updates, short expiry, restricted asset classes and ten independently
authenticated members reading one licensed synthetic feature.

Release criteria: verify GitHub Actions on the exact head SHA and after
merge, keep README/CHANGELOG/DEVELOPMENT_CONTINUITY synchronized, do not
create or enable production feature flags, and retain the separate
two-physical-Android-device/two-real-independent-Public-account acceptance
gate. Live orders, transfers, actual AI billing and payment collection remain
disabled.
