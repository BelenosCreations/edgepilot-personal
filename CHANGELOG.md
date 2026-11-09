## v0.19.15.3 — 2026-11-08 — Public Synchronization Acknowledge All
**Added:** Public Synchronization now shows the full count of outstanding alerts (including those beyond the latest 50 displayed) and a disabled-when-empty **Acknowledge All** button with an explicit confirmation prompt. New authenticated, same-origin/CSRF-protected `POST /api/sync/alerts/acknowledge-all` endpoint and atomic `dismiss_all` journal action.
**Changed:** Bulk acknowledgement is strictly scoped to the currently selected Public account and only updates `OPEN` notices to `ACKNOWLEDGED`. It leaves broker transaction history, alert details, execution attribution, repurchase permissions, risk settings and trading configuration untouched. The action returns the affected count, supports safe repeats, and refreshes the alert list.
**Fixed:** Removes the need to dismiss dozens of informational synchronization alerts individually; accounts with more than 50 open alerts can now acknowledge every outstanding alert without losing the underlying records.
**Tests:** Added tests covering 60 open alerts, cross-account separation, retained historical records, idempotency, session/CSRF/origin enforcement, selected-account requirement and UI confirmation; full CI results required before deployment.
**Known limitations:** Acknowledged notices stay acknowledged when the same event fingerprint is encountered again. Bulk acknowledgement is informational and does not verify or reconcile individual sales, grant permission to repurchase or resolve uncertain orders. Historical accounting and live order execution remain disabled/unverified as before.
**Next:** Verify full CI and deploy to Render, then confirm the Acknowledge All button works in the existing Android app without a new APK.

## v0.19.15.2 — 2026-11-08 — Protected balance range correction
**Added:** Regression tests covering 0% and 99% as valid protected percentages, while -1%, 100%, and 101% are rejected. UI assertion verifies the permitted numeric input range.
**Changed:** Settings → Protected balance now accepts 0–99% inclusive (previously 1–100%). Default remains 50%, and no existing saved user setting is silently changed. A previously saved 100% must be manually adjusted to 99% or less before saving settings again.
**Fixed:** Prevents setting a new 100% protected balance, which would reserve the entire selected balance and leave no funds available under the risk allocation model. 0% protects none of the selected balance but still respects separate spending, per-trade, and buying-power limits.
**Tests:** All 133 GitHub Actions Python/Flask HTTP and source checks passed (run 42535126402), including 0%/99% acceptance, 100% rejection, and the UI numeric range assertion. Actual broker-connected usability remains to be checked on Android.
**Known limitations:** Percentage validation controls configuration only. Existing brokerage data, security limitations, and trading safeguards are unchanged. Live order submission and autonomous execution remain disabled.
**Next:** Verify GitHub CI and Render deployment; confirm the Settings field accepts 0 and 99 but rejects 100 without changing other saved controls.

## v0.19.15.1 — 2026-11-08 — Mobile header and broker-value clarity
**Added:** Compact, two-field Public snapshot in Overview separating cash-only buying power from the aggregate market value of existing positions. Each successful dashboard fetch labels when the values were refreshed locally; an unavailable broker response shows a clear unavailable message.
**Changed:** Removed the redundant PERSONAL TRADING INSTANCE subtitle next to the approved, uncropped EdgePilot logo. The logo and Secure Session badge now share a responsive, compact header. The primary account value still comes directly from Public's `totalAccountValue`, and buying power is never added to it.
**Fixed:** Avoids confusing the conservative position-value total or brokerage buying power with the actual total account value. Updates backend version and regression-test assertions for this web-only patch.
**Tests:** All 131 GitHub Actions Python/Flask HTTP tests passed (run 42534639998), including the three new dashboard presentation checks; Python compilation and JavaScript syntax validation passed. The owner independently confirmed that the previous displayed $0.15 total matched their Public account. The new cash/positions presentation still needs a phone-side visual check.
**Known limitations:** Brokerage values are on-demand snapshots, not real-time streaming quotes or reconciled profit. The 15-minute markets feed still requires a user-triggered, real-account validation; no result is invented. The existing Android APK loads web updates without reinstalling; Android launcher version remains 0.19.15. MFA/private gateway and full broker security review remain pending. Live trading stays disabled.
**Next:** Confirm production deployment, validate the new layout in the existing Android app, and ask the owner to run one read-only 15-minute market scan to inspect its real results.

