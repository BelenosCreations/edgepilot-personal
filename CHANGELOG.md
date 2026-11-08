## v0.19.13 — 2026-11-08 — Public API connection in Settings (development review)
**Added:** Settings → Public Brokerage Connection includes masked secret entry, Save API key, Test connection, Disconnect, and status. Encrypted server-only Fernet vault requires `EDGE_CREDENTIAL_KEY`, an independent hosting secret; account selection and live-order arm state are cleared on credential changes. Authenticated API routes are same-origin and CSRF protected.
**Changed:** Public API authentication first reads the encrypted Settings credential. Existing hosting environment secret is used only as a legacy fallback when Settings has never been configured; disconnect creates a tombstone to suppress that fallback. No API secret is returned to the browser or included in general settings JSON. Android APK needs no changes because it loads the hosted Settings UI.
**Fixed:** Replacing or clearing credentials invalidates cached broker tokens to prevent carrying authentication across accounts. Fail-closed when encryption configuration is absent or a stored credential cannot be decrypted; no plaintext credential database writes or credential-bearing logs.
**Tests:** 106 automated tests passed on GitHub Actions run 42526505628 with all Flask dependencies; local baseline 106 tests passed with seven HTTP tests skipped because Flask was not installed locally. Python compilation and JavaScript syntax checks passed. This remains a draft review, not deployed. Existing live v0.19.11 is unchanged until an explicitly approved deployment.
**Known limitations:** Public API secrets may authorize trading regardless of the current read-only app; the service is internet-accessible and still lacks MFA/private access gateway and a full security review. A correctly backed up, separate `EDGE_CREDENTIAL_KEY` is required; losing it makes encrypted credentials unrecoverable. Real broker connectivity remains unverified. Real trading remains disabled.
**Next:** Set the vault encryption key privately in Render only after review approval, perform CI verification, test no-secrets responses and reauthentication, then deploy with explicit user authorization.

## v0.19.12 — 2026-11-08 — Android APK test foundation
**Added:** Android debug APK build workflow for private GitHub Actions artifacts; fixed-host HTTPS Android shell for `edgepilot.belenoscreations.biz`; custom launcher icon; `APK_TESTING.md` with Android-only installation instructions.
**Changed:** Android wrapper targets the production HTTPS origin only, supports existing v0.19.11 session cookies and theme localStorage, and blocks off-origin navigation, mixed content, third-party cookies, local files, and certificate errors. Android app version synchronized with 0.19.12; backend remains v0.19.11.
**Fixed:** Removed arbitrary-server entry flow, which could send credentials to an unintended origin; enabled DOM storage for saved theme preference.
**Tests:** 98 Python unit/HTTP tests passed in GitHub Actions; the Android Gradle debug APK build passed on GitHub Actions after upgrading SDK setup to v4. ZIP/APK contents and Android signing-block presence were checked. Android installation and login still require on-device validation.
**Known limitations:** APK is a debug-signed WebView prototype, not an independently audited native app or production-signed release. Debug signature may change across runs. No background trading or notifications. No Public credentials should be configured. The live Render backend remains v0.19.11.

## v0.19.11 — 2026-11-08
**Added:** Server-side, short-lived, host-only HttpOnly/Secure/SameSite=Strict login sessions; login throttling; logout; same-origin checks for state changes; rotating CSRF tokens; authenticated session recovery on page reload; security headers; Flask HTTP regression tests and GitHub Actions CI.
**Changed:** The existing `EDGE_APP_TOKEN` is now a login-only secret; the browser clears it after sign-in and uses the session cookie rather than sending it on every API call. API requests with the legacy `X-Edge-Token` header no longer authenticate. Sessions last eight hours. External backend URL entry is disabled; sign-in is restricted to the current HTTPS origin.
**Fixed:** Reduced prolonged JavaScript exposure of the reusable app token; blocks cross-origin state-changing requests and missing CSRF tokens; new route tests check the read-only health endpoint, login, logout, refresh, and auth rejection.
**Tests:** 91 local standard-library tests passed; 7 Flask HTTP tests were skipped locally because Flask is not installed here and package fetching is unavailable. Python compilation and JavaScript syntax checks passed. GitHub Actions completed successfully: all 98 tests passed with backend dependencies, including Flask HTTP route tests. See GitHub Actions run 42518842598. Tests have not yet been repeated on the live Render deployment.
**Known limitations:** Not yet deployed or tested against a real Render HTTP session. This is not an MFA or independently security-audited login system; the reusable token must be held in a password manager. Login rate limiting is coarse by network source and can cause temporary lockouts. Inline JavaScript remains for legacy UI controls, so the CSP still allows `unsafe-inline`; XSS audit and stronger authentication/private access gateway remain required before adding a Public API secret. The dashboard HTML is publicly reachable, but its `/api` data is protected. User must sign in again after upgrade. Trading remains disabled.
**Next:** Verify CI, merge and deliberately deploy after review, run hosted auth/CSRF tests, confirm secure custom domain certificate, then revisit second-factor/private gateway protections before connecting brokerage credentials.

