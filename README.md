# EdgePilot v0.19.10 — Private deployment and connection verification

**What this release does:** Adds authenticated, read-only Public API diagnostics on the Overview screen, a minimal `/healthz` probe for managed hosting, and a mobile-friendly self-origin connection default. It retains all historical features from v0.19.9. API keys stay on your hosting backend. Real orders remain impossible from this code path.

**What this release does not do:** It does not deploy a service, connect your Public account, guarantee a verified trading ledger, support fully automatic trading, or provide audited production security. The app requires HTTPS hosting, secrets, persistent storage, and account verification before live use.

**Phone-only deployment:** See `PHONE_DEPLOYMENT.md`. This app is packaged to be placed in a **private GitHub repository**, then deployed with Render Blueprint. Never upload a `.env` file or any real key to GitHub. A browser upload of a ZIP alone is not a deployment; the files must be committed as a repository tree. If you cannot upload an extracted folder from Android, use a GitHub-capable mobile Git client or connect a supported repository integration.

# EdgePilot v0.19.9 — Personal Edition (single user)

## Design decision

**One installation = one user.** This is being developed for the owner's personal use with their independently controlled Public account. There is no multi-user registration, family administrator, hosted user directory, shared database, credential sharing, or commercial distribution workflow. The software contains configurable fields rather than hard-coded personal credentials, so a different independent user could theoretically deploy their own instance, **subject to Public's API terms**. This design does not grant permission to distribute the software.

## Configurable personal settings

- Profile name: editable in Settings.
- Backend URL and app access token: enterable on the connection screen, with change-connection control. These identify and authenticate the individual installation (this is a single token, **not** full multi-user login management).
- Public API secret: settable/changeable in the personal host's encrypted `PUBLIC_API_SECRET` environment setting; **not entered in the frontend** to avoid storing a trading credential on the phone. After rotation restart/redeploy backend.
- Public trading account: selectable from the personally authenticated broker accounts list.
- Public or independent balance, independent balance value, protected percentage, spending cap, per-trade cap, daily loss parameter, pre-existing holding permission, autonomous preference: individually configurable.

## Current implementation limitations

This is an **unhosted source-code PWA**, not an APK or a ready-to-install URL. Live stock and prediction-market order execution, autonomous trading, realized-P&L tracking, manual broker sale detection/prompts, and independent-balance increases from gains **are not implemented**. The app intentionally disables live orders. The daily-loss field is a preference, not a verified real-time broker-enforced loss control. Bank deposits and withdrawals are not implemented and are never automated.

For a phone-only setup, deploy the application on a private HTTPS host with persistent storage. Set `PUBLIC_API_SECRET` and a long random `EDGE_APP_TOKEN` as **secret environment variables**. Do not commit real keys to source, send them in chats, or include them in screenshots. Use Chrome's Add to Home Screen after you have a valid HTTPS URL. The included `render.yaml` and Dockerfile are deployment starting points, not a completed hosted installation.

Read SECURITY.md before hosting. The access token mechanism is prototype-level security; use HTTPS and a strong access gateway before exposing a live broker-backed instance. If you shared a Public key in a screenshot, revoke and rotate it.

## Public API terms

Public's Individual API agreement is for personal use and restricts third-party redistribution. This build is scoped to the owner's own account and is not intended for distribution. No code-based configurability changes the legal permissions under Public's agreement. Verify applicable terms before sharing the app.

Official docs: https://public.com/api/docs/quickstart

## v0.7: Adaptive micro-trading economics (read-only)

Micro-trading is **not** a fixed profit-percentage strategy. The app now has distinct stock/ETF and prediction contract minimum expected-edge thresholds, a minimum modeled net winning gain, and a daily trade limit preference. A scenario evaluator uses explicit winning/losing exit prices, estimated probability, trade quantity, two-way fees, and additional spread/slippage costs. It reports net winning and losing outcomes and expected net value; it **never** claims a trade is profitable merely because the exit is above the entry.

