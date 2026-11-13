# EdgePilot

**Android-first trading intelligence, portfolio research, and risk-controlled automation. Public source, private account infrastructure; still in controlled development.**

EdgePilot is a personal trading-intelligence platform designed to bring brokerage visibility, market discovery, historical strategy research, configurable risk limits, and eventually carefully controlled automated execution into one experience. Its principal integration is the [Public](https://public.com/) brokerage API. The application covers stocks and ETFs, investigates prediction-market opportunities, and is being designed with extensibility for additional asset types and strategies.

The goal is not simply to display prices or place trades. EdgePilot is intended to provide a traceable decision system: understand what the broker actually reported, distinguish observation from simulated results, evaluate a strategy against costs and risk, and refuse activity when data or authorization is uncertain.

> **Development status:** The next development version is **v0.2.83**, strengthening the already enabled single-owner, read-only Public portfolio response and cross-asset display. The existing paid Render service has v0.2.82 LIVE; no successful real broker balance/holdings response has yet been confirmed by the owner. All multi-user enrollment architecture, isolation and recovery capabilities remain intact. The v0.2.78 invitation-only coexistence backend is merged and passed PR and merged-main GitHub tests. The previously verified v0.2.77 public-repository CI safeguards are retained. The prior v0.2.76 encrypted-family recovery engine is merged but still dormant. The family archive and readiness code are dormant; no new members or trading permissions have been activated. The existing owner-facing application supports brokerage research and experimental Observe/Paper modes; **real brokerage order submission, autonomous live trading, and bank transfers remain disabled**. A separate, gated multi-user identity platform now includes invitation registration, individually encrypted Public connections, read-only account integration, and WebAuthn passkey endpoints. An Android-capable passkey account screen provides owner-scoped Public account discovery, verified read-only linking, sanitized portfolio views, an independently gated **inactive** monitoring-plan preview, and per-account watchlist editing that cannot activate any scanner, trade, or fund transfer. The account screen links to Public's verified signup and API-key instructions, and now supports user-confirmed replacement or disconnection of only the current user's encrypted Public credentials. Previously verified account bindings are disabled after either action. Android opens only the two Public-owned help pages outside its authenticated WebView. The account security screen also supports a user-confirmed password change that revokes every session belonging to that member without changing other users' sessions or Public keys. A separately gated device-session screen now lets members review their own active identity sessions and selectively sign out other sessions without affecting another user's identity. It deliberately does not fingerprint or identify physical devices. This is not forgotten-password recovery. The manual-only Android signing workflow has now produced a certificate-pinned, privately signed v0.19.17 test APK on November 10, 2026 (GitHub run #42888113943, attempt 2). The verification and upload passed after correcting a mismatched configured fingerprint; the owner reports installing the APK and logging into the legacy dashboard on one physical phone. Physical-device passkeys and Digital Asset Links remain unverified. Account-specific running workers and real multi-user acceptance are also incomplete. Offline cross-process tests recognize fail-closed SQLite lock contention while continuing to enforce the synthetic admission limits. See [CHANGELOG.md](CHANGELOG.md) for release history, and [DEVELOPMENT_CONTINUITY.md](DEVELOPMENT_CONTINUITY.md) for a durable new-conversation development checkpoint.

**v0.2.83 provider-contract hardening.** The backend now requires the Public `portfolio/v2` response's `accountId` to exactly match the previously verified provider account, and validates decimal quantities without assuming every asset is a stock share. The account UI shows exact USD cents, a manual retrieval time (not a market timestamp), and a no-open-positions message when appropriate; any bad snapshot refuses rather than displaying cross-account or stale data. This is a read-only improvement with no new provider access, paid service, live trade, worker or bank transfer. All completed multi-user infrastructure remains untouched. The actual first successful owner account balance/holdings display remains the acceptance gate. See [v0.2.83 portfolio compatibility](PUBLIC_PORTFOLIO_COMPATIBILITY_V0283.md).

**Single-owner portfolio activation — November 12, 2026.** The owner explicitly approved the first real read-only Public portfolio test. After v0.2.82 PR #108 and merged-main tests passed, the existing Render Starter service `edgepilot-private-h9tl` was updated with **only** `EDGE_SOLO_OWNER_PORTFOLIO_ENABLED=true` using environment merge mode. The same committed code `459a7c96eb08520e110a4d462bd780d149abc77e` redeployed as `dep-dbr4ss0u01pc73a6c3o0` and finished **LIVE/SUCCEEDED** at 23:41 UTC. Startup logs showed normal Gunicorn startup and no obvious startup failures. Existing paid disk, owner credentials, invitation settings and future multi-user work remained untouched. The application now allows the authenticated sole owner to request their **own** verified Public account's portfolio on demand; no order, automated trading, fund transfer or polling permission was enabled. **A real owner-device portfolio response has not yet been inspected**, so holdings, balance and Public response-contract correctness are pending acceptance. These operational notes are staged on a documentation branch to avoid an unnecessary second production redeploy.

**Current priority — one owner first (November 12).** The owner deferred testing the second Android/family account until the existing owner can complete identity login, verified Public linking, read-only portfolio visibility, trusted market research, risk controls and paper/observe workflows. **Do not delete or disable** any multi-user code, accounts, approved invitation flags or backups. The invitation system remains present, but **no real invitation will be issued while testing is deferred**. v0.2.82 adds an independently default-off `EDGE_SOLO_OWNER_PORTFOLIO_ENABLED` capability that will refuse access unless exactly one active owner identity exists, even though the family invitation infrastructure remains configured. Live Public balances have not yet been fetched through this new path. See [Single-owner development roadmap](SINGLE_OWNER_PRIORITY_V0282.md).

**Production activation checkpoint — November 12, 2026.** After the owner ran the operator-only v0.2.81 SSH preflight, its sanitized output reported `inspection:passed`, one independent owner, one verified encrypted Public account link, no registered member, inactive invitation gates, and no orders, workers or transfers. With the owner's prior approval for **invitation-only activation but not first token issuance**, the existing paid Render service was updated by merging exactly `EDGE_FAMILY_INVITE_COEXISTENCE_ENABLED=true`, `EDGE_TENANT_SIGNUP_ENABLED=true`, and `EDGE_PERMANENT_OWNER_INVITES_ENABLED=true` into its environment without replacing other variables. Its automatic redeploy at the unchanged v0.2.81 source commit succeeded (`dep-dbqug8mk1f9s73fd3410`); no app startup errors appeared in the inspected Render startup logs. **No invitation was issued, no second account was enrolled, and no real owner login or second-device acceptance was demonstrated by this operational check.** Existing legacy login and isolated data remain preserved by architecture, but actual legacy/session login must still be retested on a device. This operational note is prepared separately so a docs-only commit does not cause an unnecessary automatic Render redeploy.

**v0.2.81 sanitized SSH-only readiness command.** An explicitly invoked, default-off command lets the owner use their existing Render SSH connection to inspect the private owner/tenant storage and current safety gates. It returns aggregate status, requires no Public or archive key entry and refuses unsafe activation claims. Real owner login, provider network authentication, and independently held cloud backup remain separate acceptance gates. The connected Render API does not provide a shell, so a green GitHub build or Render deployment alone is **not** proof this audit ran on production. See [OPERATOR_FAMILY_READINESS_CLI_V0281.md](OPERATOR_FAMILY_READINESS_CLI_V0281.md).

**v0.2.80 first-invitation readiness (dormant).** The operator-only audit checks the existing private legacy and tenant SQLite files, the independently enrolled owner and decryptable verified Public account, safe discovery-only flags, absence of active invitations or existing members, and that registration is still disabled. It is read-only and returns aggregate nonsecret status, explicitly **not** permission to enable signup. No production inspection or invite has been performed. See [FAMILY_FIRST_INVITATION_READINESS_V0280.md](FAMILY_FIRST_INVITATION_READINESS_V0280.md).

**v0.2.79 owner invitation UI (development only).** The authenticated owner may generate a private one-hour, single-use invitation only when explicitly authorized by runtime feature gates. The account page hides this panel from members and when issuance is disabled, validates the response, and provides deliberate reveal/copy actions without persisting the code in URLs or client storage. The existing member signup form remains invitation-only. There is no live rollout or family enrollment yet, and all trade/transfer safeguards still apply. See [FAMILY_INVITATION_UI_V0279.md](FAMILY_INVITATION_UI_V0279.md).

**v0.2.78 family invitation coexistence (development only).** The owner approved developing a narrower opt-in path that permits existing owner-only, one-hour private invitations and one-use non-owner registration while keeping the original legacy login intact. A separate default-off feature gate requires the verified independent tenant database, authenticated owner and restricted Public account discovery; it refuses passkeys, worker automation, portfolio reads, monitoring, live orders and tenant-only retirement. The 10-user cap extends to this mode. No source merge activates signup or issues an invitation; production enrollment still needs separately approved backup and two-device acceptance. See [FAMILY_INVITE_COEXISTENCE_V0278.md](FAMILY_INVITE_COEXISTENCE_V0278.md).

**v0.2.76 encrypted multi-member recovery rehearsal (dormant).** Building on the verified v0.2.75 read-only audit, a separate engine-only recovery utility now rehearses an AES-256-GCM encrypted backup and authenticated RAM-only restore of two to ten independent private users, removing live session hashes, unused invitation hashes and pending passkey challenges **only from the snapshot**. No web route or operator CLI is enabled, no live database is modified, and the private owner-only v0.2.74 archive remains intact. The full family archive needs both the separately held recovery key and original Fernet credential key; it has not been made or copied from production and does not authorize member signup, Public portfolio, workers, live orders or transfers. See [PRIVATE_FAMILY_ENCRYPTED_RECOVERY_V0276.md](PRIVATE_FAMILY_ENCRYPTED_RECOVERY_V0276.md).

**v0.2.75 family-account recovery readiness (dormant).** A new source-only operator audit checks up to ten independently encrypted private-family identities, distinct member Public credentials, SQLite integrity, password identity pairing and account linkage without modifying databases, making broker requests or writing an archive. It rejects shared Public API secrets and unsafe flags, and returns only aggregate nonsecret status. Current owner backup remains single-owner: a multi-member encrypted restore archive and real second-user acceptance are still outstanding. No Render feature flags, registration, workers, orders or transfers are changed by this code. See [FAMILY_RECOVERY_READINESS_V0275.md](FAMILY_RECOVERY_READINESS_V0275.md).

**v0.2.74 recovery after first verified independent Public account (operator-only).** The owner has independently confirmed the new identity has a saved encrypted Public API connection, a provider-discovered brokerage account and a linked verified account. The first-owner backup predates this credential, so this milestone adds a new default-off private backup snapshot, AES-256-GCM and authenticated tmpfs restoration. It includes encrypted credentials but strips active session hashes from the **snapshot only** and verifies that the original Fernet key can recover secrets without exposing them. No activation or trading flags change. On November 12 the owner completed the operator-only encrypted snapshot and authenticated restore on the existing paid Render service, copied the archive to protected Android Termux storage, uploaded it to the private Drive backup folder, then downloaded it again and verified the SHA-256 matches the source. This establishes byte-for-byte off-service custody of this specific archive, **not** a production disaster-recovery restore or independent credential-key recovery. The archive still requires both the separately held offline recovery key and the original Fernet credential key to restore saved Public credentials. No live multi-member acceptance has occurred. See [LINKED_OWNER_RECOVERY_V0274.md](LINKED_OWNER_RECOVERY_V0274.md).

**Live provider-discovery-only rollout (November 12, 2026 UTC).** After successful PR #95 and merged-main GitHub tests, the owner-approved feature flags were enabled through a **merge-only** update of the existing paid Render Starter environment; deployment `dep-dbqjf4ec6qcc73fhamrg` of v0.2.73 `b40874e` was confirmed LIVE. The new user account can save its own Public API secret and request a verified account list, but it **cannot fetch portfolio balances, trade, move funds, invite users or access legacy owner credentials**. No user-entered Public key or real Public account discovery has been verified yet. See [PUBLIC_DISCOVERY_ONLY_V0273.md](PUBLIC_DISCOVERY_ONLY_V0273.md).

**v0.2.73 guarded independent Public account discovery pilot (default-off).** An explicit discovery-only flag permits safely encrypted Public API secrets, identity-scoped provider account listing and verified linking while the balance/portfolio endpoint remains an unconditional 404 and the corresponding button stays hidden. Synthetic two-user tests reject cross-owner reads and verify no legacy credential migration, Public order endpoint, or transfers. This version is separate from *activation*: the existing paid Render service remains unchanged until CI passes and the already-approved narrow flags are intentionally enabled. See [PUBLIC_DISCOVERY_ONLY_V0273.md](PUBLIC_DISCOVERY_ONLY_V0273.md).

**v0.2.72 validated dual-auth coexistence and rollback boundaries.** The owner reports successful Android HTTPS login/logout as `Belenos-Owner` and successful original legacy dashboard login on the same paid Render instance. A new synthetic integration test now locks in this exact auth-only feature profile: two separate identity users on their own tenant SQLite database cannot inherit the original owner token, and legacy login cannot acquire identity sessions. Sign-out is scoped, with signup, Public broker reads, passkeys, global workers and orders off. See [DUAL_LOGIN_ISOLATION_ACCEPTANCE_V0272.md](DUAL_LOGIN_ISOLATION_ACCEPTANCE_V0272.md).

**Controlled HTTPS owner-login rollout (November 11–12, 2026).** After the independently verified `Belenos-Owner` Argon2id password and encrypted off-service tenant-owner archive, the owner approved *authentication-only* deployment on the existing paid Render service. The deployment of commit `9381b3f` is confirmed **live** with independent identity/database preparation enabled and `EDGE_PERMANENT_TENANTS_ONLY=false`. Legacy token-based login remains available; all tenant Public account features, invitation signup, passkeys, global worker, autonomous orders and bank transfers remain disabled. **A real Android HTTPS login and session/logout test have not yet been independently verified.** See [CONTROLLED_OWNER_HTTPS_LOGIN_V0271.md](CONTROLLED_OWNER_HTTPS_LOGIN_V0271.md).

**v0.2.71 read-only first-owner Argon2id password proof (dormant).** After the owner bootstrap and checksum-verified encrypted backup have been secured off Render, a new trusted-console-only tool validates that the private owner's saved password matches its Argon2id hash, without creating sessions, changing passwords, enabling public login routes, contacting Public or touching the original owner data. The report explicitly leaves real HTTPS owner login unverified. See [FIRST_OWNER_PASSWORD_PROOF_V0271.md](FIRST_OWNER_PASSWORD_PROOF_V0271.md).

**v0.2.70 first-owner tenant backup and restore (dormant).** The legacy migration backup expects an original single-user schema and cannot save the newly enrolled tenant identity. A dedicated console-only tool now creates a private SQLite snapshot on RAM, encrypts with AES-256-GCM using the existing phone-held backup key, tests authenticated temporary restoration, and refuses active workers, unsafe files and overwrites. The encrypted file still must be copied off Render; no automatic deployment backup or active login is implied. See [PERMANENT_FIRST_OWNER_BACKUP_V0270.md](PERMANENT_FIRST_OWNER_BACKUP_V0270.md).

**v0.2.69 mobile-safe first-owner bootstrap (default-off).** The protected one-time owner-console flow now rejects blank/mismatched/short hidden password entries before touching SQLite, accepts the required *nonsecret* authorization phrase through a visible prompt, and displays only fixed sanitized engine refusal reasons. This addresses Android Termux hidden-input confusion after the real production tenant database passed independent read-only checks. The engine's owner-only atomic transaction, existing login and production runtime flags remain unchanged. See [FIRST_OWNER_MOBILE_INPUT_V0269.md](FIRST_OWNER_MOBILE_INPUT_V0269.md).

**v0.2.68 safe private storage diagnostic identifiers (default-off).** The one-time tenant database initializer now reports the fixed internal stage at which a guarded manual attempt was denied, without revealing credentials, environment contents, database records, paths or raw OS errors. It still refuses to overwrite existing tenant storage, does not bypass safeguards, and cannot activate user accounts. This helps troubleshoot a real paid-disk initialization refusal after separate dry-run checks passed. See [PRIVATE_STORAGE_PHASE_DIAGNOSTICS_V0268.md](PRIVATE_STORAGE_PHASE_DIAGNOSTICS_V0268.md).

**v0.2.67 staged owner-scoped Public pilot gate (default-off).** A newly opt-in permanent runtime policy removes a preparation-only restriction that otherwise prevented eventual identity-scoped Public credential vault, account discovery and read-only portfolio views on the existing paid tenant database. Every feature still needs its own separate flag; the pilot requires a pre-enrolled independent owner, secure existing tenant file and stable encryption key, and excludes live trading, workers and open signup during coexistence. No live pilot is activated on Render. See [PERMANENT_READONLY_PILOT_V0267.md](PERMANENT_READONLY_PILOT_V0267.md).

**v0.2.66 tenant-only lockout safeguard (default-off).** Retiring legacy owner APIs now requires a pre-existing private tenant database with exactly one active, independently password-enrolled owner identity and completely paired members. Missing, duplicated, unpaired, or unsafe owner storage fails startup before routing can switch. This prevents a mere environment toggle from silently disabling the only working owner login, but physical login/recovery still requires human verification. The switch remains inactive on Render. See [PERMANENT_TENANT_OWNER_LOCKOUT_GUARD_V0266.md](PERMANENT_TENANT_OWNER_LOCKOUT_GUARD_V0266.md).

**v0.2.65 owner readiness inspection (not run on production).** A new disabled-by-default, console-only read-only audit examines the prepared separate tenant database before and after the first-owner bootstrap. It verifies private isolation, SQLite integrity, zero or one complete owner identity, and unpaired/duplicate member refusal while returning only aggregate nonsecret status. A successful report never claims an actual identity login, broker verification or authority to retire legacy APIs. See [PERMANENT_OWNER_READINESS_V0265.md](PERMANENT_OWNER_READINESS_V0265.md).

**v0.2.64 read-only owner key recovery check (not run on production).** A private console-only inspection can test a separately entered recovery copy of EDGE_CREDENTIAL_KEY against the running server's Fernet vault key and authenticate the saved Public ciphertext without showing credentials or changing owner data. The key must be secured independently from the database archive and owner access token. No production verification, migration or activation is implied by shipping this dormant code. See [OWNER_VAULT_RECOVERY_PROOF_V0264.md](OWNER_VAULT_RECOVERY_PROOF_V0264.md).

**v0.2.63 isolated storage initializer (not run on production).** A new gated, console-only, single-use preparer can create the previously missing empty, separate tenant SQLite database on the existing paid /data disk. It verifies the legacy DB read-only, stages an empty private identity schema, and atomically publishes with no overwrite or legacy ciphertext copy. This source/deployment change does not actually create any tenant DB or enable identities. A verified off-service backup, stable credential encryption key and owner recovery remain mandatory operator checks. See [PRIVATE_TENANT_STORAGE_INIT_V0263.md](PRIVATE_TENANT_STORAGE_INIT_V0263.md).

**v0.2.62 read-only production cutover preflight.** A separate manual-only security inspection checks the legacy owner database and independently authenticated tenant database on the existing paid disk for privacy, integrity, expected schemas and separation. It does not expose credentials or authorize migration, and it cannot attest to an external encrypted backup or real account recovery. No paid services or Render feature switches changed. See [PERMANENT_CUTOVER_PREFLIGHT_V0262.md](PERMANENT_CUTOVER_PREFLIGHT_V0262.md).

**v0.2.61 private family invitations.** The independent EdgePilot owner account can, when deliberately enabled after recovery, issue one-use one-hour invitations for up to **10 total private users**, including the owner. Each invited user becomes a member with separate login and independently scoped data, not an additional owner, broker or trading authority. Rate limits and a transactional cap prevent races; every request requires the trusted owner's identity session and CSRF, not the legacy token. The feature remains off on Render, and no accounts or invitations have yet been issued. See [PERMANENT_PRIVATE_INVITATIONS_V0261.md](PERMANENT_PRIVATE_INVITATIONS_V0261.md).

**v0.2.60 independent initial owner account preparation.** A restricted, console-only one-time bootstrap can prepare the first independently authenticated EdgePilot owner account in the separate tenant DB on the already paid disk. It requires a private existing DB, explicit operator opt-in, unique password, atomic audit and absence of any previous tenant identity. It does not accept the legacy owner token as identity, move brokerage holdings or credentials, or open a public bootstrap route. Deployment does not run it automatically; fresh production backup and tested recovery, operator console access and intentional feature activation are still required. See [FIRST_PERMANENT_OWNER_BOOTSTRAP_V0260.md](FIRST_PERMANENT_OWNER_BOOTSTRAP_V0260.md).

**v0.2.59 legacy retirement and permanent mobile passkey preparation.** A separate **default-off** tenant-only routing policy now allows the single-owner API and dashboard to be disabled after the original owner is safely enrolled and recovered as an independent member. It blocks old session/login/global brokerage and worker routes rather than letting new identities inherit owner access. Another independently gated policy can accept the exact certificate-pinned production Android signed-app WebAuthn origin alongside the HTTPS site origin, but only after strict tenant-database, account-login and host verification. Both are inactive in production; no migration, real broker connection, new cost, order or transfer is enabled. See [PERMANENT_TENANT_ONLY_RUNBOOK_V0259.md](PERMANENT_TENANT_ONLY_RUNBOOK_V0259.md).

**v0.2.58 architecture checkpoint — existing paid Render backend.** The approved permanent multi-user direction reuses the **already paid** `edgepilot-private-h9tl` Render Starter web service and its existing 1 GB persistent `/data` disk, rather than adding another paid service. The owner data and encrypted credentials remain in `/data/edgepilot.db`; a **separate, opt-in** `/data/edgepilot-tenants.db` is now wired to every tenant identity, passkey, session and user-scoped account store, preserving legacy data while isolation is tested. The initial unfinished v0.2.58 branch was strengthened with strict pathname/permission guards, disabled-worker and disabled-brokerage checks, and offline separate-database Flask startup tests. **This is cutover preparation, not a completed production activation or owner-data migration**: the shared-database flag is not enabled on Render, user accounts have not been migrated, and real brokerage operations, live trading and transfers remain disabled. The existing separate Free staging service remains disposable. Full operational sequence: [SHARED_PAID_BACKEND_CUTOVER_V0258.md](SHARED_PAID_BACKEND_CUTOVER_V0258.md).

The shared-user development path now includes strict owner-scoped account watchlists:
each member can save a validated stock-symbol list for a linked account without
touching another account or starting any monitor. The preview and editing APIs
are separately disabled by default. See
[TENANT_WATCHLIST_EDIT_RUNBOOK.md](TENANT_WATCHLIST_EDIT_RUNBOOK.md) for the
security and operational requirements.

**Independent device-session security.** An EdgePilot member can review active, time-limited identity sessions and selectively revoke another session belonging to the same member. A verified identity cookie and CSRF are required; only opaque, non-bearer session handles and timestamps are displayed. Current-session logout and all-device password-change logout remain separate. No device fingerprints or locations are collected, and these controls cannot grant access to the legacy owner or Public brokerage functions. See [TENANT_SESSION_CONTROLS_RUNBOOK.md](TENANT_SESSION_CONTROLS_RUNBOOK.md) for security boundaries.

**Stable Android identity preparation.** The standard debug APK continues to compile without any sensitive signing material. A separate, manually initiated GitHub Actions workflow now signs private test APKs using a long-lived operator-owned keystore and its independently pinned SHA-256 certificate fingerprint. On November 10, 2026, its first attempt stopped safely on a mismatched expected fingerprint, and the corrected retry passed compilation, Android signature verification, certificate pinning, package/version checks and artifact upload. It cannot run automatically from pull requests and uploads only verified APKs. The private v0.19.17 artifact expires after seven days. On November 10, 2026 the owner reported installing that downloaded APK on their existing Android phone and successfully signing in using their previously verified legacy owner token. This is an owner-reported real-device **legacy login smoke test**, not independent verification of the installed certificate, Digital Asset Links, tenant passkeys or two independent EdgePilot users. This lays groundwork for Android Digital Asset Links and device passkeys without enabling authentication or brokerage features in production. See [ANDROID_PRIVATE_SIGNING_RUNBOOK.md](ANDROID_PRIVATE_SIGNING_RUNBOOK.md) for the signing and two-device verification requirements.

**Android website-association configuration (November 10, 2026).** After an owner-reported successful stable-signed APK install/login, the owner checked `https://edgepilot.belenoscreations.biz/.well-known/assetlinks.json` and saw the expected fail-closed `{"error":"Not found"}` response. The public X.509 certificate was independently extracted from the GitHub-signed APK and matched between its Android v2 and v3 signature blocks. Only the `EDGE_ANDROID_CERT_SHA256` environment variable was then merged into the existing Render service and deployment `dep-dbppig56e07s73b34d1g` was verified **live**. The user subsequently reloaded that exact HTTPS URL on their Android phone and supplied a screenshot showing the correct JSON array, credential-sharing relationship, `com.edgepilot.mobile` package name and configured signer fingerprint. This verifies public website response content as observed on that phone, but not Android OS Digital Asset Links credential association or passkey registration/authentication; tenant passkeys remain default-off. No login token, broker credentials, order/transfer flags or other production settings were changed.

**Real cryptographic tenant-passkey rehearsal.** The v0.2.41 tests generate two local, temporary P-256 ES256 WebAuthn authenticator keypairs and exercise actual CBOR attestation plus signed assertions through the real Flask identity/passkey HTTP routes and unmodified py_webauthn verification. They test independent identities, HTTPS origin and user verification, tampered signatures, challenge replay, counter rollback, revocation and prevention of legacy owner privilege inheritance. Unlike earlier stubbed passkey tests, the cryptographic verifier runs for real, but this is **fully offline synthetic testing**, not proof of Android Credential Manager, an actual biometric prompt, OS-level association or two physical devices. Production passkey, tenant and brokerage flags remain disabled. See [WEBAUTHN_REAL_CRYPTO_ACCEPTANCE_RUNBOOK.md](WEBAUTHN_REAL_CRYPTO_ACCEPTANCE_RUNBOOK.md).

**Isolated, side-by-side Android passkey test preparation.** Version 0.2.42 adds an optional Android staging build with a **different package name** (`com.edgepilot.mobile.staging`) and visible **EdgePilot Staging** label, so biometric test installations cannot replace the owner's currently working permanently signed app. Staging only accepts a separately supplied, owned HTTPS hostname at compile time; absent input points to a deliberately unusable `.invalid` hostname. A distinct manual-only GitHub workflow can sign the staging package using the existing private signing certificate, after the operator provisions an isolated host. The backend refuses to initialize isolated staging if its RP, package, ephemeral database, credential, worker or identity configuration is unsafe, and serves staging-only Digital Asset Links only after those checks pass. **No additional Render service/domain is created and no dormant tenant/passkey/Public flag is enabled on production.** The staging APK has not been signed, deployed or installed. See [ANDROID_ISOLATED_STAGING_RUNBOOK.md](ANDROID_ISOLATED_STAGING_RUNBOOK.md).

**Encrypted tenant recovery validation.** EdgePilot now includes a strictly offline, synthetic-only SQLite backup/restore rehearsal for the future shared backend. It makes an authenticated encrypted test archive entirely within verified Linux `/dev/shm`, restores to a new restricted test file, checks database relationships and two-user account separation, and deliberately invalidates all pre-restore login sessions, passkey challenges, invitations and worker leases. It also quarantines every restored Public connection, linked account, and registered passkey so that an older backup cannot revive a revoked API key or authenticator. It is **not a production backup service**, cannot access Render's live database, and does not grant trading or broker access. A real backup policy still requires separate key custody, offsite storage, retention, disaster authorization and restore testing. See [TENANT_BACKUP_REHEARSAL_RUNBOOK.md](TENANT_BACKUP_REHEARSAL_RUNBOOK.md).

**Integrated two-user backend rehearsal.** EdgePilot now tests the full *synthetic* lifecycle for two independent users sharing one HTTPS service: invitation enrollment, separate secure identity sessions, passkey registration options, individual encrypted fake Public keys, fake broker account discovery, verified read-only linking, portfolio isolation, per-account watchlists and inactive monitoring previews, plus selective session revocation. Its test provider rejects every unlisted endpoint, preventing the harness from reaching real Public APIs or submitting orders. **This is not yet two physical devices, native biometrics or two real Public accounts.** The final acceptance objective remains open. See [TWO_DEVICE_SYNTHETIC_ACCEPTANCE_RUNBOOK.md](TWO_DEVICE_SYNTHETIC_ACCEPTANCE_RUNBOOK.md).

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

## Free-first intelligence architecture — staged implementation

EdgePilot's approved three-layer research strategy is designed for the
private owner, up to ten independently funded private users, and possible
future distribution without rebuilding its core. **Layer 1** is permission-
and freshness-checked provider observations and zero-paid-AI calculations.
**Layer 2** is chronological validation, after-fee/slippage expected-value
scenarios and measured risk-adjusted paper-forward performance.
**Layer 3** is optional explanations/context from AI, constrained by consent,
user-specific budgets and independently secured credentials. AI text cannot
authorize orders, move money or replace verified price facts.

The v0.2.43 code adds a reusable **provider-neutral research interface**
requiring explicit source rights, verified asset coverage, UTC timestamps,
bid/ask, market state and staleness checks. It refuses future-dated or crossed
books, disallows assumed cache/redistribution rights, and makes midpoints
non-executable. Prediction-market scenarios require quoted ask, book depth,
time to expiry, settlement descriptions and all explicitly supplied costs.
An externally claimed chronological held-out probability is an unverified
input—not a calibrated success claim. Free deterministic momentum and
realized-dispersion descriptions are available with no AI requests.

**Implementation status:** This is a locally tested module, not yet a
live data feed, autonomous scanner, scheduled worker, complete prediction
probability estimator or proven trading advantage. Crypto and 15-minute
market access require their own independently confirmed provider rights
and metadata. User-configurable $0 paid AI is a supported product goal;
actual brokerage/data service licensing and continuous operation are not
implied by the existence of this layer. See
[FREE_FIRST_RESEARCH_RUNBOOK.md](FREE_FIRST_RESEARCH_RUNBOOK.md).
Legacy optional AI accounting and future member-owned BYOK budgets will be
improved in separate gated milestones.

**Optional AI is budgeted separately from free research.**
The on-demand legacy owner AI assistant is disabled by default and
never places orders or transmits credentials. v0.2.44 replaces its
previous fixed-$0.20 request hold with an SQLite-serialized,
**model-aware, token-informed** preflight estimate using manually
verified public Standard API text rates for an allowlist of low-cost
OpenAI models. Estimates and reconciled token usage are stored in
integer micro-US-dollar units, with conservative pending/uncertain
holds for timeouts or missing provider usage, no automatic retries,
UTC monthly rollovers and preservation of historical reservations.
The monthly dashboard displays remaining *local* budget, estimated
token spend, blocked requests, and price-check dates. The default
owner budget remains unchanged and **AI remains off** until explicitly
enabled by the owner. Rate snapshots require periodic re-verification
and fail closed when stale; this is **not a provider-side billing cap**.
Separate per-user AI funding and encrypted BYOK remain a future
gated milestone, not a capability of the current owner login.
See [AI_COST_ACCOUNTING_RUNBOOK.md](AI_COST_ACCOUNTING_RUNBOOK.md)
for priced models, assumptions, security boundaries and tests.

## Market data, research, and accounting

**Public connection management.** A signed-in user can choose one of their own encrypted Public connections and explicitly replace its secret key or disconnect it. Both are confirmation-required, account-scoped changes. Replacing a key disables previously verified linked-account records until they are independently reverified; disconnecting EdgePilot does not close the Public brokerage account or revoke keys at Public. Identity and CSRF remain valid only when verified in the same database write transaction as these changes, and the UI removes stale balances, holdings and connection data after a change. All these features remain separately default-off until a controlled multi-user activation. See [TENANT_PUBLIC_CONNECTION_MANAGEMENT_RUNBOOK.md](TENANT_PUBLIC_CONNECTION_MANAGEMENT_RUNBOOK.md).

**Public connection onboarding.** Members who do not yet have a Public account can open Public's official signup from EdgePilot's account screen. Existing Public customers receive a direct link to the official API quickstart and in-product guidance to generate a **secret API key** in Public's Settings > Security > API. EdgePilot asks users to return and enter that key only into their own secure account form. The Android wrapper opens these exact two help pages outside its authenticated WebView; it will not silently navigate to arbitrary external hosts or attach credentials to URLs. This guided enrollment is separate from EdgePilot identity registration and does not grant broker authorization or activate trading.

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

**Per-user AI funding and privacy (in development).** EdgePilot's
future shared backend is designed for a no-paid-AI mode, independently
funded **bring-your-own-provider-key** mode, and a reserved managed-credit
option that cannot be activated until billing is separately approved.
The new v0.2.45 **dormant** per-member AI vault stores each member's
encrypted provider key with a dedicated AI encryption key, user-bound
ownership metadata, independent analysis-depth preference and precise
monthly local budget. Ten-member synthetic tests exercise concurrent,
cross-user-isolated admissions, CSRF/session revocation and encrypted key
rotation; a friend cannot use the owner's AI credential by default.
The managed-credit mode is refused, not sold. No HTTP API or live OpenAI
provider execution is connected to this vault yet: actual BYOK setup,
commercial tiers, credit purchases and real account billing remain
disabled. See [TENANT_AI_BYOK_BUDGET_RUNBOOK.md](TENANT_AI_BYOK_BUDGET_RUNBOOK.md)
for limitations and acceptance.

**Licensed public-research reuse (dormant v0.2.46).** A small, bounded
internal cache now demonstrates how ten independently authenticated members
could reuse one **non-personal** technical feature without repeating market
computations or making AI calls. It enforces independent provider rights to
analyze, cache, redistribute and cover the instrument, rejects stale/future
and malformed quote evidence, and requires an independently linked Public
account plus that member's own stock/ETF watchlist before reading a feature.
The feature is a reference-only quoted spread, **not an executable quote,
trading recommendation, calibrated prediction or evidence of profits**.
Crypto and 15-minute prediction per-user previews stay unavailable until
actual coverage, rights and account entitlements can be confirmed. No
provider rights are claimed to be approved merely because synthetic tests
pass. The cache is not wired to real providers, HTTP routes, a worker,
paid AI, or production flags. See [SHARED_RESEARCH_CACHE_RUNBOOK.md](SHARED_RESEARCH_CACHE_RUNBOOK.md).

**Cost-aware continuous-intelligence design (dormant v0.2.47).**
A quota-aware, provider-neutral planner can now produce a research-only
*proposal* to sample verified market data more efficiently. It checks
current analysis and coverage rights, per-member entitlements, explicit
provider quotas, backoff, known market sessions, freshness and prediction
contract expiry. When redistribution rights and central access are
affirmatively verified, ten eligible users may be represented by one
shared prospective market-data request; otherwise any proposed reads
remain independently authorized and quota-isolated per member.
There is no blanket promise of free real-time data or universal 15-minute
market access. This planner does not call a data provider, start a scanner,
charge AI tokens, authenticate a live user or authorize a trade.
See [ADAPTIVE_RESEARCH_PLANNER_RUNBOOK.md](ADAPTIVE_RESEARCH_PLANNER_RUNBOOK.md).

**Evidence-first optional AI evaluation (dormant v0.2.48).**
A new offline, matched forward-study evaluator can compare a zero-paid-AI
forecast baseline with an independently validated AI-assisted model on
identical binary outcomes, while attributing *measured* optional AI cost
in microUSD. It rejects future information, unverified settlements,
unknown AI usage, mixed event definitions and account-private input.
The resulting Brier-score difference is a **description of forecast
quality, not a trading profit, causal AI advantage or guaranteed
risk-adjusted return**. It cannot spend tokens, ask a model, submit
orders or approve automation. Real provider outcomes, true forward
evidence and net-after-trading-cost validation are still necessary.
See [PAIRED_RESEARCH_AUDIT_RUNBOOK.md](PAIRED_RESEARCH_AUDIT_RUNBOOK.md).

**Future commercial entitlement separation (dormant v0.2.49).**
The shared-identity architecture now keeps an independently authenticated
member's *requested* Free/Plus/Pro/Custom concept distinct from granted
capabilities, BYOK API bills, local AI limits, market-data rights and
brokerage actions. Selecting a proposed tier does not activate it: all
effective tiers remain Free, no subscription or payment can be processed,
and no premium feature can be unlocked. Names and possible pricing are
exploratory, not announced plans. Any eventual commercial release still
needs verified licensing, unit economics, legal/policy and Google Play
review, including the restrictions that may affect 15-minute YES/NO
prediction-market functionality. See
[TENANT_TIER_INTENT_RUNBOOK.md](TENANT_TIER_INTENT_RUNBOOK.md).

**AI overage attribution (dormant v0.2.50).**
When trusted measured AI usage exceeds a member's conservative local
preflight reservation, the isolated cost ledger no longer treats the
request as a normally completed cheap call: it records the larger
amount as uncertain attributed cost and reduces that member's remaining
local budget accordingly. Missing actual usage continues to hold its
reservation. Other members' budgets and keys remain separate.
This protects local accounting in synthetic tests but **does not
establish a provider-enforced spending cap, actual AI execution,
completed billing integration or proof of research usefulness**.
See [TENANT_AI_OVERAGE_RECONCILIATION_RUNBOOK.md](TENANT_AI_OVERAGE_RECONCILIATION_RUNBOOK.md).

**Isolated Android passkey staging preparation (v0.2.51).**
A deliberately **not deployed** Render service proposal now specifies a
separate staging hostname, independently installed Android package and
disposable test database, with no owner login token, Public credential,
payment, AI provider secret or trading access. It is checked by
fail-closed automated tests that reject production service references,
auto-deploy, substituted paid plans and unsafe environment settings.
This preparation does **not** create a new Render service, spend money,
configure DNS, install a staging APK or prove passkeys work on physical
Android phones. Render Free compute has usage-based overage exposure and
an ephemeral filesystem; final hosting/billing review and separate
approval of any additional charges remain required. See
[STAGING_RENDER_COST_APPROVAL_RUNBOOK.md](STAGING_RENDER_COST_APPROVAL_RUNBOOK.md).

**Separate private Android staging environment.** A new **Free** Render
staging service now runs independently of the owner's existing
EdgePilot application, with its own disposable test data, an independently
verified public Android signing certificate and no brokerage secrets,
trading, fund transfers, paid AI or background trading workers.
It uses a distinct Android package that will install side by side
with the working owner app. This is a backend **startup milestone**:
the staging custom hostname still requires a DNS record and HTTPS
verification, the manual staging APK has not been signed or installed,
and physical passkeys and independent live Public accounts have
not been accepted. Render Free's ephemeral storage is unsuitable for
durable brokerage identities. See
[STAGING_RENDER_LIVE_CHECKPOINT.md](STAGING_RENDER_LIVE_CHECKPOINT.md)
for what is verified and what still needs an operator action.

**Android staging signed build safety.** The private staging APK is
built through a manual-only, signed GitHub workflow. After a failed
first attempt on a phone due to an accidental trailing hostname space,
the workflow now normalizes only surrounding whitespace, then
strictly validates the owned staging host and builds against that
same validated value. The rejected run did not produce a signed APK;
a new authorized manual workflow run and real device verification
remain required.

**Staging account activation for two private test users.** The
isolated Android staging homepage now opens EdgePilot Accounts directly,
rather than the legacy personal-dashboard token login. A separately
key-protected operator screen supports exactly two one-time invitations
for disposable, synthetic member identities. Public brokerage and
orders remain disabled, and production's owner dashboard is unchanged.
The operator key is never checked into source or included in an APK;
its SHA-256 digest is configured only in the Free staging backend.
The signed staging APK, physical biometric sign-in and durable two-user
Public accounts are **not** completed by this software alone. See
[STAGING_OPERATOR_INVITATIONS_RUNBOOK.md](STAGING_OPERATOR_INVITATIONS_RUNBOOK.md).

**Android staging APK ready for installation (November 11, 2026).**
The separate `EdgePilot Staging` Android package is now successfully
assembled and permanently signed through a manual GitHub Actions run
[#43013142566](https://github.com/BelenosCreations/edgepilot-personal/actions/runs/43013142566).
The archived APK artifact was independently downloaded and inspected:
its package is `com.edgepilot.mobile.staging`, version
`0.19.17-staging`, the embedded hostname is the separate staging
domain, and the Android v2 certificate matches the approved public
signing fingerprint. The production `com.edgepilot.mobile` package is
not replaced, and no real trading credentials are included. The test
APK has **not yet been installed or exercised on real phones**;
WebAuthn/biometric acceptance and independent Public accounts remain
open. The staged server still uses disposable synthetic storage.

**Isolated Android passkey compatibility.** Device testing exposed a
registration verification error despite a successfully authenticated
synthetic member. Android's signed-app WebAuthn origin can differ from
a website HTTPS origin; EdgePilot's isolated staging verifier now
supports only those two **explicitly pinned** origins, using the
independently verified public signing certificate. Production remains
website-origin-only, and biometric success on an actual phone
still requires retesting after isolated staging deployment.
Nothing in this change enables real Public accounts or trading.

**Passkey status and management in the account screen.**
EdgePilot's signed-in account view now verifies the number of active
passkeys belonging to the member rather than always prompting to add
another. When enrolled, it displays a confirmed passkey-enabled state
and count; the Account Security section lists registration dates and
offers optional additional passkeys or per-passkey revocation. Removing
a passkey revokes all active sessions for only that EdgePilot member;
password authentication remains available. This server-side removal
does not erase the stored passkey in an external credential manager.
No device-identifying information or biometrics are stored or
invented in the list. Brokerage and autonomous execution remain
disabled on isolated staging. The two-physical-phone, independent
Public account acceptance is still subject to real-device tests
and durable infrastructure.

**Verified signed Android staging passkey test.** A test user on the
installed Android staging application successfully completed
passwordless passkey enrollment and then reported successfully
signing out and back in via their credential provider. The new
account screen also correctly switched from “Set up biometric
login” to “Passkey login enabled — 1 passkey registered.”
This is a user-confirmed **one-device synthetic identity test**,
not yet the two-separate-phone acceptance target.

**Persistence is the next gated milestone.** Render Free staging uses
an ephemeral SQLite database, which already reset both synthetic
accounts during a deployment. A [staging persistence decision and
cost runbook](STAGING_PERSISTENCE_DECISION_V0257.md) describes a
separate paid web instance and disk option (approximately $7.25
additional per month before overages), alternatives and migration
checks. No paid upgrade or real broker data has been authorized.
The existing production owner app and backend remain separate.

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
- **Authenticated sessions:** The owner-facing application uses HTTPS, secure server-side sessions, and same-origin/CSRF protections for protected operations. The separately gated multi-user sessions cannot authorize legacy owner endpoints. Members can securely change a known password and invalidate all their own active sessions; forgotten-password recovery is a separate, unfinished requirement.
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
- [TENANT_PASSWORD_CHANGE_RUNBOOK.md](TENANT_PASSWORD_CHANGE_RUNBOOK.md) — password security, all-device session revocation, and recovery limits.
- [TENANT_PUBLIC_READONLY_PREFLIGHT_RUNBOOK.md](TENANT_PUBLIC_READONLY_PREFLIGHT_RUNBOOK.md) — Public API authorization and read-only readiness boundaries.
- [TENANT_PUBLIC_DURABLE_SAFETY_REHEARSAL_RUNBOOK.md](TENANT_PUBLIC_DURABLE_SAFETY_REHEARSAL_RUNBOOK.md) and [TENANT_PUBLIC_OFFLINE_WORK_FENCING_RUNBOOK.md](TENANT_PUBLIC_OFFLINE_WORK_FENCING_RUNBOOK.md) — synthetic stop, lease, and work-stage safety testing.
- [APK_TESTING.md](APK_TESTING.md) — Android test build and installation information.

## Important disclaimer

EdgePilot is experimental software for portfolio visibility and research. Its analysis, simulations, strategy settings, and AI outputs are not investment advice or promises of returns. Historical backtests and simulated trades are not live results. Brokerage access and eventual use by multiple independent users remain subject to applicable provider agreements, security requirements, and law.

**The README describes the project. Version-by-version development history belongs in the [changelog](CHANGELOG.md).**

## Public GitHub source, private operational data

On November 12, 2026, the source repository became **public** following reviewed PR #102 and a passing historical credential-pattern preflight, application tests, unsigned Android test build, and merged-main tests. **Public GitHub visibility does not publish Render databases, user accounts, brokerage credentials, offline recovery keys, or Android signing material.** The verification uses heuristics and does not replace ongoing reviews of logs, artifacts, public history or provider access.

The development workflows use standard GitHub-hosted runners, avoid redundant full-history scans for every small change, and reduce unsigned PR APK artifact retention. Manual signed Android workflows remain constrained to the trusted main branch, but their resulting artifacts should not be assumed private merely because the workflow name says *private*.

See [Public repository safeguards](PUBLIC_REPOSITORY_READINESS.md) for current controls and remaining operator checks. Publication does not enable new family users, Public portfolio access, live or autonomous trading, bank transfers, paid hosting, or public distribution of account data.
