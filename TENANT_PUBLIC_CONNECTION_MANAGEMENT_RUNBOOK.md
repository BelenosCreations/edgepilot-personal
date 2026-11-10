# EdgePilot v0.2.35 — User-owned Public key replacement and disconnection

## Purpose

The multi-user account screen now lets a signed-in EdgePilot member manage
their existing encrypted Public connections. The user first selects one of
their own connections, and may replace its saved Public API secret or
disconnect it from EdgePilot. No action closes the Public brokerage account,
submits an order, triggers a scan or requests a funds transfer.

All operations are still opt-in and require the existing identity and
Public-vault feature flags. The backend lifecycle endpoints already existed;
this milestone exposes them through explicit, user-confirmed UI controls and
hardens the session validity check inside the database transaction.

## Behaviors

**Replace saved key** requires a fresh secret and an explicit confirmation.
The browser sends a CSRF-protected POST to
/api/identity/public/connections/<connection_id>/rotate. The backend encrypts
the replacement and disables all previously bound Public account records,
since the replacement key might belong to a different brokerage account.
The user must rediscover and verify any linked account again.

**Disconnect selected account** requires a second explicit confirmation
before the browser issues a CSRF-protected DELETE to
/api/identity/public/connections/<connection_id>. The backend revokes only
that owner's connection, disables linked account bindings, and appends a
secret-free audit event. The operation does not delete or cancel the user's
Public brokerage account, nor automatically revoke the key at Public.

After either operation, the browser discards previously displayed account,
balance, holding, monitoring, and connection data and fetches the current
user-scoped list again. A request returning after a logout/account switch
cannot repaint a prior user's data. The replacement secret input clears even
when the server refuses the request.

## Server safeguards

The rotation/disconnection mutation now verifies that the identity cookie
and CSRF token remain valid **inside** the same SQLite BEGIN IMMEDIATE
transaction as the actual credential update and account revocation. This
fences the race where a user logs out or their identity is revoked between
the initial identity check and the write. Owner identity is never accepted
from the client, ciphertext stays encrypted, and audit events are append-only.

The existing default-off EDGE_TENANT_PUBLIC_VAULT_ENABLED gate remains in
place. There is no new public API for retrieving decrypted credentials;
the legacy global owner credential remains completely separate. No
production database migration or provider network activity is required
by this code-only milestone.

## Verification

Regression tests exercise a revoked session between preflight and the
mutation, attempt both rotate and disconnect, and verify the key and audit
rows are unchanged. Existing two-user HTTP tests check cross-owner denial,
wrong CSRF, secret redaction, linked account invalidation and audit behavior.
New UI checks verify confirmation, scoped IDs, no local storage of secrets,
stale identity response rejection and explicit no-trading flags.

Only post-merge CI success, plus real on-device tests, can establish
compatibility beyond code. This milestone does **not** finish physical
two-device sign-in, permanent Android signing, real Public permissions,
tenant worker migration or the user's two-account acceptance objective.