These are configurable screening thresholds and illustrations, **not a market forecasting engine or trading system**. No broker orders are placed. To trade live, broker fill reconciliation, verified data quality, position attribution, cash settlement rules, and order-level server-side limits must be implemented and independently tested. The default illustrative edge thresholds are *not* empirically validated.


## v0.8: Production-oriented accounting foundation

- Adds `backend/engine/ledger.py`: append-only broker-fill history keyed by execution ID, average-cost attributed positions, realized P&L, and manual-sale repurchase decisions.
- Adds `backend/engine/risk.py`: deterministic fail-closed risk calculator which requires fresh reconciled broker balances, counts reserved exposures, honors the selected balance source, and preserves every absolute cap.
- Adds authenticated read-only `/api/ledger` endpoint. At present it returns no imported broker fills. **The engine does not claim live portfolio or verified P&L** until a broker-execution adapter is implemented and tested.
- Adds tests for duplicate fill processing, sell proceeds vs profits, manual sells, conflicting fills and allocation/risk boundaries.
- Order execution is still disabled. No autoscheduler, bank transfers, or autonomous buying/selling have been added.

Run the unit tests (Python standard library): `cd backend && python -m unittest discover -s tests -v`. The app uses SQLite for a single private deployment; production needs encrypted persistent disk and tested backups. No API secret is bundled.

## v0.19 — Personal dashboard and account history
- Portfolio-style dashboard with 1D, 1W, 1M, 3M, 1Y, ALL account-value trend chart, current holdings, and recorded ledger P&L.
- Appearance settings: System, Light, Dark (saved locally on the device; no trading secrets stored).
- Real account value snapshots saved to SQLite at most once per minute per selected account, only on successful Public dashboard retrieval. **No fabricated back-history.**
- Changes in account value **are not investment profit**, as transfers and outside trades also change them; ledger realized P&L is only from reconciled fills.
- Live order execution and autonomous execution remain disabled.

## v0.19.1 — Read-only Public synchronization

Adds on-demand Public portfolio + fully paginated transaction capture with atomic persistence, broker ID deduplication, changed-transaction alerts, position-decrease review alerts, and explicit acknowledgement. Source: Public API v2 portfolio + account history.

**Crucially:** Public history rows do not include order IDs and may lag fills. Historical trades are not automatically attributed to EdgePilot or posted to the confirmed-fill ledger, and alerts are not proof of manual sales. Acknowledging an alert does not permit repurchasing. The independent balance remains manually assigned until verified attribution and fee-aware reconciliation can be established. No real orders, autonomous worker, or banking actions.

From the home screen, use **Sync now** after the backend has a valid Public secret and an account selected. This fetches the broker history with pagination and saves data only once all pages succeed. Requires secure persistent storage for SQLite. Test commands: `cd backend && python -m unittest discover -s tests -v`.


## v0.19.2 — Order and execution evidence (READ ONLY)

This patch adds `backend/engine/order_audit.py` and authenticated routes:
- `POST /api/orders/audit/run` — retrieve order **details** by order ID already seen in the Public portfolio or local database; commit validated broker order/trade evidence atomically.
- `GET /api/orders/audit` — inspect observed orders, trade IDs, partial fills, unverified origin and fee-related alerts.

**This patch does not submit trades, automatically label historical orders as EdgePilot orders, or post broker trades into realized P&L.** Public order detail `trades[]` includes unique trade IDs and execution price/quantity, but not reliable per-trade fees. Public transaction history reports fees yet lacks an order ID. The two cannot safely be joined by timestamp or approximate price alone. Uncertain executions remain unattributed and profit values unverified. Direct source registration of EdgePilot-created orders is intentionally reserved for a future audited execution component; there is currently no exposed registration API that could falsely claim an outside order.

Operational caveat: Public's order detail endpoint retains only approximately 30 days of order records. The snapshot-based audit cannot discover all prior orders, and imported broker transactions may lag. **No order means no inference about performance.** Live execution is still disabled.

