# EdgePilot — Approved AI Intelligence, Cost, and Scale Strategy
**Approved by owner:** 2026-11-10  
**Status:** Approved product/development requirements; implementation is not implied to be complete.  
**Repository:** BelenosCreations/edgepilot-personal

## Purpose and governing principles

Build **one modular EdgePilot research/intelligence platform** that works for (1) a single private owner, (2) up to ten private friends with independent Public accounts and AI budgets, and (3) an eventual Google Play commercial product. Avoid redesigning the analysis core when user counts change. This is an **approved development direction** to incorporate incrementally into the current multi-user workstream; it is not authorization to activate real orders, automatic live trading, deposits, withdrawals, or commercial services.

Optimize for **credible risk-adjusted, after-cost expected value**, signal calibration, measured usefulness, and capital protection — **not guaranteed profit, trade count, excessive model calls, or backtest overfitting**. Every recommendation must acknowledge uncertainty; a paid tier must not imply higher guaranteed returns. Trades must continue to respect protected balances, loss stops, ownership and execution permissions.

Preserve existing work, security boundaries, stable installed Android owner application, disabled-by-default tenant gates, brokerage credentials, and development continuity. Update README.md (product capabilities, not a changelog) and CHANGELOG.md at each implementation milestone; document tests and limitations. Follow DEVELOPMENT_CONTINUITY.md and existing acceptance requirements. The **current multi-user acceptance milestone** remains two physical devices, independent EdgePilot identities, and independently verified Public accounts, tested end to end. Cost/intelligence architecture may be developed in parallel, but must not delay or falsely claim that milestone complete.

## Three-layer architecture — free-first

### Layer 1: Efficient, non-AI market intelligence
- Retrieve provider-authorized market data for supported stocks/ETFs, eligible prediction-event contracts, and crypto **only when corresponding coverage is verified**.
- Compute local/server-side trends, technical features, momentum/mean-reversion indicators, realized volatility, spreads, volume/liquidity, time-to-expiry, market/session and event/settlement status, and preliminary screening.
- Scan an appropriately bounded permitted universe. Use adaptive sampling based on market activity, data staleness, API limits, market hours, and account entitlements rather than pretending to monitor everything continuously.
- Do **not** equate an API quote with an executable price. Reject missing/stale/inconsistent market data.
- Separate market-data acquisition rights from redistribution/caching rights; validate Public and secondary provider terms before sharing or publishing data.

### Layer 2: Statistical and validated predictive analysis
- Offer baseline rules, historical studies, fee/slippage-sensitive scenario calculations, chronological train/held-out validation, walk-forward analysis, calibration checks, risk metrics and drawdown evaluation.
- Compare technical/statistical models and locally executed ML if it can demonstrate value. Do not treat a classifier confidence score, a hypothetical backtest, or LLM prose as a verified probability or profitable signal.
- Rank opportunities by conservative **net expected value after commissions, spreads, slippage, exchange/provider charges and settlement rules**, subject to uncertainty and risk limits.
- Avoid lookahead bias, data leakage, survivorship bias and overfitting. Add paper/observe forward testing with timestamped inputs and later realized market outcomes.
- A user who elects **$0 paid AI** still receives a useful, properly risk-controlled intelligence experience.

### Layer 3: Optional, budget-limited advanced AI
- AI contributes qualitative explanations, research comparison, news/event context when licensing and provenance permit, alternative scenarios and identification of missing evidence.
- AI cannot submit or authorize orders, access bank transfers, disable controls, or overwrite verified market facts/probabilities.
- Default to low-cost models, escalating to more expensive reasoning **only when expected incremental research value warrants it**, and only if the user's configuration and budget permit it.
- Prefer selective/event-driven AI after free/statistical screening, not an LLM request for every quote or 15-minute interval.
- No silent third-party transmission of private holdings, user identity, keys or personal portfolio data. Require appropriate consent and scoping; retain redaction and auditability.

## Use case 1 — single private owner

