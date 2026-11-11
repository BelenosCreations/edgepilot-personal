# EdgePilot v0.2.43 — Free-first research-contract acceptance

This milestone implements the first piece of the owner-approved
AI_ANALYSIS_COST_STRATEGY.md three-layer research strategy. It is a pure
Python provider-neutral module with no user, network, key, scheduler, account,
broker execution, market-data API or LLM dependencies.

## Contract

backend/engine/research_intelligence.py requires market asset category,
instrument identifier, provider rights assertions (analysis, cache, resale/
redistribution and covered instrument), a fresh UTC observation timestamp,
receipt timestamp, bid, ask, last, volume and an open market state.
Missing or invalid coverage, analysis rights or snapshots fail closed.
Analysis permission does NOT imply permitted caching or redistribution.
The provider-specific integration must verify the self-asserted rights:
this module alone cannot establish contracts/terms.

Supported category names are stock, etf, crypto and prediction, but a
category label is NOT evidence that any provider offers it. Observations
with stale/future-dated timestamps, crossed bid/ask or missing prices are
rejected. The output explicitly marks a midpoint as a non-executable
reference and all outputs as read-only research.

Prediction YES scenarios require explicit valid contract expiry, settlement
details, sufficient top-of-book depth, quoted ask, commission, exchange fee,
settlement fee and slippage, plus externally supplied evidence claiming
a chronological held-out probability with at least 30 observations.
The backend does NOT independently certify that claim; true calibration and
risk-quality acceptance requires forward outcomes and separate independent
tests. The computed cost-adjusted expectation is a hypothetical scenario,
never a recommendation or an executable order.

The historical momentum/dispersion baseline uses strictly increasing UTC
timestamps, a caller-supplied UTC cutoff, bounded input sizes and no
future bars. It costs zero LLM/API model calls, conveys no calibrated win
probability and does not place a trade. Observations cannot be used to
claim guaranteed continuous monitoring of crypto or 15-minute contracts.

## Testing

Run (from backend after installing requirements.txt):

    python -m unittest tests.test_free_first_research_v0243 -v

The standard GitHub workflow discovers these tests. Negative paths include
no source rights/coverage, missing quote fields, impossible books, stale
receipt or observation timestamps, unknown/expired predictions, insufficient
book depth, unapproved prediction probabilities and future/duplicated bars.

## Acceptance boundary

This is not wired into live routes, broker adapters, polling intervals or
automated execution. It introduces no cost to the owner and preserves
the original signed Android APK, Render settings, Public credentials,
default-off multiuser identity gates, and all bank/order restrictions.

The next steps are explicit signal provenance from licensed adapters, test-
quality forward paper outcome measurement, upgrading existing optional AI
budget controls away from the fixed $0.20 reserve, then isolated per-user
budget and BYOK architecture. Do not claim actual provider licensing,
forward trading returns or a validated ability to run all markets for free.