## v0.19.15 — 2026-11-08 — Approved EdgePilot logo and app icon
**Added:** The owner's approved EdgePilot_Option_B_13in_400DPI.png is displayed as the full, uncropped branded logo on the web/PWA header. The approved EdgePilot_App_Icon_1024.png and EdgePilot_Android_Icon_Package.zip supply browser favicon, PWA/Android launcher assets, and a platform-safe Android adaptive foreground.
**Changed:** Browser/PWA manifest now advertises accurate icon purposes and a separately padded maskable alternative; Android launcher uses density-specific PNGs plus an adaptive launcher for Android 8+. Updated APK version to 0.19.15 and CI artifact name. No trading controls or authentication paths changed.
**Fixed:** Updated stale Flask health-version assertion to 0.19.15. Replaced generic green-letter EdgePilot launcher graphic and text-only website header with approved artwork. Original branding and color composition are preserved; display images are downsampled for device use without cropping.
**Tests:** Local image-size, manifest, Android resource, PNG signature, and source checks added; CI must pass Python HTTP/unit and Android APK build on the release branch. Physical-device visual testing and installed APK signature/update compatibility remain outstanding.
**Known limitations:** Native app requires downloading/installing a newly built APK for the Android launcher icon to update; the existing installed APK will receive the new hosted website header automatically. Debug APK signing may differ between CI runs, requiring uninstall/reinstall. Website images remain accessible to anonymous visitors; all financial data endpoints retain secure sessions. No brokerage credentials connected; live trading disabled.
**Next:** Confirm GitHub CI and release, verify branded website and new Android APK on a phone. Make production-signed Android package later using securely backed-up signing credentials.

## v0.19.14 — 2026-11-08 — 15-minute market discovery (read-only)
**Added:** Public `FIFTEEN_MINUTES` event summary filter and bounded, one-shot event-details scanner; new Markets → 15-Minute Markets mobile panel with target price, close countdown at capture, YES/NO bid, ask, spread and illustrative break-even win rate. Scanner is authenticated; the UI prompts for a Public connection instead of fabricating results.
**Changed:** Validates Public event identity, 15-minute timeline, tradability, quote completeness and numeric precision before display. At most two summary pages and eight details are queried per manual refresh. No order/preflight calls, background worker, automated polling, or server-side simulated fills are included.
**Fixed:** Omits expired, future, halted, settled, mismatched and malformed contract windows, and avoids describing implied contract prices as independently validated probabilities.
**Tests:** Local parser/fixture tests and existing baseline; GitHub Actions results to be verified before production deployment. Live Public API response is still untested without account credentials.
**Known limitations:** Prices are event-detail snapshots, not real-time bid/ask-size quotes; no paper ledger, settlement tracking, or strategy forecast yet. Break-even assumes an illustrative $0.02 buy fee, which is not a broker preflight quote. Partial 15-minute market coverage; no brokerage order functionality.
**Next:** Validate real Public payloads and read-only market listing after the account access controls are strengthened; add safe paper trade recording and settlement verification in a later release.

## v0.19.13 — 2026-11-08 — Public API connection in Settings
**Added:** Settings → Public Brokerage Connection includes masked secret entry, Save API key, Test connection, Disconnect, and status. Encrypted server-only Fernet vault requires `EDGE_CREDENTIAL_KEY`, an independent hosting secret; account selection and live-order arm state are cleared on credential changes. Authenticated API routes are same-origin and CSRF protected.
**Changed:** Public API authentication first reads the encrypted Settings credential. Existing hosting environment secret is used only as a legacy fallback when Settings has never been configured; disconnect creates a tombstone to suppress that fallback. No API secret is returned to the browser or included in general settings JSON. Android APK needs no changes because it loads the hosted Settings UI.
**Fixed:** Replacing or clearing credentials invalidates cached broker tokens to prevent carrying authentication across accounts. Fail-closed when encryption configuration is absent or a stored credential cannot be decrypted; no plaintext credential database writes or credential-bearing logs.
**Tests:** 107 automated tests passed on GitHub Actions run 42527547538, including the encrypted-credential Flask HTTP route test. Python compilation and JavaScript syntax checks passed. v0.19.12 Android APK installation and sign-in were confirmed on a real device. Hosted v0.19.13 verification remains required after deployment.
**Known limitations:** Public API secrets may authorize trading regardless of the current read-only app; the service is internet-accessible and still lacks MFA/private access gateway and a full security review. A correctly backed up, separate `EDGE_CREDENTIAL_KEY` is required; losing it makes encrypted credentials unrecoverable. Real broker connectivity remains unverified. Real trading remains disabled.
**Next:** Confirm the Render deployment and encryption-key configuration; verify authenticated Settings metadata and read-only diagnostics. Do not enter a brokerage credential until stronger private access protections are reviewed.

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