Validation: `cd backend && python -m unittest discover -s tests -v`.

## v0.19.3 — Optional AI intelligence foundation

- **Off by default:** AI research is enabled separately from the broker and disabled until the owner explicitly opts in.
- Set `OPENAI_API_KEY` and optionally `OPENAI_MODEL` only on the private backend; never in the Android app.
- The AI tab supports on-demand research using **only the question and market context the user chooses to submit**; it does not ingest personal portfolio data or live market quotes.
- `/api/ai/analyze` uses OpenAI's Responses API with `store=false` and no tools. It cannot place orders, deposit/withdraw funds, alter settings or bypass existing risk safeguards.
- `/api/ai/status` and `/api/ai/history` display settings and a private audit history.
- The user sets a monthly *local reservation budget* in dollars. The system pessimistically reserves $0.20 per request using a serialized SQLite transaction, preventing excessive application requests, but **does not know true token billing rates** and is **not a guaranteed OpenAI spending cap**. Set platform-level billing controls. Failed/uncertain attempts retain their reserved amount.
- A ChatGPT ↔ EdgePilot connector is **not deployed or enabled**; its preference is reserved but cannot be activated.
- This milestone is not an autonomous signal generator or investment prediction engine. Live broker orders remain disabled.

To test: `cd backend && python -m unittest discover -s tests -v`. The OpenAI network request requires your own API key and was not exercised during local tests.


## v0.19.4 — Market snapshots for optional AI research
- Adds official Public equity quote lookup and prediction event contract lookup with strict symbol validation, server-side authorization, and a read-only API. These routes are request-triggered, not a continuous scanner.
- Shows actual bid/ask, spread, quote timestamps (when supplied) and available market data, without claiming a fair value or predicting price changes.
- Adds an explicit, separately confirmed button to send an allowlisted *fresh quote snapshot* and your question to OpenAI when built-in AI is enabled. Neither API credentials nor account identifiers are sent.
- Does not fetch general news, calibrate probabilities, rank investments or execute orders. No live execution or autonomous engine is activated.
- Quote availability and exact payload shape must be validated with an authenticated Public account before live use.


## v0.19.5 — Read-only opportunity research scanner
- Enter a personal watchlist of up to 25 stocks/ETFs on Markets, then use **Scan opportunities**. Enabled prediction-market watch rules are included with independently user-supplied fair-probability assumptions.
- Uses broker bid/ask, volume, quote timestamps when supplied, and contract status to score *quote quality*. A high score **is not a forecast of profit**. Stocks have no estimated expected value without a calibrated directional model.
- Prediction-contract expected value is illustrative, assumes holding to settlement and your manually supplied fair probability, and subtracts an estimated 2-cent entry fee; it is **not** a validated probabilistic model. Actual fees may differ.
- Scan exceptions produce unavailable records rather than fabricated prices. Runs are stored privately on the SQLite backend for audits. Scanning is on demand, not unattended.
- **No live orders, autonomous execution, market-wide discovery, AI-driven predictions, or performance claims.** The existing source needs authenticated broker testing and strong production authentication before being hosted publicly.


## v0.19.6 — Automatic discovery modes (READ ONLY)
- Automatic Discovery **default**: retrieve Public’s equity instrument catalog (`GET /userapigateway/trading/instruments`) and take a bounded rotating sample, plus a small volume-sorted page of open prediction events (`POST /userapigateway/eventcontract/summary`). Inspect at most two contracts per selected event.
- Hybrid Discovery: same broker discovery plus user-provided equities and enabled prediction watch rules. Watchlist Only: solely user-entered symbols/contract rules.
- Scan sizes configurable: 1–40 equities, 0–10 events. Saves a rotation cursor in local SQLite. A scan is partial market coverage, not whole-exchange real-time surveillance. No directional predictions or automatic orders.
- Catalog ingestion intentionally excludes non-equity instruments. The API may not distinguish ETFs from common stocks in the basic type filter; both can be included if represented as equities.
- Requires a working authenticated Public API configuration; all source responses remain unverified against a real account until deployment and live testing.
- Data provider API restrictions and request limits apply. For production, implement scheduling, caching, backoff, data freshness alerts and historical predictive validation.

