# EdgePilot v0.2.40 — Two-user shared-backend synthetic acceptance rehearsal

## Scope

This test suite represents **two separate devices using two isolated HTTP
cookie jars against one Flask HTTPS application instance**. It is a backend
acceptance rehearsal only — not a signed Android APK, a biometric device
test or permission to connect unrelated real Public brokerage accounts.

The suite provisions two EdgePilot member identities with distinct one-use
invitations; verifies that registration does not issue a login session;
signs in Alice and Bob separately; exercises session CSRF rotation, secured
cookies and independent identity values; then checks the following sequence:

1. Each identity can request WebAuthn passkey enrollment options bound to
   the server's exact HTTPS relying party. Cryptographic passkey signing
   and Android Credential Manager user verification remain covered by
   separate tests; no biometric enrollment is faked as successful here.
2. Each identity saves a different **fake** Public secret in its own
   encrypted tenant vault, never in the legacy single-owner credential store.
3. A deny-by-default in-process Public HTTP double provides distinct
   accounts and portfolio values, and will throw on any unlisted endpoint
   or invalid token. No real network calls are made.
4. Each user discovers and links only the broker account returned for that
   user's own fake secret. User A cannot read or link user B's connection,
   linked account or portfolio.
5. Each member saves and reads their own inactive watchlist and monitor
   preview, while no account becomes an active worker.
6. Alice may sign in a second synthetic client and selectively revoke that
   session; Bob's session remains valid. Neither member identity can
   authorize the legacy personal dashboard or a brokerage execution route.
7. CSRF mismatch, missing CSRF, cross-origin requests and anonymous access
   are tested for mutation denial.

The fixture uses no real Public secrets, account identifiers, trades,
withdrawals, deposits, bank data or production environment flags.

## Acceptance stage

**Synthetic backend two-user lifecycle:** Tested as a CI integration
rehearsal only. This is a *prerequisite* for the actual user-approved
completion target, not completion itself.

**Still required before the project stage is complete:**
- Owner-provisioned permanent Android signing key, secure backup and
  fingerprint-pinned signed APK (v0.2.38 only prepared the workflow)
- Verified Digital Asset Links response for that exact APK and HTTPS host
- Working native Android Credential Manager/WebAuthn enrollment and
  sign-in on two real devices, plus lost-device recovery testing
- Real Public account read-only verification for two independent users
  once provider authorization and security readiness are confirmed
- Account-specific background scanning/workers and persistent caches that
  cannot cross user/account boundaries, if active monitoring is needed
- Real production data backup and disaster restore policy with separate
  key custody and recovery approvals
- Live trading, autonomous order submission and funds transfers remain
  disabled until separately and explicitly authorized

Review MULTIUSER_PLATFORM_ACCEPTANCE.md and
DEVELOPMENT_CONTINUITY.md before declaring completion.

## CI

Run `python -m unittest discover -s tests -v` in `backend`, followed by
Python compilation and browser JavaScript syntax checks. The full synthetic
acceptance rehearsal is in
`backend/tests/test_two_device_synthetic_acceptance_v0240.py`.

Any apparent HTTP provider call outside the test fake's explicit URL and
method list is a failing test. A successful CI result only validates
server-side behavior at that commit; physical-device and live-provider
acceptance must be evidenced separately.
