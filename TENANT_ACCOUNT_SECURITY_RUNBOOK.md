# EdgePilot v0.2.36 — Account password and session security

## Purpose

Users of the future shared EdgePilot service can securely change their
EdgePilot password or explicitly sign out every device, without relying on
a separate server administrator. These are identity-only security actions;
they cannot change another user's session, Public secret, linked account,
trading state or funds.

Endpoints (both require a currently authenticated identity, same-origin
HTTPS, and the identity CSRF token):

- POST /api/identity/security/change-password with exactly currentPassword
  and newPassword
- POST /api/identity/security/sign-out-everywhere with exactly currentPassword

Both operations require **proof of the current EdgePilot password**.
The password is never logged or returned. Every user session is invalidated
when the operation succeeds, including the current phone and other devices.
Passkey credentials stay registered and may be used to sign in again.
This is not a lost-password recovery flow.

## Server safeguards

Security actions first verify the identity session and CSRF and consume
one entry in a per-user attempt budget. Eight attempts per 10-minute
window are permitted, protecting against online guessing with a stolen
session. Argon2id verifies the supplied password outside the write lock,
avoiding unnecessary database blocking during expensive password hashing.

Immediately before changing credentials or revoking sessions, the server
rechecks the identity cookie, CSRF, credential version, user active status
and original password hash **inside a SQLite BEGIN IMMEDIATE transaction**.
A logout or credential rotation between the preliminary verification and
the write therefore causes fail-closed denial. The new hash is stored with
an incremented credential version and all sessions are removed atomically.

A separate append-only identity-security audit records only action,
user identifier and timestamp; never a password, passkey or Public API
secret. The audit rows reject ordinary SQL updates/deletes.

The account UI uses password inputs, clears them on success/failure,
checks the explicit server safety flags, and removes all previous account
data after logout. It warns that passkeys remain registered.

## Limitations

The user still needs at least one valid login method and their current
password to perform these actions. There is **no self-service forgotten
password or lost-device recovery** yet. That requires separately designed
identity verification, one-use recovery codes or verified contact methods.

Identity authentication remains default-off unless intentionally enabled.
These endpoints are never available through the legacy personal owner
session and cannot enable real brokerage orders, trading or transfers.
All real two-device, Public-credential and Android biometric acceptance
requirements remain pending.

## Testing

Synthetic two-user Flask and repository tests exercise password proof,
rate-limiting, cross-origin/CSRF denial, overposting, stale-session
invalidation, password changes, all-device signout, separate-user
preservation, append-only audit and account UI secret clearing. A passing
CI run cannot substitute for real device/passkey and provider tests.