## v0.19.10 — 2026-11-08
**Added:** Authenticated read-only Public connection diagnostic; minimal unauthenticated hosting liveness endpoint; home-screen Test Public connection control; self-origin backend URL default for PWA; Android-first deployment guide.
**Changed:** Managed hosting health check uses `/healthz`. New-install demonstration defaults are not tied to the $10 proof-of-concept allocation; all limits remain adjustable and enforceability is contingent on the live execution engine being built.
**Fixed:** Health/version label now reflects current source. Broker diagnostics distinguish unconfigured credentials, broker account listing, selected account validity, and portfolio-read success without returning the secret.
**Tests:** 80 standard-library unit tests passed, including eight new injected broker-diagnostic tests; Python compilation, JavaScript syntax, and ZIP-integrity checks passed. Flask HTTP integration tests, external authenticated broker requests, and hosted deployment testing remain outstanding.
**Known limitations:** Single-token beta auth; no externally tested credentials; trades disabled; no automatic P&L attribution or profit-adjusted independent balance; no one-tap PWA deployment from ZIP; cloud hosting requires the user to provision their own accounts.
**Next:** User-controlled private cloud deploy and actual Public read-only connection verification, followed by order provenance/ledger validation.

# EdgePilot Changelog

Version history distinguishes shipped code from design ideas. Dates are release dates when known; older entries are reconstructed from prior packages, not audited production releases.

## v0.19.9 — 2026-11-08
**Added:** Anchored expanding-window walk-forward evaluation for historical stock/ETF data, chronological model-parameter selection on training data only, disjoint out-of-sample testing, and a mobile validation report. Supports Public historical bars or user-provided CSV.
**Changed:** Research reports explicitly distinguish windows and evidence sufficiency from order eligibility; no studied strategy is trade-authorized.
**Fixed:** Reject overlapping test windows, invalid price bars, unsupported parameters, and insufficient sample windows rather than claiming a validated edge.
**Tests:** Updated automated tests for walk-forward calculation and baseline suite; see release README for actual test count.
**Known limitations:** Uses idealized daily opening prices and a simple long-only momentum rule; parameter-selection bias, corporate actions, data gaps, trading costs, and regime changes remain potential sources of error. Authenticated Public integration remains unverified. Not deployed; no live trading.
**Next:** Validate market data and account sync with a securely hosted read-only Public connection before developing actual execution.

## v0.19.8 — 2026-11-08
**Added:** Read-only Public stock/ETF daily-bar retrieval using the documented EQUITY Get bars v2 endpoint, authenticated via private backend; persisted per-symbol/per-period six-hour SQLite cache; mobile Fetch & Run historical study controls.
**Changed:** Momentum backtest can now use broker historical daily bars; manual CSV remains supported. Added provenance (symbol, period, date range, cache status) and historical-data warning.
**Fixed:** Reject invalid or duplicate timestamps, non-finite prices, invalid OHLC ranges, short histories, unexpected symbols, and unsupported periods rather than silently constructing price data.
**Tests:** 65 automated unit tests passed; Python compile and JavaScript syntax checks passed; ZIP integrity verified. Public live API connectivity was not tested.
**Known limitations:** Not tested with authenticated Public account; broker payload changes could require adapter updates. Historical studies do not account fully for dividends/splits, delistings, market impact or intraday execution; no validated forward prediction. No production deployment or live orders.
**Next:** Improve strategy validation and add controlled walk-forward analysis before trade eligibility.

## v0.19.7 — 2026-11-08
**Added**: Historical CSV research and a no-look-ahead momentum backtest with chronological holdout split, modeled trading costs, and a read-only Markets study panel.
**Changed**: App version/health to v0.19.7. Introduced this formal changelog.
**Tests**: See current release validation below in README or release notes.
**Limitations**: No automatic historical-data feed; no calibrated forecasting, no live execution, no authenticated Public production test, no hosted Android app.

## v0.19.6 — 2026-11-08
**Added**: Automatic, hybrid, and watchlist-only discovery modes, bounded equity/event scans, catalog rotation.
**Tests**: Previous release reported 51 local automated tests; not independently reverified here as a historical claim.
**Limitations**: Research discovery only, not predicted profits or automatic trading.

## v0.19.5 — 2026-11-08
**Added**: Market-quality scanning, quote and spread checks, manually supplied prediction probabilities.
**Limitations**: No validated investment forecasts.

## v0.19.4 — 2026-11-08
**Added**: Read-only equity/event snapshots; optional explicit snapshot sharing with AI.

## v0.19.3 — 2026-11-08
**Added**: Optional built-in OpenAI research screen and research history.

## v0.19.2 — 2026-11-08
**Added**: Order audit, execution IDs, partial-fill handling and conflicting record checks.

## v0.19.1 — 2026-11-08
**Added**: Read-only Public portfolio/transaction synchronization and outside-sale alerts.

## v0.19 — 2026-11-08
**Added**: Portfolio home screen, limited historical account snapshots, appearance modes.

## v0.8 and earlier — Prior experimental builds
**Added over multiple builds**: Local ledger, fail-closed risk calculator, independent balance configuration, manual/automatic preferences, initial Android/PWA shell.
**Limitations**: The entire development sequence remains a prototype; all real trading is disabled.