**Objective:** strongest empirically useful analysis at lowest possible cost.
- Offer choices: **$0 AI**, **$2–$5/month**, **$10–$20/month**, and **custom** budget, alongside an analysis-depth/preference control. These are suggested user choices, not fixed entitlement claims.
- Keep regular market monitoring and non-AI research functional at $0 AI spend; paid AI is an optional increment rather than a dependency.
- Prefer the existing Public data integration where access and entitlements permit; independently verify any free supplemental data, plan quotas, licensing, freshness, and commercial restrictions. No assumption of free, unrestricted real-time crypto/market depth.
- Add a budget dashboard: provider/model, requests, estimated tokens/cost, actual usage when available, remaining app budget, blocked requests and reason, forecast, and attributable infrastructure usage.
- Existing code has AI default-off and a default $2 monthly budget with an overly conservative fixed **$0.20 reservation per request** (backend/engine/ai_analysis.py). Replace *after tests* with model-aware, max-token-informed preflight reservations, provider token usage reconciliation, failure/timeout handling, accounting in integer micro-units or otherwise precise units, and explicit model fallbacks. An in-app request budget **is not a provider-side guaranteed billing cap**. Never promise a hard financial cap without supported provider enforcement.
- Actual AI cost estimates must be pulled from current provider pricing and measured token counts. Illustrative example costs from earlier discussion are not authoritative price guarantees.

## Use case 2 — private shared platform, up to 10 friends

**Objective:** shared fixed overhead, per-user isolation and per-user-funded AI.
- One shared backend may compute and cache *permitted public/non-sensitive signals* once, then apply **each member's own** Public connection, allowable instruments, account balance, risk profile, watchlist, preferences and permissions separately.
- Tenant ownership boundaries cover API keys, budgets, model settings, holdings, portfolios, historical records, strategy outputs, cached personally tailored analysis, job queues, logs, broker rate quota attribution, notifications and backups.
- Provide three **optional** AI billing modes:
  1. **No paid AI** — non-AI signals/analysis only.
  2. **Bring your own API key (BYOK)** — user's own OpenAI/provider account is billed directly; credentials are securely encrypted and isolated in the backend, not shipped in Android, browser storage or telemetry.
  3. **EdgePilot-managed credits/allowance** — reserve architectural support; user-funded subscription/prepaid/custom credits only after owner approves enabling billing and policies are verified.
- Every user can select budget and analysis depth independent of the owner and other users. A friend's AI use must not be charged against the owner's OpenAI key unless a **separately consented owner-funded allocation** is configured.
- BYOK may require users to separately establish paid API-provider accounts; ChatGPT consumer subscriptions do not themselves supply API billing credits.
- Use tenant-safe provider request queues, rate limits, quotas, circuit breakers, provider outage fallbacks, detailed per-user cost attribution, and consistent visibility of actual vs estimated spending.
- Shared data reuse is conditional on relevant license and confidentiality requirements. Reuse only valid timestamped data; never leak holdings, risk settings or user-generated research across tenants.
- Load-test ten concurrent users; monitor worker CPU/memory, DB growth, event-loop/queue pressure, disk, bandwidth, external API throttling and backups. Hosting upgrade costs must be measured, not promised to stay at Starter pricing.

## Use case 3 — eventual Google Play commercial app

**Objective:** affordable free-to-start research with commercially sustainable optional enhancements.
- Keep the same safe free core; suggested tier concepts, **not approved final prices**:
  - Free: account link, portfolio visibility, limited watchlists/market screening, paper trading.
  - Plus: greater scan/research capacity, alerts, modest AI allowance.
  - Pro: larger capacity, richer research, deeper validation and increased AI allowance.
  - Custom/Power: user-configurable research budget and/or BYOK where compliant.
