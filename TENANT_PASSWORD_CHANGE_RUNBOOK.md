# EdgePilot v0.2.36 — Tenant password security and device sign-out

This is an **authenticated password change**, not a lost-password recovery
or a publicly accessible account reset. An EdgePilot member who knows their
current password may change it in the separate /account security form. A
successful change revokes **every existing EdgePilot identity session** for
that user (including other phones and passkey-authenticated sessions), and
requires sign-in again. Other users' sessions, passkey public keys and
encrypted Public connections are unaffected.

## Default-off activation gate

The endpoint POST /api/identity/password/change is disabled unless
EDGE_TENANT_PASSWORD_CHANGE_ENABLED=true with already prepared tenant schema
and EDGE_IDENTITY_AUTH_ENABLED=true. No new flags are enabled by a routine
GitHub merge or Render deployment.

Only exactly two JSON properties are accepted: currentPassword and
newPassword. The request must be HTTPS same-origin with an active HttpOnly
EdgePilot identity session and its CSRF token. Client-submitted userId,
accountId, role, or recovery bypass parameters are not allowed.

Inside one BEGIN IMMEDIATE SQLite transaction, EdgePilot rechecks that
the caller's identity session is active, unexpired and unrevoked, that the
CSRF token matches, and that the owning user is active. A current-password
Argon2id verification is required. It then atomically replaces the Argon2id
hash, increments the credential version, deletes only this user's identity
sessions, and records an immutable secret-free PASSWORD_CHANGED event.
A separate per-user budget of five wrong-password attempts per 15 minutes
prevents unlimited guesses from an already authenticated session.

No password is logged or echoed, and no new session or recovery credential
is issued. The browser clears both password fields after every attempt,
hides private account content after success and displays a sign-in-again
message. The server expires the current identity cookie as well.

## What is not provided

- Forgotten-password recovery without a verified prior login.
- Email/phone ownership verification, one-time backup codes, account takeover
  review, operator credential-reset UI or passkey-only password replacement.
- User reactivation, role grants, brokerage authorization, account migration,
  trading, transfers or a new worker process.

Those require separate security design and tests. Do not treat a passkey
prompt alone as authorization to change an unknown password.

## Acceptance tests

Tests cover two independent users and several sessions, lost/stale sessions,
wrong CSRF/cross-origin requests, overposting, malformed passwords,
per-user rate limiting, concurrent password changes, current-password
verification, account disable, immutable security auditing, fail-closed
schema initialization, cookie clearance and continued legacy login
isolation. Only synthetic accounts are used.
