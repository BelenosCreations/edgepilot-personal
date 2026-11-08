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


## v0.19.11 secure sessions

**Migration and scope:** `EDGE_APP_TOKEN` is now the one-time browser login secret; keep it in Render Environment and your password manager. Do not send it via `X-Edge-Token` after upgrading. API endpoints check an eight-hour randomly generated, host-only `__Host-` secure/HttpOnly/SameSite=Strict cookie stored as a SHA-256 digest on the existing persistent disk. The login secret is cleared from the UI on success and is never written to the browser storage. Logout revokes the cookie server-side.

All API state changes require HTTPS same-origin `Origin` matching and an `X-Edge-CSRF` token held in JavaScript memory; a page reload rotates the CSRF token via authenticated GET. User-provided backend host overrides are blocked. Login failures are rate limited per remote network source for ten minutes. Basic HSTS, no-store, CSP, frame blocking and permissions policy headers are applied.

**Important remaining risks:** The page itself is internet-visible and the single bearer login token is not multi-factor authentication. Rate limiting does not eliminate online brute-force or denial-of-service risks. SQLite session state and AI histories reside on a persistent disk without application-layer encryption. The existing UI uses inline event handlers, so CSP allows `unsafe-inline`; this is not a full XSS defense or independent security audit. Because of these limitations, use an additional private access gateway and improve login before connecting a Public API secret. Public may grant trading permissions regardless of EdgePilot's own read-only behavior.


## v0.19.12 Android test wrapper
Android WebView loads only `https://edgepilot.belenoscreations.biz/`; SSL bypasses, untrusted origins, mixed content, third-party cookies and local file access are blocked. First-party secure session cookies remain server-side authenticated. The debug APK is non-production and not independently audited; no Public API secret belongs in the application package.


## v0.19.13 — User-managed Public API credentials
Under Settings, the Public API secret is sent once over the HTTPS same-origin authenticated, CSRF-protected API, encrypted by Fernet, and stored as ciphertext in the persistent SQLite database. The *separate* `EDGE_CREDENTIAL_KEY` must be a stable Fernet key configured privately in Render; never put it in Git, the APK, a user message, or the database. It must be backed up securely because losing or rotating it without re-encryption makes saved credentials inaccessible. Never return credential bytes, ciphertext, or key fragments to clients. The key can be replaced or disconnected in-app; disconnect tombstones any legacy environment secret. Browser form values are cleared after save. Server logs must not include request bodies. This is not a replacement for an external authenticated gateway/MFA, and Public secrets may still have trade privileges at the broker.
