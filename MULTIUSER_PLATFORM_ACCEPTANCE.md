# EdgePilot multi-user platform — approved architecture and acceptance gate

## Product scope (approved 2026-11-10)

EdgePilot is currently a personal-use development project. Build its architecture
for a future single-hosted, multi-user service without requiring separate
GitHub repositories, Render services or backend URLs per person. A user
registers an EdgePilot identity, signs in using a passkey/Android biometrics
or secure recovery method, and manages only their own encrypted Public API
connection. No commercial distribution or actual multi-user Public permission
is asserted by this document. Permission may be assumed for design and
mock testing; do not treat it as verified authorization to call Public using
another real person's key. Live orders and funds transfers stay disabled.

## Core boundary

1. One HTTPS service and one installable Android app. Each user has a stable
   server-generated UUID. Each login session is tied to exactly one user and
   cannot impersonate another by supplying a user_id in a request.
2. Passkeys use WebAuthn with exact HTTPS RP origin and required user
   verification. The device/credential provider verifies biometrics; the
   server stores public keys, credential IDs, replay counters and revocation
   state, **not biometric data**. Password/recovery is a separate protected
   flow. A WebView biometric prompt is NOT equivalent to WebAuthn and does
   not authenticate the backend session.
3. Credentials are encrypted at rest per user and provider connection. Never
   return a Public secret in responses, logs, settings or Android storage.
   A real Public credential must never be sent through a third-party test
   or entered into source code. Prefer envelope encryption with key version
   and tested rotation before broad production rollout.
4. Every portfolio, balance, connection, strategy, scan, history, alert,
   worker job, cache key, account selector, and ledger record must be
   tenant-scoped. Never fall back to a global selected account. All broker
   reads must resolve the connection and account from the verified
   principal, not from an arbitrary caller-supplied account identifier.
5. Independent sessions on two Android devices must be isolated. Logging
   out, revoking a passkey or disconnecting Public for user A must not
   mutate user B. Emergency controls must be scoped correctly and a
   separate platform-wide safety stop must fail closed.
6. Device enrollment, passkey registration, account recovery, stolen-phone
   revocation, and lost-passkey recovery require explicit flows and tests.
   Password reset must not silently grant access to broker credentials
   or bypass WebAuthn.
7. For scalability use a database and job/queue design with enforceable
   tenant boundaries, durable migrations, transaction semantics, encrypted
   backups, idempotency, worker isolation and observability. SQLite
   synthetic rehearsals are evidence only; not a distributed production
   safety gate. Avoid a premature untested migration of the live personal
   database.

## Existing implementation and current blockers

- Identity sessions use Argon2id, and invitation-only member registration
  exists behind an independent default-off feature flag. Identity sessions
  deliberately cannot access legacy owner/trading endpoints.
- WebAuthn registration/authentication is wired into six independently gated
  Flask endpoints. A separate /account web interface requests WebAuthn;
  Android WebView enables native Web Authentication when supported. Verified
  Digital Asset Links, stable app-signing and end-to-end device tests remain
  outstanding; the server stores no biometric information.
- The tenant-owned encrypted Public credential vault and read-only verified
  account adapter are independently feature-gated, and remain separate from
  the legacy global broker_credentials module. The global credential
  repository must never be used to serve multiple users.
- Existing `tenant_public_live_readonly.py` is feature-flagged; all legacy
  portfolio/settings/worker paths still use single-owner state. The
  `tenant_route_audit.py` inventory explicitly blocks multi-user cutover.
- Android MainActivity.java opens the approved HTTPS host and enables
  WebView WebAuthn conditionally. The shared backend is still the intended
  architecture; do not replace it with per-user server URLs. The separate
  /account page is optional and the existing legacy login is unchanged.
- The personal-use legacy login and existing Render service remain in place
  until a verified migration. Do not auto-enable dormant identity, passkey
  or Public flags simply because code exists.

## Verification stage update — v0.2.40

Backend integration now exercises two independent synthetic users from
invitation through isolated read-only fake Public accounts, watchlists,
inactive monitor previews and session revocation on one hosted process.
Android passkey enrollment and login are **not** verified by this test:
only WebAuthn registration options are exercised, with signature
cryptography tested separately. No real brokerage keys/accounts or
production worker jobs are involved. Physical Android and permitted
real-account acceptance criteria below are still outstanding.

## Permanent Android signing artifact — CI verified November 10, 2026

The privately signed Android v0.19.17 test APK completed its manual workflow
run #42888113943 on the second attempt after the owner's certificate
fingerprint configuration was corrected. GitHub independently verified
the APK signer and uploaded the private artifact with seven-day retention.
This satisfies ONLY the **stable signed APK CI artifact** precondition.
Digital Asset Links association with the runtime host, real-device
WebAuthn passkey/biometric registration and login, and two independent
physical-device user acceptance are still unverified. The current
debug-signed APK may require uninstall/reinstall to change signatures,
so no installation instruction should claim safe in-place updates.

