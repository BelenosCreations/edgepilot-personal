# EdgePilot v0.2.48 — Paired forward-research and AI cost audit

## Why this milestone exists

The approved AI strategy demands evidence that optional paid AI improves
research enough to merit incremental expense. An LLM explanation, model
confidence, attractive backtest or lower latency **is not evidence of
investment profits**. This offline evaluator tests one narrow component:
the descriptive Brier score of **paired** pre-settlement, independently
validated binary forecasts for exactly the same independently verified
settlements, along with their *measured attributable* optional AI costs.

The evaluator in `backend/engine/paired_research_audit.py` is pure
Python and accepts no user account, brokerage credential, portfolio,
holdings, payment, order, API key, network response or unrecognized input
field. It cannot call a provider, spend tokens, buy/sell or start a job.

The source adapter, not this evaluator, must verify outcome provenance,
issue timestamps, independent chronological validation and real token
cost attribution before supplying any record. Synthetic test fixtures
do **not** establish these real-world assertions.

## Fail-closed evidence contract

A record is eligible only if:

- It declares a consistent asset class, outcome definition and source
  for the whole evaluation cohort. Event IDs cannot repeat.
- The baseline and optional-AI-assisted probability were both
  issued after the observation but before the independently verified
  settlement. Independent validation completed *before* the observation.
- Both forecasts have at least 30 held-out calibration cases with a
  chronological validation method; AI-written prose does not qualify
  as probability verification.
- The verified outcome is binary 0/1 and the settlement is already
  observed by the evaluation cutoff.
- Attributable AI spend in microUSD is an actual measured nonnegative
  amount, not an estimated invoice, omitted usage or rounded guess.

For a descriptive status rather than insufficient evidence, require at
least 30 matched forward observations spread over at least seven
UTC observation days. **Even then**, the result is only a descriptive
difference in Brier-score forecast quality. There is no causal
AI-outperformance claim, after-fee trade profitability, executable edge,
risk-adjusted alpha or live execution permission. Correlated event
outcomes, cherry-picked models, training leakage, poor provider
settlement, regime change and sunk data costs remain potential problems.
Prespecified protocol, separate forward studies and capital-risk
modeling are still required.

## Test and operational status

From `backend/`:

    python -m unittest tests.test_paired_research_audit_v0248 -v

Tests use 40 synthetic timestamped matched events, exact cost accounting,
model degradation, small samples, future validation leakage, unknown
cost, unverified outcome, private fields, mixed categories and repeated
event IDs. No real prices or user accounts are accessed.

No HTTP route, tenant activation, worker connection, scheduling, AI
provider call, paid request, actual model calibration, brokerage order,
bank transfer, API key rotation, commercial sale or production
configuration is part of this milestone. Merging the code is not proof
that a trading strategy works. The standing two-device/two-separate-
Public-account acceptance remains open.
