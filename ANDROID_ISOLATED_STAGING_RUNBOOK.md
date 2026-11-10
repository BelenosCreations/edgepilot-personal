# EdgePilot v0.2.42 — Side-by-side isolated Android staging test app

## Why a separate test app

The owner has installed and successfully logged into the permanent-signed
EdgePilot v0.19.17 Android app. The existing app always opens
https://edgepilot.belenoscreations.biz and uses package
com.edgepilot.mobile. That owner dashboard must remain operational with
its existing server-side access token, observe/paper data and settings.

Testing the separate per-user login and Android Credential Manager requires
a controlled backend that can enable identity/passkey flags, and that test
backend must NOT inherit live owner access, real Public credentials or
trading/transfer permissions.

This development milestone adds a second Android build type. It does NOT
activate any test deployment, provision a paid service or generate a new
Android signing key.

## Android build variants

- Existing debug build: regular com.edgepilot.mobile / EdgePilot label,
  pinned production host, unchanged debug artifact workflow.
- Existing release build: regular com.edgepilot.mobile / EdgePilot label,
  unchanged manually signed production package and certificate workflow.
- New staging build: com.edgepilot.mobile.staging / EdgePilot Staging label.
  This separate Android package can coexist on one physical phone with the
  original. A compile-time hostname supplied as edgePilotStagingHost must be
  an owner-controlled subdomain ending in .belenoscreations.biz, and must
  not be the production EdgePilot hostname.

Without a hostname property, the staging variant deliberately compiles
against unconfigured.edgepilot.invalid, a nonfunctional placeholder. This
cannot accidentally load the existing owner's live dashboard.

Compile a staging variant locally, replacing the hostname only once an
independent staging backend and HTTPS domain are provisioned:

    gradle -p android :app:assembleStaging -PedgePilotStagingHost=YOUR-OWNED-STAGING.belenoscreations.biz

The debug workflow checks this variant compiles, but uploads only the
existing normal debug APK. It never distributes an unsigned staging build.

A **separate, manually dispatched** GitHub workflow can sign an isolated
staging APK with the operator's already configured certificate:
.github/workflows/android-staging-signed.yml. It takes one explicit
staging_host input, rejects the owner's production hostname and other
domains, runs only on main, signs a staging-only package, checks the
installed-certificate SHA-256, and uploads only that verified APK for 7
days. No manual staging signed job should be triggered before the isolated
HTTPS backend and exact domain are verified.

## Isolated website association

The backend staging startup guard and Digital Asset Links route enforce
separate nontrading configuration. The association route still publishes com.edgepilot.mobile
by default. To serve the separate staging package, an isolated test service
must explicitly set both EDGE_ISOLATED_STAGING=true and
EDGE_ANDROID_ASSOCIATION_PACKAGE=com.edgepilot.mobile.staging. The route
refuses staging association unless the request's HTTPS host and configured
WebAuthn RP ID/origin match a distinct owned staging subdomain, and unless
the following safety conditions also hold:

- EDGE_ANDROID_CERT_SHA256 is an actual verified public certificate value.
- EDGE_DB_PATH is NOT under /data/ (the live Render persistent volume path).
- EDGE_APP_TOKEN and PUBLIC_API_SECRET are absent/empty; production owner
  access and real provider secrets must never be copied into staging.
- EDGE_AUTOMATION_WORKER_ENABLED, ENABLE_LIVE_ORDERS,
  EDGE_TENANT_PUBLIC_VAULT_ENABLED and
  EDGE_TENANT_PUBLIC_READONLY_ENABLED are all false.
- A missing requested staging package or an arbitrary package is refused.
- The existing production package and its association response remain intact.

These conditions are enforced both by the website association route and
by a process-startup preflight that refuses unsafe isolated-test settings
**before database or owner credential-store initialization**. They do not
constitute authorization to route any live account or real brokerage
connection to staging. A staged service requires a separate private test
database, separate URL and operational isolation; treat it as untrusted
until reviewed.

## Recommended staging identity test settings (not deployed)

After approving any required new hosting/domain cost and creating an
isolated HTTPS service, consider this test-only set:

    EDGE_DB_PATH=/tmp/edgepilot-staging.db
    EDGE_TENANT_SCHEMA_PREPARE=true
    EDGE_IDENTITY_AUTH_ENABLED=true
    EDGE_TENANT_SIGNUP_ENABLED=true
    EDGE_TENANT_PASSKEYS_ENABLED=true
    EDGE_WEBAUTHN_RP_ID=THE-OWNED-STAGING-HOST
    EDGE_WEBAUTHN_ORIGIN=https://THE-OWNED-STAGING-HOST
    EDGE_ISOLATED_STAGING=true
    EDGE_ANDROID_ASSOCIATION_PACKAGE=com.edgepilot.mobile.staging
    EDGE_ANDROID_CERT_SHA256=THE-ALREADY-VERIFIED-PUBLIC-FINGERPRINT
    EDGE_AUTOMATION_WORKER_ENABLED=false
    ENABLE_LIVE_ORDERS=false
    EDGE_TENANT_PUBLIC_VAULT_ENABLED=false
    EDGE_TENANT_PUBLIC_READONLY_ENABLED=false
    PUBLIC_API_SECRET=[UNSET]
    EDGE_APP_TOKEN=[UNSET]
    EDGE_CREDENTIAL_KEY=[UNSET]
    EDGE_TENANT_ACCOUNT_READS_ENABLED=false
    EDGE_TENANT_MONITOR_PREVIEW_ENABLED=false
    EDGE_TENANT_WATCHLIST_EDIT_ENABLED=false

This is a test-only *plan*, not a Render change. A temporary SQLite file
is not a recovery or durable multi-user database. Do not use actual
brokerage accounts or install/uninstall the owner's regular application.

## Acceptance test once staging is approved

1. Verify staging HTTPS serves ONLY staging's package/certificate in
   /.well-known/assetlinks.json; verify the original website still serves
   the original app ID and certificate.
2. Build a private staging signed APK on main and check its package,
   certificate and compile-time host. Install beside owner EdgePilot.
3. In the staging app, use distinct one-use invitation(s), create synthetic
   EdgePilot member accounts and register passkeys via Android Credential
   Manager. Confirm actual biometric/PIN user verification and a
   server-verified new tenant session.
4. Revoke one synthetic passkey and verify its sessions stop working while
   the other account and the original owner app remain untouched.
5. Repeat with a second real Android device and an independently owned
   EdgePilot identity. Real Public account testing is a separate later
   read-only gate subject to appropriate provider authorization.

No such device or production acceptance is claimed by CI compilation.