## Single-phone signed APK smoke test — owner report on November 10, 2026

After the independently verified permanent-signing CI attempt, the owner
reported installing that v0.19.17 APK on the same Android phone used for
earlier debug tests, then successfully logging into the legacy dashboard
with their existing saved owner token. This closes the **owner-reported
single-device app install and legacy login** subcheck only. It does not
prove the installed signing fingerprint, HTTPS Digital Asset Links,
Credential Manager passkey login, two separate tenant identities or
independent Public connections. The full multi-user acceptance gate
remains open.

## Android Digital Asset Links HTTPS response — owner-confirmed November 10, 2026

The owner captured the actual association JSON returned by the EdgePilot
HTTPS domain on an Android phone, after the verified permanent APK signer
was configured in Render. The JSON advertises the correct package,
certificate fingerprint and credential-sharing relation. This validates
the public endpoint's content, not the operating system's credential
association or passkey enrollment. All two-device identity and Public
account acceptance gates below remain open.

## v0.2.41 — Genuine WebAuthn cryptographic replay tests, offline only

The new two-user local HTTP suite uses independently generated ephemeral
P-256 software authenticator keys, actual CBOR attestation and signed
ES256 assertions verified by the production py_webauthn routines, not
patched fake cryptographic verifiers. It tests valid independent logins
and malicious origins, signatures, UV flags, challenges, counters, user
handles and cross-user revocation without any external HTTP access.
This closes only the **synthetic cryptographic protocol verification**
subcheck. Device-level Android Credential Manager biometrics, OS website
association, two real phones and independent real Public account linking
are still unverified; tenant feature flags remain default-off.

## v0.2.42 — Isolated mobile staging compilation and server-link safety

A separate, side-by-side test Android package and compile-time staging
host can now be built without modifying or uninstalling the regular
EdgePilot owner app. A fail-closed process-startup guard and the staging-only Android
association both require exact isolated RP/host, separate package, no live owner token or
Public secret, no worker/trading activity and no production database path.
A manual-only staging signer is isolated from the existing signed owner
APK workflow. This is a code/CI readiness step, not a deployed staging
service, OS association test, Android biometric assertion, or evidence of
two actual independently owned accounts. See ANDROID_ISOLATED_STAGING_RUNBOOK.md.

## Free-first AI intelligence and cost strategy (approved 2026-11-10)

The approved AI_ANALYSIS_COST_STRATEGY.md requires rights-checked zero-paid-AI
research, out-of-sample statistical validation and risk-adjusted after-fee
signals, followed by optional per-user AI with independent budgeting/BYOK
and commercial-readiness abstractions. It never grants orders, fund
movement, public distribution or customer billing. v0.2.43 begins this
research contract with standalone source-provenance, market-data quality
and conservative scenario utilities, but does not activate any provider
or worker. Explicitly preserve two physical devices/two separate
identities/two permitted independent Public accounts as the core gate.

## v0.2.45 — BYOK/budget separation is synthetically tested, not active

Encrypted per-member AI keys, depth preferences and local budget reservations
now have a separate identity-authenticated, no-HTTP test module. Ten
synthetic users demonstrate independent concurrent budget admission
and cross-user revocation boundaries. This does not enable a real person
to fund/use AI or connect a Public account, and does not establish
commercial billing, actual provider usage or ten-device scalability.
Managed credits/payments are disabled. The existing physical two-device/
two-independent-Public-account and Android biometric gate remains open.

## v0.2.46 — Licensed shared feature reuse only, not tenant activation

A dormant account-neutral cache now reuses one provider-rights-asserted,
short-lived synthetic public spread feature across ten isolated authenticated
identities. Reads check current licensed rights, individual account linkage,
CSRF, watchlist ownership and inactive worker status. No personal portfolio
data, API key or AI budget is shared. This is NOT evidence that any real
market-data provider permits caching/redistribution, nor that crypto or
prediction market coverage exists, nor that a real phone can complete
tenant onboarding. Real two-device independent Public acceptance remains
required and no live orders, transfers or AI billing are enabled.

## v0.2.47 — Offline proposal only, not connected scanning

Provider-neutral scheduling groundwork can plan one licensed shared
public fetch instead of ten duplicate requests, or isolated per-member
quota-limited work, but ONLY for verified source rights and entitlements.
All simulated calls remain proposed/not executed. Unknown sessions,
rights, quotas, backoff, user entitlement and short-lived event-settlement
conditions block planning. No autonomous worker, true market-data
license, third-party key, data redistribution, hardware login, live broker
access, subscription or payment acceptance is established. The original
two-device/two-independently owned-Public-account criterion remains open.

