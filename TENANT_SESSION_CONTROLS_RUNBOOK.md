# EdgePilot v0.2.37 — Scoped active-session management

This milestone adds a separately disabled-by-default identity-session control
surface for future two-device EdgePilot users. It does not activate Public
brokerage access or the legacy trading/Observe/Paper worker.

## Optional identity-only endpoints

Set EDGE_TENANT_SESSION_CONTROLS_ENABLED=true only after the independently
prepared tenant schema and EDGE_IDENTITY_AUTH_ENABLED=true are ready.

GET /api/identity/sessions requires a verified identity cookie and identity
CSRF. It returns only the member's active sessions, issue/expiry timestamps,
an opaque non-bearer session handle, and a current-session indicator.
No username, device fingerprint, browser user agent, public IP, location,
credential hash, raw bearer token, CSRF, Public secret or account ID is returned.

DELETE /api/identity/sessions/<session_id> requires same-origin HTTPS, the
identity cookie and identity CSRF. It may revoke ONLY another active session
of the same authenticated member. The current session must use the existing
logout operation. Both listing and revocation serialize with identity changes
using BEGIN IMMEDIATE SQLite write transactions. A forged handle, disabled
member, expired/revoked cookie, stale CSRF or cross-member request fails
closed without mutating another identity.

A successful revocation deletes the targeted identity session and records a
secret-free immutable audit event. It does not change passkeys, credentials,
brokerage accounts, stored watchlists or another user's sessions.

## UI and limitations

The /account screen lists signed-in sessions with timestamps and a badge
for the current session. Other sessions have a confirmed "Sign out this
session" action. Data from a previous user is cleared and asynchronous
results are invalidated on logout/account switch.

Because EdgePilot intentionally stores no fingerprints, IP addresses,
device labels or locations, it cannot accurately identify a physical device
from this list: the user sees sign-in times and the current-session indicator.
For lost devices or uncertain sessions, changing the EdgePilot password still
revokes *all* sessions. Current identity sessions expire after four hours.

This does not establish forgotten-password recovery, persistent native
biometric login, device binding, backend authorization for real multi-user
Public accounts, account-scoped running market scanners, or two-device
end-to-end acceptance. The default production flag remains OFF.

## Validation

The full backend/Flask and JavaScript CI must pass with multi-user synthetic
sessions; tests verify other-user denial, own-session protection, CSRF,
cross-origin restrictions, concurrent revocation, password/all-device
revocation, immutable audit, disabled-by-default state and browser safety.
No real broker key or market data request is used.

Read MULTIUSER_PLATFORM_ACCEPTANCE.md and DEVELOPMENT_CONTINUITY.md
before considering this feature ready for an enabled multi-user rollout.
