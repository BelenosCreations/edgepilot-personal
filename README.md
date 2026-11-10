# EdgePilot

**Android-first trading intelligence, portfolio research, and risk-controlled automation — in private development.**

EdgePilot is a personal trading-intelligence platform designed to bring brokerage visibility, market discovery, historical strategy research, configurable risk limits, and eventually carefully controlled automated execution into one experience. Its principal integration is the [Public](https://public.com/) brokerage API. The application covers stocks and ETFs, investigates prediction-market opportunities, and is being designed with extensibility for additional asset types and strategies.

The goal is not simply to display prices or place trades. EdgePilot is intended to provide a traceable decision system: understand what the broker actually reported, distinguish observation from simulated results, evaluate a strategy against costs and risk, and refuse activity when data or authorization is uncertain.

> **Development status:** The repository is currently developing **v0.2.33**. The existing owner-facing application supports brokerage research and experimental Observe/Paper modes; **real brokerage order submission, autonomous live trading, and bank transfers remain disabled**. A separate, gated multi-user identity platform now includes invitation registration, individually encrypted Public connections, read-only account integration, and WebAuthn passkey endpoints. An Android-capable passkey account screen provides owner-scoped Public account discovery, verified read-only linking, sanitized portfolio views, an independently gated **inactive** monitoring-plan preview, and per-account watchlist editing that cannot activate any scanner, trade, or fund transfer. Actual multi-device biometric sign-in, account-specific running workers, and live multi-user acceptance are not yet verified. See [CHANGELOG.md](CHANGELOG.md) for release history, and [DEVELOPMENT_CONTINUITY.md](DEVELOPMENT_CONTINUITY.md) for a durable new-conversation development checkpoint.

The shared-user development path now includes strict owner-scoped account watchlists:
each member can save a validated stock-symbol list for a linked account without
touching another account or starting any monitor. The preview and editing APIs
are separately disabled by default. See
[TENANT_WATCHLIST_EDIT_RUNBOOK.md](TENANT_WATCHLIST_EDIT_RUNBOOK.md) for the
security and operational requirements.

## The project vision

EdgePilot is being built around a few durable objectives:

- **One cohesive control center.** Bring portfolio monitoring, market research, historical analysis, observation health, and trading-strategy configuration into a mobile-first interface.
- **Intelligence before execution.** Use market data and historical evidence to evaluate potential decisions without confusing a quote-quality score, backtest, AI response, or paper trade with a proven profitable signal.
- **Capital protection by design.** Keep protected balances, exposure limits, loss limits, position ownership, emergency stops, and explicit execution permissions separate from strategy logic.
- **Independent user ownership.** Ultimately, each person will have their own EdgePilot login and connect their own Public API credential; no user should inherit another person's brokerage connection, history, preferences, or automation activity.
- **Future-ready architecture.** Develop toward a shared, multi-user service and multi-device sign-in without requiring every phone to host an independent backend. This is a design objective, not an assertion that the transition has been completed.
- **A cautious path to automation.** Observe, simulate, validate, reconcile, and audit before considering any live execution. Live trading requires a separate decision and further technical and security work.

EdgePilot is currently being developed for private use, not commercial distribution. Its design anticipates the possibility of broader use later without representing that regulatory, security, brokerage-permission, or distribution requirements have already been satisfied.

## The EdgePilot experience

### Overview: portfolio and system health

The Overview screen serves as the main dashboard for the connected owner account. It can display Public-reported account value, buying power, holdings, saved account-value history, and the application's recorded ledger information. Account-value charts support multiple time windows; snapshots are created only when actual broker data has been retrieved rather than inventing missing history.

The screen also surfaces **Observation Health**: whether an Observe/Paper worker is running, when a scan completed, when a validated quote was last seen, accepted and rejected quote counts, market-session status, and recent warnings. Its foreground display refreshes approximately every two minutes without causing another market scan.

A change in total account value is **not automatically trading profit**. Transfers, outside trading, dividends, and other broker activity can affect account value independently of EdgePilot's own accounting.

### Auto-Trade: strategy planning and paper observation

Auto-Trade is a configuration and experimental simulation workspace, **not an enabled live broker trader**. It provides plan settings, risk profiles, stock/ETF allocation controls, position limits, loss thresholds, engine state, and Observe or Paper operating modes.

Observe mode gathers and records eligible market observations. Paper mode can model hypothetical stock entries and exits from broker-sourced quotes using explicit assumptions about spreads and fees. These are simulated transactions, not broker fills, and their results do not establish forward-looking profitability. The stock paper model checks the regular NYSE trading calendar and fails closed when required market-session information is unavailable.

The architecture anticipates other asset classes, including crypto, but the presence of a configuration option should not be interpreted as a complete live data, settlement, or trading engine for that asset.

### Micro-Trade: small-position strategy economics

Micro-Trade explores how transaction costs, spread, slippage, minimum net gain, position sizing, and risk limits affect small trades. Its scenario evaluator distinguishes gross price movement from estimated net outcomes and expected value.

This is intended to remain useful at different account sizes: an initial small allocation is a proof-of-concept choice, not an architectural ceiling, permanent strategy, or guarantee that tiny trades are economical.

### 15-Minute Markets: short-duration prediction-market research

The 15-Minute workspace investigates eligible short-duration prediction-market events through Public's market-data endpoints. It can examine contract status, YES/NO quotes, spreads, targets, and available event timing, while rejecting expired, halted, incomplete, or inconsistent source data.

The current capability is research-oriented. It does not provide a validated probability forecast, guaranteed executable prices, automatic settlement accounting, or broker order submission.

### More: supporting workspaces

Supporting sections include **Markets**, **AI research**, **Funds & Transfers**, and **Settings**.

Markets provides configurable discovery across sampled brokerage instruments and user watchlists, quote-quality research, historical strategy studies, and walk-forward validation. Funds & Transfers is informational: money movement must still be performed through the brokerage's own supported channels. Settings covers connection management, account choice, risk parameters, appearance, and optional integrations.

The bottom navigation is designed for an Android phone, with dedicated Overview, Auto-Trade, Micro-Trade, 15-Minute, and More destinations.

## Market data, research, and accounting

**Brokerage connectivity.** The owner-facing backend can connect to Public through server-managed credentials, retrieve supported account and portfolio information, and fetch available market data. Broker secrets belong on the backend, not inside the Android APK or browser storage. Data availability, rate limits, endpoint behavior, and the permissions granted to a Public credential remain governed by the provider.

**Read-only synchronization.** EdgePilot can capture paginated brokerage transaction history and observed order details, deduplicate provider records, and flag changes or decreases for review. An alert is not proof that EdgePilot executed a trade or that a human manually sold a position. Missing order identifiers and incomplete fee evidence prevent arbitrary attribution of an outside trade to EdgePilot's realized P&L.

**Market discovery.** Automatic Discovery samples supported equity instruments and eligible prediction events; Hybrid mode combines those sources with the user's watchlist; Watchlist Only restricts the universe to explicit selections. This is bounded sampling, not a claim to continuously scan every listed instrument.

**Historical strategy research.** The research tools accept supported historical CSV inputs and can retrieve Public daily stock/ETF bars. They provide a baseline momentum study, chronological training/held-out evaluation, modeled costs, return and drawdown statistics, and expanding-window walk-forward analysis. Results are retrospective and sensitive to assumptions, data quality, corporate actions, and changing market regimes.

**Optional AI analysis.** The built-in OpenAI research path is opt-in and disabled by default. It receives only research context explicitly submitted by the user; its API key is configured on the backend. It cannot submit broker orders, transfer funds, bypass risk controls, or turn an AI opinion into execution authorization. Any local request-budget reservation is not a provider-enforced billing ceiling. A separate private read-only ChatGPT connector remains a future, independently optional integration rather than an active default.

## Architecture

EdgePilot currently consists of a hosted web application, a Python backend, persistent storage, and an Android shell:

~~~text
Android test app (WebView)     Installable browser PWA
            \                       /
             \      HTTPS          /
              v                   v
                 Flask backend
              /       |        \
       Public API   SQLite    Optional AI API
       read paths   records   research only
              \
        Observe / Paper worker
        (no broker execution)
~~~

- **Frontend:** Responsive HTML, CSS, and JavaScript delivered by Flask, with a PWA manifest and local app icons. The current Android application is a WebView wrapper of the hosted interface rather than an offline, fully native trading client.
- **Backend:** Python 3.12, Flask, requests, and internal engine modules covering market data, brokerage evidence, settings, risk calculations, simulation, authentication, observation, and research.
- **Persistence:** SQLite on a persistent server volume for the existing personal deployment. Durable storage, secret management, and tested backup/restore procedures are essential for hosted operation.
- **Hosting:** Docker and a Render Blueprint are included. The present service runs a single-owner backend and an experimental Observe/Paper worker, with SQLite leases to reduce duplicate work. This is not yet a horizontally scaled, independently durable trading-worker system.
- **Android:** Gradle-based test APK project under the android directory. The debug APK loads the approved HTTPS site, never bundles Public credentials, and now prepares WebView for native Credential Manager-backed WebAuthn on supported devices. A verified app-signing certificate and Digital Asset Links association are still prerequisites for real passkey operation.
- **Continuous integration:** GitHub Actions runs backend unit/HTTP tests, Python compilation checks, JavaScript syntax validation, and a separate Android debug-build workflow.

The principal source directories are **backend/** (server, engines, tests, and web assets), **android/** (Android wrapper), and **.github/workflows/** (CI and APK generation).

## Multi-user accounts and biometric sign-in

The intended destination is **one EdgePilot platform with distinct, independently authenticated users**. Each user will sign in to EdgePilot, provide their own Public API credential through a secure flow, and see only their authorized linked accounts and corresponding records. Different Android devices must be able to operate with different users and different Public accounts without sharing account selection, brokerage credentials, history, strategy settings, or monitoring state.

A full implementation requires:

1. Secure onboarding, individual accounts, account recovery, and independently revocable sessions.
2. Server-side encrypted Public connections owned by the authenticated user, with verified broker-account binding and safe credential rotation.
3. Tenant/account authorization on every API request, database query, worker task, cache entry, notification, backup, restore, and migration.
4. Passkey-capable sign-in using WebAuthn, Android Credential Manager, and verified application/website association. Phone biometrics or device PIN verify the user locally; the backend should not store biometric images.
5. Real end-to-end validation with two separate devices, identities, and independently connected Public accounts before declaring the multi-user development stage complete.

**Where this stands now:** Separate identity sessions and invitation-only signup, tenant-owned encrypted Public keys, gated read-only Public account access, and cryptographically verified WebAuthn endpoints are implemented behind independent feature flags. The /account screen includes password, invitation, passkey, key entry, verified account linking and read-only portfolio viewing; the Android WebView can request native Web Authentication on supported devices. Actual biometric passkey enrollment still requires a verified app-signing certificate, Digital Asset Links, a controlled pilot and independent device testing. Production tenant cutover, account-scoped background workers, recovery and two-device acceptance testing are **not complete**.

The tenant vault can be enabled only behind explicit server-side feature gates; storing an unverified credential there does not connect or verify a brokerage account. Synthetic multi-user tests are not equivalent to an activated shared platform. The existing owner connection must never be silently assigned to another user.

The development plan assumes that multi-user Public API integration may be engineered, but that assumption is **not** a statement that Public has approved such use. Applicable provider terms must be checked before external multi-user operation or distribution.

## Security and operational boundaries

Security is a governing constraint, not a marketing claim.

- **No real-money execution:** Production broker order submission, autonomous live trading, deposits, and withdrawals remain disabled. Observe and Paper are not permission to trade.
- **Server-managed credentials:** Public and optional AI secrets must never be committed to Git, embedded in APK files, pasted into support messages, or exposed through client logs. Existing personal brokerage credentials are encrypted server-side where configured, using a separately managed encryption key.
- **Authenticated sessions:** The owner-facing application uses HTTPS, secure server-side sessions, and same-origin/CSRF protections for protected operations. Dormant multi-user identity sessions are separate and cannot be used to access legacy owner endpoints.
- **Explicit user and account scope:** Future brokerage data access, credential decryption, automation work, and history restoration must be authorized for the authenticated owner and intended account; merely knowing an account identifier is insufficient.
- **Fail-closed research and simulation:** Missing quotes, incomplete transaction evidence, revoked credentials, unknown market schedules, and failed checks should not produce invented market data, fabricated gains, or an executable approval.
- **Emergency and rate-control research:** The repository includes synthetic account-scoped leases, budgets, stops, and work-stage fencing tests. Many of these are deliberately disconnected from production. Their successful tests are **not** evidence of a distributed, production-safe stop or broker-side cancellation mechanism.
- **Private operation:** A debug APK or reachable HTTPS endpoint is not a security audit. Strong hosting controls, backups, monitoring, credential rotation, and review of broker permissions remain the operator's responsibility.

A Public API credential can have capabilities broader than the read-only behavior exposed by EdgePilot. Treat it as sensitive even while the app refuses to place trades. Consult [SECURITY.md](SECURITY.md) and the relevant runbooks before changing server flags or attaching credentials.

## Development and testing

The repository can be tested without connecting a real Public account or enabling execution.

From the repository root, install the backend dependencies in a Python 3.12 environment and run:

~~~bash
python -m pip install -r backend/requirements.txt
cd backend
python -m unittest discover -s tests -v
~~~

CI additionally checks Python compilation and the legacy and account-login JavaScript syntax. Android changes are independently built as a debug APK in a separate workflow. The inactive multi-user and broker-safety modules have separate synthetic/negative tests to exercise isolation, malformed requests, revoked access, stale operations, and failure handling. Passing automated tests does not replace real brokerage-contract verification or mobile-device acceptance testing.

The included **render.yaml** and **backend/Dockerfile** describe the private hosted service. Deployment requires HTTPS, durable data storage, and securely configured server environment variables. Do not put live credentials in the repository or use sample configuration as a security guarantee. See [PHONE_DEPLOYMENT.md](PHONE_DEPLOYMENT.md) for the historical phone-oriented setup guide; some of its steps describe earlier versions and should be checked against current security requirements before use.

For a test APK, see [APK_TESTING.md](APK_TESTING.md). The hosted site can update without replacing the APK, while Android launcher/native changes require a new build. The APK is a development artifact, not a Play Store-ready application.

## Direction of development

The near-term priority is to finish independently usable user accounts on different devices with separate Public connections, while maintaining a firm boundary from the current single-owner deployment. The next major work is secure onboarding and recovery, Android passkey integration, production-safe tenant migration, verified account ownership, read-only multi-user broker access, and comprehensive cross-user and backup isolation tests.

Beyond that foundation, EdgePilot's longer-term work includes stronger historical and live-data validation, research quality measurement, credible simulated execution and reconciliation, robust independent worker infrastructure, and production-grade risk enforcement. Any possible future live trading needs separately approved functionality, execution provenance, fee-aware accounting, broker-side safeguards, operational controls, and independent end-to-end testing; it is **not** unlocked by completing the multi-user stage.

## Documentation

This README explains **what EdgePilot is**, the capabilities of the system, its intended architecture, and the boundaries of the current development stage. Detailed implementation decisions and operating procedures are maintained separately:

- [CHANGELOG.md](CHANGELOG.md) — chronological changes, release validation, and limitations.
- [SECURITY.md](SECURITY.md) — private-instance authentication, secrets, and known security considerations.
- [TENANCY_MIGRATION_PLAN.md](TENANCY_MIGRATION_PLAN.md) — shared-user architecture, migration, and rollback prerequisites.
- [TENANT_PASSKEY_SHARED_PLATFORM_RUNBOOK.md](TENANT_PASSKEY_SHARED_PLATFORM_RUNBOOK.md) — identity and biometric/passkey integration requirements.
- [TENANT_PUBLIC_VAULT_RUNBOOK.md](TENANT_PUBLIC_VAULT_RUNBOOK.md) — user-owned encrypted Public credential lifecycle and inactive integration status.
- [TENANT_PUBLIC_READONLY_PREFLIGHT_RUNBOOK.md](TENANT_PUBLIC_READONLY_PREFLIGHT_RUNBOOK.md) — Public API authorization and read-only readiness boundaries.
- [TENANT_PUBLIC_DURABLE_SAFETY_REHEARSAL_RUNBOOK.md](TENANT_PUBLIC_DURABLE_SAFETY_REHEARSAL_RUNBOOK.md) and [TENANT_PUBLIC_OFFLINE_WORK_FENCING_RUNBOOK.md](TENANT_PUBLIC_OFFLINE_WORK_FENCING_RUNBOOK.md) — synthetic stop, lease, and work-stage safety testing.
- [APK_TESTING.md](APK_TESTING.md) — Android test build and installation information.

## Important disclaimer

EdgePilot is experimental software for portfolio visibility and research. Its analysis, simulations, strategy settings, and AI outputs are not investment advice or promises of returns. Historical backtests and simulated trades are not live results. Brokerage access and eventual use by multiple independent users remain subject to applicable provider agreements, security requirements, and law.

**The README describes the project. Version-by-version development history belongs in the [changelog](CHANGELOG.md).**
