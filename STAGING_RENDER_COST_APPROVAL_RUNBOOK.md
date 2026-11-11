# EdgePilot v0.2.51 — Cost-gated, isolated Render staging proposal

**Status: prepared in GitHub, NOT deployed.** This proposal is not an
auto-applied Render Blueprint. The existing production Render service,
its persistent disk and current owner Android APK must stay unchanged.
There is no new Render resource, DNS record, payment instruction,
brokerage credential, signed staging APK or actual passkey enrollment.

## Workspace, proposed service and physical-device isolation

The approved target is **Belenos's workspace** in Render. The existing
production service is `edgepilot-private-h9tl`, with its own `/data`
persistent volume. NEVER duplicate that service or inherit its settings.

The prepared, deliberately non-deployable proposal is
`deploy/staging/render-service.proposal.json`. The candidate is
`edgepilot-passkey-staging` in the Ohio region, from the same private
GitHub repository, using the `backend/Dockerfile` and branch `main`.
It has auto-deploy **off** and a proposed Render Free web service plan.
Only a separately verified test hostname
`staging-edgepilot.belenoscreations.biz` may be used. That hostname
is a proposed DNS name, **not proof that DNS is configured**.

The owner-facing Android package is `com.edgepilot.mobile`.
The proposed signed staging package is
`com.edgepilot.mobile.staging`, installed **side by side**. Never
uninstall the working owner's existing APK to start staging.

The proposal intentionally leaves
`EDGE_ANDROID_CERT_SHA256=REQUIRES_VERIFIED_PUBLIC_CERT_BEFORE_DEPLOY`,
which fails the existing backend startup isolation guard until a
genuine certificate fingerprint has been independently extracted from
the signed Android APK. This placeholder is not a certificate and
must never be replaced with a sample or invented value.
The future staging site must have its own valid TLS certificate and
Android Digital Asset Links content for **only** the staging package.
Verifying JSON content alone is not proof of OS passkey association.

## Mandatory runtime separation

Required explicit staging settings:

- `EDGE_ISOLATED_STAGING=true`, `EDGE_DB_PATH=/tmp/edgepilot-staging.db`
- `EDGE_TENANT_SCHEMA_PREPARE=true`,
  `EDGE_IDENTITY_AUTH_ENABLED=true`,
  `EDGE_TENANT_SIGNUP_ENABLED=true`,
  `EDGE_TENANT_PASSKEYS_ENABLED=true`
- Exact staging WebAuthn RP host/origin and staging Android package;
  the public, genuine signed APK certificate fingerprint
- `EDGE_AUTOMATION_WORKER_ENABLED=false`,
  `ENABLE_LIVE_ORDERS=false`, Public-vault/read-only flags
  **false**, tenant account reads and monitor/watchlist preview
  flags **false**, password/session management **false**
- Omit `EDGE_APP_TOKEN`, `PUBLIC_API_SECRET`,
  `EDGE_CREDENTIAL_KEY`, OpenAI keys, signing keys and all
  production session/identity/database files

A temporary SQLite database is adequate only for disposable
synthetic phone ceremonies. On Render Free, spinning down or
redeploying may erase passkeys, test accounts, invitations and
sessions. It is NOT adequate proof of durable multi-user recovery,
and real Public-account linking is still disallowed in staging.

## Hosting review required before provisioning

Render documentation describes a $0 compute Free tier, but the
workspace's included build minutes and outbound bandwidth are
shared and **may incur overage charges if a payment method is saved**.
Free web services spin down after 15 minutes idle and have an
ephemeral filesystem. Current provider source:
https://render.com/docs/free

A Starter plan may avoid free-tier sleep but introduces a recurring
hosting charge; a persistent disk would introduce separate cost and
require a separately designed isolation-safe database path. The
current repository guard intentionally forbids reusing the production
`/data` location. Any paid staging capacity, persistent storage,
third-party data services, new commercial billing or overage exposure
must be explicitly priced and approved **before** deployment.
This user approval authorizes preparation, not undisclosed charges.

Before any Render service creation, separately confirm:
1. Actual workspace usage and permitted overage/spend controls in
   Render Billing; do not assume every $0 compute service is no-cost.
2. The final plan, disk decision, price and monthly liability; obtain
   explicit user authorization for additional charges.
3. Ownership and DNS routing of the candidate hostname plus TLS.
4. The signed staging APK's real public cert fingerprint.
5. Exact production-vs-staging environment, host/package and DB
   difference; check no unexpected inherited env or shared disk.
6. Safe invitation creation/testing for two separate synthetic users.
7. Whether short-lived disposable data is sufficient for the first
   hardware ceremony; durable identity acceptance requires later
   isolated persistent storage and recovery testing.

Only then deploy under explicit approved cost controls and verify
`/healthz`, `/.well-known/assetlinks.json`, false production
flags and logs. The Android staged signer should remain manual-only
until HTTPS/Digital Asset Links are confirmed.

## Reproducible offline security test

From `backend/`:

    python -m unittest tests.test_staging_release_readiness_v0251 -v

This test reads only the proposal JSON and exercises the existing
`staging_isolation.validate` guard using a **test-only** certificate
string in memory. It rejects production credentials, production
host/package/DB, automated deployments, paid plan substitution,
missing disable flags and unexpected fields. It never makes a
Render, DNS, Public, payment, OpenAI or GitHub API request.
Passing this test establishes a safe *proposal shape*, **not**
a running service, approved provider usage, cost cap or physical
phone passkey acceptance.

The core development completion condition remains two physical
Android devices, two independent EdgePilot identities and two
independently owned Public brokerage accounts successfully linked
and isolated end-to-end after required provider authorization.
No live orders or bank transfers are part of that acceptance.
