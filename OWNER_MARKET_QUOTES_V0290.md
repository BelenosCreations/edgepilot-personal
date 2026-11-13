# v0.2.90 — Independent owner manual Public market quotes

This is a one-owner, **research-only**, request-driven market quote feature. The Public Individual API documents `POST /userapigateway/marketdata/{accountId}/quotes` for EQUITY and CRYPTO with the `marketdata` scope. Public's personal API documentation describes no additional API use fee, but actual quote access still depends on each credential/account's provider permissions. The official docs do **not** establish EdgePilot's right to retain quotes, redistribute market data or automatically execute a paper-ledger simulation.

## Trust and identity boundary

The existing independently authenticated `/owner` page presents a manual stock/ETF (EQUITY) or crypto (CRYPTO) symbol input and a **Retrieve source quote** button. No browser quote is requested on sign-in, account discovery or refresh. Its POST route requires the original same-origin identity CSRF check, verified owner identity, actively verified Public account, the sole-owner rollout flag and active sole-owner status checked before and after provider network activity. That last check ensures enrollment of another user in the middle of the request fails closed. The route cannot use the legacy global-token auth.

The adapter independently finds the selected Public provider account ID from the private, user-owned tenant database. It checks live account enrollment, brokerage connection revocation, credential revision, active identity, the authoritative brokerage account list and an existing server-side read request quota before making exactly one allowlisted quotes request. It never accepts a caller-supplied provider account ID, market-data rights assertion, quote, account owner or credential. A revoked identity or changed account/credential after the request refuses the result. No broker key, account reference or bearer token appears in the JSON response.

## What is—and is not—displayed

Returns only source-reported last, bid and ask (where present), source quote timestamps, server receipt time, freshness indicators and explicit Public API attribution. Missing prices stay absent and missing or malformed source timestamps/prices fail closed. An old quote is shown as **stale** rather than silently relabeled current. Equity market hours are not inferred from a timestamp. No guaranteed price, suggested fill price, real-time guarantee, performance, P&L, forecast, return chart, autonomous opportunity ranking or investment advice is claimed.

Every returned observation includes `cacheRightsVerified=false`, `paperFillEligible=false`, `executable=false`, `ordersEnabled=false` and `transfersEnabled=false`. It cannot be inserted into the v0.2.88–v0.2.89 paper ledger. The browser does not persist quotes, cache them, poll in the background or mingle them with unrelated accounts. The Public API quote endpoint itself uses HTTP POST **only to request market data**, not to place an order.

## Acceptance and gates

- Unit tests use fake Public HTTPS responses, two identities, account isolation, data-source failures, stale observations, revoked credentials and identity logout mid-request. They do not call a real broker.
- CI checks backend unit/HTTP isolation, credential exposure and JavaScript syntax including owner-dashboard.js. PR CI, merged-main CI, and existing Render auto-deploy must all pass; a successful deploy does not prove the real user's API key has the `marketdata` scope.
- The owner must sign into `/account`, navigate to `/owner`, select the verified linked account, request a symbol such as AAPL and report **whether a source quote or the safe unavailable status appears**, without sharing any key. They should separately reconcile their Public account balance against the Public app. No account value is committed to GitHub.
- Only after a separately verified market-data retention/license policy and a production-grade encrypted paper-ledger backup/restore may any persistent paper fills be considered. All live brokerage orders, autonomous workers and bank transfers remain disabled regardless.

**Additional cost:** $0 beyond the already-existing Render service. No external feed/vendor, new hosted app or paid API was added.