## v0.19.9 — Historical predictive research foundation
- Adds historical CSV import (date,open,close) and an explicit, non-optimized trailing-momentum baseline.
- Chronological 60/40 training and held-out testing by default; signal at close and next-open entry avoids look-ahead on the entry bar.
- Models a configurable estimate of round-trip costs; reports compounded return, win rate, trade count, and maximum drawdown.
- Adds a Historical Strategy Study panel to Markets. Does **not** automatically pull broker historical bars, forecast future returns, or authorize trading.
- Adds a persistent release CHANGELOG.md. Future versions must update it with verified test results and remaining limitations.


## v0.19.9 — Broker daily historical data (read only)
- Markets → Historical Strategy Study → Fetch history from Public. Enter an equity/ETF symbol, select 1Y/5Y/10Y/All and choose Fetch & Run. Existing lookback, hold, costs and training split settings apply.
- Uses official Public `GET /userapigateway/historicdata/EQUITY/{symbol}/{period}/ONE_DAY?tradingSessionToggle=REGULAR_HOURS` with backend-managed API tokens. Never enter a broker secret in the PWA.
- Caches validated daily bars in SQLite for six hours; optionally force refresh. Broker errors fail closed; no synthetic fallback. Must have ≥50 dated bars.
- This is historical research, not a directional prediction, a trading signal, or evidence of live profitability. Prediction contracts require a separate history source/strategy. Cash/dividend/split adjustments and data vendor timestamps require real-account verification.
- Public documentation: https://public.com/api/docs/resources/market-data/get-bars-v2-with-aggregation
- No trade execution is enabled.

**Validation for v0.19.9:** 65 local automated tests passed; Python compilation and JavaScript syntax checks passed; ZIP integrity verified. Public real-account response was not tested.


## v0.19.9 — Walk-forward research validation
Under **Markets → Walk-Forward Validation**, select Public daily history or pasted CSV. The expanding-window backtest selects one momentum lookback using past data, evaluates it on later non-overlapping windows, and reports out-of-sample results, win rate, compounded modeled returns, and maximum drawdown. It flags small sample sizes and inconsistent returns rather than implying safety or profitability. Endpoint: `POST /api/predictive/walk-forward`. This module is read-only and cannot enable trading.


## v0.19.11 secure session migration (not yet deployed)

- Existing `EDGE_APP_TOKEN` is used once to sign in; it is not an API authorization header after this release.
- API data is available only after an 8-hour host-only secure session cookie is established. Mutations require a same-origin request and CSRF token. Sessions persist across reloads, but a refresh rotates the anti-CSRF token. Sign out revokes the session immediately.
- Opening a page at one hostname and entering another backend hostname is blocked intentionally. Use the Render hostname until the custom domain has an active HTTPS certificate; then sign in directly at the custom HTTPS domain.
- Render secrets and database contents must never be committed. Reuse the existing `EDGE_APP_TOKEN` environment variable; no new secret is required for this migration.
- The login screen and API header contract change. v0.19.10 clients cannot authenticate against the new backend; refresh or reinstall the new PWA after deployment.
- The web UI remains accessible to anonymous visitors, but all financial endpoints remain authenticated. Additional private access controls and MFA are not yet deployed; do not connect Public brokerage credentials.
- Production builds still disallow all broker order submissions. To apply this source to Render, merge the reviewed PR to `main` only after CI and release checks succeed. Render currently has branch auto-deploy enabled; merging may deploy immediately.


## v0.19.12 Android test APK (review branch)
Android test build instructions are in `APK_TESTING.md`. A GitHub Actions workflow produces a private debug APK as a downloadable workflow artifact; the code is not merged to production automatically. The backend remains v0.19.11, and orders remain disabled.
