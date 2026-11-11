# EdgePilot v0.2.53 — Staging-only two-user invitation bootstrap

This milestone prepares an isolated, synthetic **two-person** Android
passkey experiment on the already-created Render Free staging service.
It does not create a paid resource, change the production EdgePilot APK
or authenticate with either Public brokerage account.

## Behavior

- On an explicitly isolated staging process, `/` redirects to
  `/account` so the separate staging Android APK opens identity
  login rather than the token-only owner dashboard.
- The original production process still serves the unchanged legacy
  dashboard at `/`; production does not accept staging operator requests.
- An opt-in staging-only `/staging-operator` page lets the trusted
  operator mint exactly **two** disposable, one-use, 60-minute EdgePilot
  member invitation codes by entering a separate 256-bit random
  staging operator key.
- The service stores only `EDGE_STAGING_OPERATOR_SHA256` (lowercase
  hexadecimal SHA-256 of the operator key) as a **staging-only** Render
  environment setting. Do not put the plaintext operator key in
  Render, GitHub Secrets, repository files, screenshots or URLs.
- HTTPS and exact origin/hostname restrictions apply to
  `POST /api/staging/invitations`. A 43-character random key in
  `X-Edge-Staging-Operator` is verified by constant-time SHA-256
  digest comparison. An invalid or missing key fails; six failed
  attempts per source in 15 minutes block further attempts.
- A two-slot SQLite reservation prevents races from minting
  more than two codes within the same staging database.
- The browser sends the key once in a POST **header**, clears
  its input, and never uses localStorage, sessionStorage or URLs.
  A successful response displays two codes locally, which can
  be copied and redeemed separately using the ordinary invitation
  registration process. No roles other than `member` are granted.
- No owner-session cookie, Public credential, account read,
  trading order, automation worker or bank transfer is
  enabled by this bootstrap.

## Operator key setup — after verified staging HTTPS

1. Generate an unpredictable, private 32-byte secret in
   URL-safe base64 without padding (43 characters). Do not choose a
   memorable password. Never paste that secret into this chat.
   Keep it in a private password manager or user-owned offline file.
2. Calculate its lowercase SHA-256 hex digest **locally** (the 64
   hexadecimal-character hash). This is a configuration identifier,
   not a password. The raw secret must never be committed to GitHub.
3. On Render open **only** the
   `edgepilot-passkey-staging` service (service ID
   `srv-dbpupj2jnfac73ehv1v0`) and add
   `EDGE_STAGING_OPERATOR_SHA256=<digest>`; never add it to
   `edgepilot-private-h9tl`. Once code is deployed, do
   not enable any new broker/worker/trading flags.
4. In the phone's HTTPS browser open
   `https://staging-edgepilot.belenoscreations.biz/staging-operator`.
   Enter the plaintext secret, issue exactly two codes, and
   redeem one in each independently owned Android account.
   The two codes expire in one hour; use only synthetic identities.
5. If Render Free sleeps/restarts or the database is lost, **all
   synthetic user, passkey and invitation records may disappear**.
   Do not mistake a fresh ephemeral database for secure recovery.
   A new test session must be provisioned with new codes and
   distinct members; unchanged operator secret is scoped to this
   temporary staging environment only.

## Critical gates and verification

The Render service must still use:

- `EDGE_ISOLATED_STAGING=true`;
  `EDGE_DB_PATH=/tmp/edgepilot-staging.db`
- `EDGE_WEBAUTHN_RP_ID=staging-edgepilot.belenoscreations.biz`
  and `EDGE_WEBAUTHN_ORIGIN=https://staging-edgepilot.belenoscreations.biz`
- Staging package `com.edgepilot.mobile.staging`, actual
  matching **public** signing certificate fingerprint and
  staging-only Digital Asset Links
- `EDGE_TENANT_SCHEMA_PREPARE=true`,
  `EDGE_IDENTITY_AUTH_ENABLED=true`,
  `EDGE_TENANT_SIGNUP_ENABLED=true`,
  `EDGE_TENANT_PASSKEYS_ENABLED=true`
- All Public vault/read-only account, monitor, trading, automation,
  owner token and credential secrets disabled or absent

Verify `/healthz`, `/.well-known/assetlinks.json`, and the
independent `/account` page on the **custom HTTPS hostname**
before attempting Android Credential Manager. Render's default
`onrender.com` address is not the configured WebAuthn RP.

**Manual staging Android workflow:** GitHub Actions →
"EdgePilot isolated staging Android test APK" → Run workflow on
`main`, input `staging-edgepilot.belenoscreations.biz`.
The workflow alone has existing private keystore access. Confirm
signed APK certificate, package, URL and SHA-256 independent of
the production installation before sideloading on each phone.
Only the separate staging package may be installed for this test.

No physical passkey, two-device identity acceptance or real
Public-account acceptance is established by offline tests.
Any eventual real Public API access needs separate provider
authorization, durable isolated data storage, and read-only
gate verification. Live orders and fund transfers remain disabled.

See `STAGING_RENDER_LIVE_CHECKPOINT.md` for the actual Free
service and earlier DNS checkpoint. This bootstrap is limited
to two synthetic invitations per ephemeral database and is
not a general-purpose multi-tenant administration endpoint.
