# EdgePilot private-instance security

For the intended single owner, keep one private server and persistent volume, use your personal Public API secret, and generate a random EdgePilot access token of at least 32 characters. The ZIP contains no personal credentials and has no user registration or administrator functions.

Never email or message Public secrets, include them in screenshots, commit them to Git, or type them in the browser's backend-token field. Set the Public secret only in the host's secret environment variable. The app access token is also sensitive; keep it private.

The backend only authorizes API requests with its configured `EDGE_APP_TOKEN`. Public page assets can be accessed without authentication, but account data cannot. For serious use, protect the *entire* app behind an authenticated access gateway in addition to HTTPS; current single-token authorization is a beta safeguard, not a full security audit.

**The current personal beta disables live broker order submissions and autonomous trading.** It does not implement secure order reconciliation, P&L-based daily loss cutoff, or trading provenance; these must be completed and tested before permitting live use. No deposits or withdrawals are implemented.

The independent balance currently represents a fixed assigned virtual reference and does **not yet automatically track profits/losses** or independently reconcile sales from within Public. Do not treat the allocation as segregated cash.


### v0.19.2 audit controls
Order import is READ ONLY. Never grant order provenance on the basis of a matching timestamp or a client-provided order ID. Fees missing from broker execution details remain unverified. A broker API or data error aborts the full audit rather than posting partial P&L. Real money, automated trades, and bank transfers remain disabled.

### Optional AI provider
External analysis sends only submitted text fields to the configured provider. Do not paste API tokens, account identifiers, personal details or confidential holdings in those fields. Store the AI key as a host secret, rotate if exposed, and use separate provider billing protections. Research prompts/responses are stored in the single-user SQLite database and need encrypted disk/backup policies. Local AI budget reservation is not an upstream bill limit.

## v0.19.8 — Historical data
Public historical requests originate server-side, using the existing secure backend token. Validated ticker path segments and fixed enum parameters prevent arbitrary URL access. SQLite contains market prices and timestamps only, not API credentials. A successful backtest never authorizes an order.


## v0.19.10 read-only connection verification
`GET /api/connection/verify` requires the single-user EdgePilot access token. It performs only Public `GET` calls to account listing and (when selected) portfolio; it does not return API secrets, bearer tokens, complete account identifiers, balances or holdings. `/healthz` deliberately exposes only a minimal liveness signal. The PWA does not persist the app access token to browser storage, but it remains in memory while connected.

**Do not treat the Public secret as scope-restricted/read-only:** It may have broader account permissions, even though EdgePilot intentionally provides a read-only diagnostic. Use a trusted private host and, before real trading is developed, add stronger app authentication and credential management. Never enable auto-trading on this release. Host access may incur charges even while only checking balances.
