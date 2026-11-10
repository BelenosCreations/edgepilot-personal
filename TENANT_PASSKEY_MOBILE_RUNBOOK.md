# EdgePilot mobile passkey integration — v0.2.30

## What the code provides

- A responsive, separate /account screen for invitation redemption, password
  sign-in, passkey sign-in/enrollment and user-owned encrypted Public key setup.
- Browser WebAuthn create/get with binary/base64url conversion. All credential
  signatures are verified on the backend using the fixed HTTPS relying party.
  The browser never stores a password, Public key or bearer cookie in local
  storage; server cookies are HttpOnly, Secure and SameSite=Strict.
- Android WebView native Web Authentication support via AndroidX WebKit
  (with a runtime capability check), using stable AndroidX Credential Manager
  dependencies. Unsupported devices fail naturally and may use password
  sign-in; no fake biometrics or JavaScript credential bridge is installed.
- A fail-closed /.well-known/assetlinks.json endpoint that only publishes
  delegate_permission/common.get_login_creds for com.edgepilot.mobile when
  a correctly formatted EDGE_ANDROID_CERT_SHA256 fingerprint is supplied.
  A missing or invalid fingerprint returns HTTP 404.

The current Android application still opens the existing personal dashboard
by default. The account interface is reachable directly at /account, but new
tenant signup, identity authentication, vault and passkeys all remain behind
their separate default-off server flags. Ordinary code deployment does not
activate those flags.

## Verified certificate requirement

Digital Asset Links must use the *actual* SHA-256 fingerprint of the
certificate signing the Android app the user installs. An unsigned or
ephemerally signed GitHub Actions debug build cannot be trusted as the
permanent production certificate. Do not guess or invent the fingerprint.
After configuring a stable signing process, inspect the release signing
certificate, verify ownership of the HTTPS domain, then configure the
server-side EDGE_ANDROID_CERT_SHA256 value in secure deployment settings.
For a test device the exact certificate of that installed test build
must match the association response.

Test the association by visiting:
https://edgepilot.belenoscreations.biz/.well-known/assetlinks.json
It must return the expected package name and matching SHA-256 value. Do not
claim biometrics work until verified on the intended device with a provider
that supports passkeys.

## End-to-end validation plan

1. Verify the app is signed and website association validates.
2. Enable independent tenant/schema, identity, registration, passkey and
   Public vault flags in a controlled test environment; do not turn on
   trading, fund transfers, legacy account cutover or worker execution.
3. Use two different invitation tokens to enroll two separate EdgePilot
   accounts on distinct Android devices. Verify password session isolation.
4. Register passkeys through the account UI using Android Credential Manager.
   Test fresh passkey sign-in and server session verification on each phone.
5. Confirm one user's revoked passkey only invalidates their own sessions,
   and a stolen/expired/replayed challenge creates no login.
6. Store synthetic Public credentials separately and verify cross-user
   access to connection IDs, linked accounts, portfolio metadata, and
   worker tasks fails. Test server restart and backup/restore.
7. Only after independently verified provider authorization and security
   readiness, connect two actual Public accounts read-only with real keys.
   Live brokerage orders and funds transfers remain disabled.

## Limitations

No verified device biometric login, permanent signing identity,
credential-recovery workflow, provider permission confirmation, production
multi-tenant worker migration or two-real-device acceptance yet. A passing
GitHub Android build checks compilation only; it does not establish a valid
Digital Asset Link or successful on-device WebAuthn ceremony.

This development milestone does not require asking permission for routine
CI, source merges or Render deploys, but does not authorize exposing or
turning on sensitive production authentication/brokerage flags.