## v0.2.48 — No implied predictive performance or permission to trade

A separate, non-networked evaluator can compare matching synthetic
pre-settlement binary forecasts and measured optional-AI microUSD costs,
but its Brier-score improvement is descriptive only, and independent
data-source validation is not established by test fixtures. There is
no claim of real accuracy, ROI, after-fee profit, risk-adjusted alpha,
ongoing monitoring, subscription activation or a working trading bot.
The two physical independent Android users/Public accounts remain the
acceptance gate for this development phase.

## v0.2.49 — Synthetic requested tiers do not prove paid entitlement

A new tenant identity-scoped store tracks only requested future tier
labels. Effective tier remains Free, and managed credits,
subscriptions, payments, owner AI allocation, brokerage permissions
and commercial distribution are all disabled. The ten-member tests
do not activate or validate a retail billing program. Official policy,
market-data rights and independent two-physical-device/Public-account
acceptance remain separate required gates.

## v0.2.50 — AI overage reconciliation safety is synthetic

Member-specific AI reservations now preserve measured usage above the
preflight hold as an uncertain, higher-counted local budget charge.
This prevents optimistic local accounting but does not establish a
real provider-enforced hard spending limit, activated BYOK execution,
commercial payments, independent Public brokerage accounts or
working Android biometrics. Physical two-device verification and
all brokerage/trading restrictions remain mandatory.

## v0.2.51 — Isolated staging deployment proposal only

The previously approved separate Android passkey staging plan now has
a manually reviewed proposed Render service configuration and static
negative tests. It forbids copying production secrets, packages,
hosts, databases, active broker/worker permissions and any paid
plan substitution. It DOES NOT provision a new Render service,
configure DNS, verify an APK signing certificate, grant permissions,
guarantee zero hosting overages, install another app or validate
hardware passkeys. Hosting exposure requires additional cost
approval. Two physical independently logged-in Android devices
and two verified independent Public accounts remain the acceptance
goal. See STAGING_RENDER_COST_APPROVAL_RUNBOOK.md.

## Milestone acceptance criteria — not complete until verified

- Two separately provisioned EdgePilot users can register and sign in from
  separate Android devices to the same HTTPS service.
- Passkey registration and login work on both devices using Android's
  supported Credential Manager/WebAuthn flow, with an independently
  verified server session and recovery path.
- Both users can independently save and rotate their own **synthetic**
  Public credentials, with zero cross-user read/write access.
- Synthetic brokerage adapters return distinct portfolios and accounts;
  all HTTP endpoints and worker jobs preserve identity isolation.
- Adversarial tests cover swapped user/account/connection IDs, cookie
  theft/revocation, forged CSRF, replayed WebAuthn challenge, concurrent
  requests, restart, recovery, and encrypted database backup/restore.
- Only after API authorization is established, independently verify two
  real Public accounts on separate devices in read-only mode; no live
  orders or transfers. A CI green result alone does not prove this.
- Real account connection must fail closed until those authorization,
  security, and on-device acceptance checks are satisfied.

## Release process

Routine code development, tests, pull-request merges and Render deploys are
authorized as part of this approved development phase. A feature question
alone does not authorize implementation; this multi-user goal is explicitly
approved. Major out-of-scope features still require confirmation.


## v0.2.52 — Backend staging live, acceptance remains open

A separate Render **Free** backend now exists and starts normally
with fail-closed staging settings and no owner/Public secrets.
The public signer from the archived owner APK was verified and is
configured for the distinct planned staging Android package.
This is **not** complete acceptance: custom staging DNS/TLS is
unverified, staging APK is not installed, passkeys were not tested
on real devices, invitation provisioning is still blocked by the
Free service's no-shell constraint, storage is disposable, and
independent real Public accounts have not been linked. No new live
trading or payment authorization. See
STAGING_RENDER_LIVE_CHECKPOINT.md.


## v0.2.53 — Staging screen and operator one-use invitations

For an isolated staging process only, the main URL now redirects
to EdgePilot Accounts; an operator-key-gated endpoint can issue
only two one-time synthetic test member invitations per temporary DB.
Independent origin checks and attempts/quota limits apply;
the production owner landing screen and Public permissions
are unchanged. Domain Verified was reported by the user;
it is not itself Android passkey validation. This milestone
does not establish real phones, actual biometric authentication,
persistent recovery, real independent Public accounts, or
authority to trade/fund transfers. Operator key setup, signed
staging APK and real device acceptance remain separate gates.
See STAGING_OPERATOR_INVITATIONS_RUNBOOK.md.
