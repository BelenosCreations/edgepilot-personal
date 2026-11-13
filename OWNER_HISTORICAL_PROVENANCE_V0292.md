# v0.2.92 — Dormant historical source provenance, no market-data storage

## Purpose
Public's official [Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2) documents `GET /userapigateway/historicdata/{type}/{symbol}/{period}`, with fields for open, close, high, low, volume and timestamp. The independent [Get quotes](https://public.com/api/docs/resources/market-data/get-quotes) endpoint documents the `marketdata` scope for real-time quotes. Neither endpoint's mere existence proves that a particular EdgePilot credential can retrieve data or that EdgePilot may store, re-share or use it as execution evidence. Public's [Individual API Program Agreement](https://public.com/disclosures/individual-api-program) includes personal-use restrictions, additional market-data terms, and a prohibition on distributing licensed data to third parties without prior written approval.

The new offline-only `backend/engine/owner_historical_bars.py` contract is purposely *not connected* to app.py, the identity routes, live Public API, legacy global history cache or the dormant paper ledger. It reads a caller-supplied in-memory payload and produces a validated, labeled representation or refuses it. It does not authorize provenance or data entitlements.

## Validation
- Require exact requested symbol and period from the supplied response and supported EQUITY/CRYPTO type.
- Require a nonempty, bounded, strictly chronological `regularMarket.bars` series with explicit timezones; reject future bars relative to an injected UTC receipt clock.
- Preserve source-provided nonzero positive price strings with up to 12 decimal places. Enforce low <= open/close <= high and high >= low using exact Decimal arithmetic.
- Require a nonnegative, bounded integral source volume and reject NaN, infinity, float coercion, leading zero ambiguities, future dates and malformed/unordered observations.
- Do not include the API's `leadingFill` synthetic history padding, infer missing market sessions, compute investment returns, fabricate price series or claim adjusted-price completeness.
- Output `providerRequestAuthenticated=false`, `accountScopeVerified=false`, `dataRightsVerified=false`, `cacheRightsVerified=false`, `redistributionAllowed=false`, `paperFillEligible=false`, `productionEligible=false` and `performanceVerified=false`. The provider label explicitly says the payload is unverified.

## Before any owner deployment
The future adapter must authenticate the independent owner, enforce its selected user-owned Public account, document the source/period precisely, verify provider-marketdata access **with a real manual read**, and ensure provider retention and derived-use rights before any saved history, chart, paper fill or automated research. A successful synthetic validator cannot establish these facts. Additional real identities remain deferred, with existing multi-user architecture preserved. All production paper fills, real brokerage orders, autonomous execution and bank transfers stay disabled.

## Tests
`python -m unittest tests.test_owner_historical_bars_v0292 -v` uses synthetic data only; the standard GitHub PR and merged-main CI run all tests. No fees, new hosted resources, live source requests or disk writes are introduced.
