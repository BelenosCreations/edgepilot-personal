# EdgePilot v0.2.25 — Shared multi-user identity and passkey foundation

**Status: BACKEND-ONLY / INACTIVE.** The approved product direction is one
EdgePilot platform with a user account per person, their own Public API
credential, separate history and settings, and biometric-capable login.
Permission to develop as though Public permits multi-user integration is an
engineering assumption, not a representation that Public granted permission.
No product registration, brokerage read, new account or live execution is
enabled by this release.

## Architecture and completion requirements

1. One EdgePilot service with independent authenticated users and sessions.
2. User-scoped encrypted credential connections, verified provider account
   bindings, settings, portfolio, history, workers, queues, cache and audit.
3. User/account authorization on EVERY API route, database query, worker
   event, decrypted secret, monitoring cycle, restore and backup operation.
4. No Public secret, biometric image, private passkey key or banking detail
   in the APK, browser localStorage, logs or other users' information.
5. WebAuthn passkeys with Android WebView Credential Manager and verified
   Digital Asset Links. Biometric/PIN checks happen on-device. EdgePilot
   stores credential public keys, IDs and signature counters only.
6. Secure registration (email verification or invitations), account recovery,
   password reset and anti-abuse controls; no shared admin login token.
7. Read-only Public calls scoped to each user's encrypted credential and
   verified linked account, without legacy global account selection.
8. Actual two-device, two-identity, separate-Public-account tests before the
   user-requested current development stage may be called complete.
9. Live orders, automated trades and transfers remain disabled unless
   separately authorized and secured.

## Added in v0.2.25

The new dormant module at backend/engine/tenant_passkeys.py uses the
maintained py_webauthn library, not a custom signature implementation.

- A current authenticated identity session and CSRF must authorize passkey
  registration. Random five-minute challenges are consumed once, tied to a
  fixed HTTPS relying-party origin and stored with hashed request IDs.
- Discoverable passkey login does not reveal existing usernames. Each
  signed response is validated cryptographically for challenge, origin,
  relying-party domain, user verification, credential ID, user handle and
  monotonic signature counter before issuing an identity-only session.
- Registration and revocation check the authenticated user's ownership.
  Passkey sessions cannot authenticate the legacy owner brokerage or worker.
- Neither Flask nor the Observe worker imports the module. Static route audit
  rejects accidental wiring. Production never executes passkey table setup.

## Current test and activation limits

Local regression tests use a test-only stub for *successful* WebAuthn
cryptographic verification; invalid real assertions are checked against
the real library. **This is not yet a verified Android biometric sign-in.**
The existing Android WebView wrapper needs Credential Manager and a signed
assetlinks.json website association before passkeys work on-device.

Existing global backend credential, sessions, settings and worker paths are
still single-owner. Next steps include secure self-registration, per-user
credential endpoints, tenant data migration, independent monitoring, encrypted
backup isolation, cross-owner negative tests, Android passkey integration,
real two-device tests and two distinct Public read-only connections.

Routine merge and Render deployment can proceed after passing PR CI, but
these modules must remain dormant. The legacy owner credential must never
be silently assigned to another tenant, and provider permission should
be reviewed before external multi-user distribution.
