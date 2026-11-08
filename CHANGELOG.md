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
