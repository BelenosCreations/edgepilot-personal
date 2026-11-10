# EdgePilot v0.2.33 — Account-scoped watchlist editing (inactive)

Each signed-in EdgePilot member can update an inactive monitoring watchlist for
a linked Public account they own, without affecting another user's account.
The new endpoint is PUT /api/identity/accounts/<account_id>/monitor/watchlist
and accepts exactly {"symbols":["SPY","QQQ"]}. A blank array clears the
watchlist. Valid symbols are 1–15 uppercase ASCII characters, must start
with A–Z, and may include digits, periods and hyphens. Maximum 25 unique
symbols, with a 512-character comma-separated storage limit.

The route requires a verified tenant identity session, same-origin HTTPS,
identity CSRF and a feature gate. The service rechecks identity and CSRF
*under the database write lock*, then verifies account, user, Public
connection and observe-only inactive runtime before writing a scoped
setting and secret-free audit event. Missing/foreign/revoked account and
invalid runtime are denied. Invalid input returns a sanitized error.

The /account page provides an editable, per-account comma-separated
watchlist and a Save action. It preserves session-generation fencing:
responses arriving after logout or user switch never populate the new
session's UI. Values are rendered with textContent, not HTML injection.

## Configuration

EDGE_TENANT_WATCHLIST_EDIT_ENABLED=false by default. If enabled, the
existing tenant schema, identity authentication, tenant account reads, and
inactive monitor-preview feature must already be enabled. The new setting
cannot enable a running monitor, paper trader, live trader or funds transfer;
the existing legacy single-owner worker is never connected to this code.

## Verification

Two different identity sessions with separate fake Public connections must
be able to edit only their own watchlists. Regression tests cover CSRF,
cross-origin requests, forged account/user IDs, invalid/duplicate symbols,
revoked sessions, disabled accounts, revoked Public connections, inactive
runtime checks, audit rows, independent portfolios and zero worker leases.
No real API keys or trading instructions are used in CI.

Do not mark multi-user acceptance complete until real independently owned
Public accounts, device passkeys, signed Android installations, tenant
history/worker isolation, backup/recovery and provider authorization are
verified. See MULTIUSER_PLATFORM_ACCEPTANCE.md.