- Proposed exploratory prices: Plus **$4.99–$7.99/month**, Pro **$12.99–$24.99/month**. Final pricing depends on actual unit economics, provider data licenses, service fees, churn/support costs, regulation and market testing.
- Separate **subscription feature entitlements**, **AI spend allowance**, **user-owned provider billing**, **market-data costs**, **brokerage transaction costs**, and **hosting costs** in code and statements.
- Architect a provider-independent billing/entitlements abstraction now; do not silently turn on payments or subscriptions.
- Before Play distribution, check current Play Billing and financial-features policies, requirements for financial apps and account deletion, investment adviser/brokerage regulatory issues, data licensing and redistribution, commercial use of Public APIs, privacy/security obligations, incident response and support.
- **Important distribution blocker:** Google Play's binary-options policy creates material risk for the 15-minute YES/NO prediction-market trading feature. Do not assume it can be offered in a Play listing; obtain a policy/legal determination and plan for store-specific feature gating or a research-only scope if needed.
- Model efficiency: permitted centralized research computations, cache controls, batching, queue prioritization, user entitlements, cost and quality telemetry, and adaptive scan rate.

## Profitability and guardrail evaluation

Measure and compare:
- Forward paper-trading performance after realistic fees, spread, slippage and failed-fill assumptions; drawdown, volatility, hit rate, exposure-adjusted returns and data availability.
- Calibration of predicted probabilities and how much signals improve out-of-sample over simple baselines.
- Incremental value of paid AI vs non-AI baseline (A/B or controlled shadow assessment), per-request token cost and attributable net improvement where evidence supports it.
- Differences by equity, ETF, crypto and 15-minute markets. Prediction event selection must include contract metadata, settlement conditions, permitted trading state, book depth, expiration, fees, and conservative break-even math.
- Loss avoidance and reliability: missing data means no qualifying opportunity; protect allocated cash; no guaranteed returns or claims of automatic profitability.

## Implementation order / logical milestones

1. **Do not derail current gated tenant/2-device acceptance path.** Preserve disabled real-order, live-autonomy and transfer boundaries.
2. Add provider-neutral data + research-layer interfaces and stable signal schemas with provenance/timestamps and cost assumptions.
3. Enhance zero-cost statistical analysis, screening, backtesting and paper-forward measurement. Audit data licensing and rate limits.
4. Correct existing optional AI accounting (fixed $0.20 reservations), implement model routing, consumption visibility, conservative but proportionate preflight, fail-closed provider spending controls. Add tests for rollover, concurrency, timeouts, retries, model pricing changes, missing actual usage, and unauthorized requests.
5. Add tenant-scoped BYOK vault, per-user AI budgets, isolation and budget-invoice tests. Keep all new provider integrations default-off and separate from brokerage authorization.
6. Evaluate shared permitted research cache, monitoring economies and ten-user load testing; capacity upgrade only with measurable need.
7. Design future tier/entitlement/payment abstraction without prematurely enabling payments or commercial service. Separately review commercial policy/legal/data-provider constraints.

## Development acceptance / documentation rules

- For each milestone: test negative paths and isolation, verify CI against exact commit, log test status, document cost assumptions and limitations, update README.md and CHANGELOG.md; keep detailed revision history in changelog rather than turning README into a changelog.
- Any new model/market-data provider is optional until configured and tested; do not invent coverage or authorization.
- No billing or key spending without explicit, understandable per-user opt-in. Do not log secrets, transmit private account information without consent, or silently charge owner for other users.
- No guaranteed accuracy/profitability, no manufactured win rates; use reproducible research evidence and measured billing.
- **Approved now:** engineering architecture and incremental development of the free-first three-layer analysis, individual budgets, tenant isolation, BYOK readiness, usage accounting, and commercial-readiness abstractions.
- **Not approved by implication:** activating live orders/autonomous trading, money movement, enabling public/paid distribution, charging customers, signing contracts, purchasing new third-party services, or introducing a new major unreviewed feature.

## Handoff to active development conversation

Read this file together with DEVELOPMENT_CONTINUITY.md, VERSION, README.md, CHANGELOG.md and latest main/PR/CI status. Treat it as **owner-approved product requirements**, incorporate opportunistically in the continuing EdgePilot milestones and keep already-active development work intact. Commit tested implementation in normal focused milestones, preserving README/changelog, and stop only for major out-of-scope decisions or necessary credentials. Do not claim any of these recommended advanced-analysis/billing features are already deployed merely because this requirements file exists.
