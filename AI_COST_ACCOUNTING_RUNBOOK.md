# EdgePilot v0.2.44 — Owner optional AI cost accounting preflight

## Scope

This milestone replaces legacy ai_analysis.py's fixed $0.20-per-request
reservation with a verified-price, model-aware, precise *local* budget
ledger. It preserves the existing legacy owner app, private Render service,
original default-off AI opt-in, Public brokerage credentials, and all
disabled order/transfer controls. It does not enable AI automatically.

Supported **Standard, short-context text-only** OpenAI models and verified
input/output API rates (USD per 1,000,000 tokens) as checked 2026-11-10:
- gpt-6-luna: $0.10 input, $0.50 output.
- gpt-6-sol: $2.00 input, $10.00 output.

Official current source: https://developers.openai.com/api/docs/pricing
Prices may change, vary by region/service tier/context window and incur
additional charges; source rates above are a dated snapshot and must not be
presented as provider billing guarantees. The allowlist is fail-closed and
expires December 10, 2026 until explicitly reviewed and updated.
No other model, cached-input discount, expensive service tier, tool call
or prompt length above 15,000 serialized UTF-8 bytes is permitted by this
owner-only research flow. Models not on the allowlist are rejected without
making an API request. The on-demand research endpoint defaults to the
low-cost allowed model when no explicit owner server model is configured.

## Preflight, ledger and reconciliation

Each optional request passes a serialized-input upper token bound
(UTF-8 byte size plus 1,024 overhead tokens) and a 500-token output cap
into a price calculator. Estimated maximum text-token charges are rounded
*up* to integer micro-US dollars ($1 = 1,000,000 microUSD).
The SQLite ledger uses BEGIN IMMEDIATE to serialize concurrent reservation
attempts against the owner-selected monthly local budget. Older ai_runs
records are retained and counted at their original conservative reserved
amount rather than silently disappearing during migration. Month boundaries
are UTC. Denials store only a reason and model label, not user data.

When OpenAI returns a successful text answer **with documented input/output
token usage**, the ledger records actual token counts and a cost estimate
at the request model's reviewed rate, releasing unused local reservation.
Cached-input price reductions are deliberately not assumed. Unknown/missing
provider usage, network timeout, HTTP rejection or text failure leaves
the full initial reservation in an uncertain state until independently
reconciled; no automatic retries or assumed refunds occur. Double finish
is refused. Estimated token charges are NOT actual invoice records;
provider bills can differ.

The dashboard shows local budget, amount counted including pending and
uncertain holds, model-priced token cost estimate from completed requests,
remaining local budget, blocked request count/reason, reviewed rate date
and review expiry. Six decimal places preserve sub-cent visibility.
A $0 AI budget remains a valid non-AI choice. Legacy owner AI analysis
still requires the existing owner sign-in and explicit optional AI setting,
and the snapshot-sharing route independently requires user consent.
There are NO new AI requests, background scheduling or saved phone API keys.

## How to verify

From backend/ after installing requirements.txt:

    python -m unittest tests.test_ai_analysis tests.test_ai_precise_cost_v0244 -v

The standard GitHub CI runs all other backend/Flask tests, JavaScript
syntax checks and existing safety tests. Important negative cases:
model not on rate list, expired pricing, missing opt-in/key, insufficient
budget, 16 simultaneous reservations with only three allowed, rate changes
not repricing historical ledger entries, UTC month rollover, duplicated
finalization, missing usage, provider timeouts/rejections, and preserving
existing fixed-$0.20 historical rows.

## Limits and next development

This is a LOCAL owner application budget circuit breaker, not a provider-
guaranteed hard cap or an actual billing API connection. Charge finality,
taxes, cache adjustments, tier multipliers, atypical usage, billing exports
and provider organization-level spending controls are separate.
No ChatGPT consumer subscription includes automatic API credits.

Next implement member-owned BYOK encryption and **separate per-user**
allowances behind independent feature flags (without reusing the
owner's key). Then provider-neutral managed credits and subscription
entitlement *interfaces* only; actual customer charging/distribution
requires separate authorization. Continue the separate two-device/
two-independent-Public-account acceptance. No live orders or transfers.
