# EdgePilot v0.2.16 — Dormant session/account API and monitor isolation

**Safety status: INACTIVE.** This release introduces future-only service
classes and synthetic tests. It does NOT enable multi-user authentication,
convert existing HTTP routes, connect new Public accounts, run real per-account
workers, execute broker orders, transfer funds or migrate production data.

## Account switching per device

`backend/engine/tenant_api_gateway.py` is a future read-only application
service. The schema installer is **opt-in**, never called during ordinary
server startup. In isolated tests it adds:
`tenant_session_account_selection(token_hash,user_id,account_id,selected_at)`.

A selection is keyed by a SHA-256 hash of the verified identity cookie token,
not the plaintext token or a global selected-account setting. A second device
gets its own identity session and independent selection. The schema uses
foreign keys plus insert/update triggers to prevent a token from being
associated with another session owner's user ID.

`DormantAccountGateway` enforces:
- A valid identity session and active user for every read and switch.
- A valid identity CSRF token for changing/clearing a selection.
- Account membership and non-disabled account, non-revoked Public connection.
- No fallback to the legacy global account or to the first account.
- Per-account and per-user filters on all metadata reads, including history
  references and source-only historical summaries.
- Selection loss on logout/revocation, and denial on disable/revocation.
- No broker request, worker command, order placement or fund operation.

All HTTP routes and Android account-switching UI remain unchanged. **Do not
expose this class directly as a Flask route** without rechecking cookie origin,
CSRF, authorization, error behavior, logging, rate limits, and all app
session-to-tenant authorization boundaries. The live legacy login cookie is
not an identity tenant cookie.

## Disabled account-specific observation planning

`backend/engine/tenant_monitor_blueprint.py` provides internal-only
`DormantAccountMonitorPlanner` and immutable `MonitorBlueprint` objects:
- Trusted backend caller supplies explicit `(user_id, account_id)`, never an
  HTTP-provided user ID or the legacy `selected_account()`.
- Account, user and Public connection are verified; watchlists are drawn only
  from the corresponding account's settings.
- Every plan is hardcoded inactive, Observe only. No plan is scheduled,
  connected to Public, granted paper/live trading, or enabled at runtime.
- Explicit start/trade methods fail closed.
- A synthetic observation replay requires an exact offline-only approval
  phrase and a verified /dev/shm database. It records a clearly labeled
  `SYNTHETIC OFFLINE REPLAY ONLY` with zero accepted quotes through the
  existing account-scoped lease store. This is **not** real monitoring or a
  health check, and is never a job in production.

Synthetic tests cover two separate owners with separate Public connections,
two accounts under one owner, two concurrent phone sessions choosing different
accounts, cross-user/foreign-account denial, CSRF, session expiration/revocation,
disabled accounts/connections, direct SQLite owner spoofing, account watchlist
separation, offline lease scope and runtime/trade activation rejection.

## Current production blockers

The static route audit continues to report that legacy APIs and the active
observation worker use a global selected account. Its new checks reject
accidental imports of the dormant gateway or planner into live Flask or the
legacy worker. This audit is a source-level gate, **not proof of live runtime
isolation**; it is deliberately not a real multi-account implementation.

Future work needs an explicitly approved end-to-end redesign of:
account-specific authentication and session/CSRF middleware, scoped
transactions/portfolio/broker calls, query boundaries in all APIs, per-account
worker runtime budgets and ownership checks, scheduling and error isolation,
Android UI and on-device account enrollment, recovery, and reversible migration.
No production cutover is authorized by v0.2.16.

## SSH warning — diagnostic only, no changes made

The repeated Termux message:
`client_global_hostkeys_prove_confirm: server gave bad signature for ED25519
key 0` occurs during an OpenSSH **additional host-key update proof** exchange,
which is distinct from the initial host-key comparison. That helps explain
why commands can complete, but is **not** sufficient evidence that the SSH
connection is safe.

Render's official Ohio public SSH key fingerprint as of the development
review is:
`SHA256:kRDsLlrHqOyqso58sEKyO6ZFMPj7p24zfNxYJ42yXGI`.
Official source: https://render.com/docs/ssh

On Android, read-only diagnostic commands for a future supervised check:
- `ssh -V` (installed OpenSSH version).
- `ssh-keygen -F ssh.ohio.render.com -f ~/.ssh/known_hosts`
  (inspect the host-key record without changing it).
- Use Render's current documentation or dashboard independently to confirm
  the hostname and expected ED25519 fingerprint; investigate a mismatch.

Do not delete `known_hosts`, accept an unfamiliar key, disable
`StrictHostKeyChecking`, disable additional host-key verification, or
modify SSH settings merely to hide the message. Any production migration
remains blocked pending host-key review.

## Rollback, privacy and release

All additions are dormant modules and synthetic fixtures. No live database
schema change is performed by this release (unless a separately authorized
tenant-only setup is explicitly called in a safe environment). The existing
Observe worker, Public credential, single-owner browser/API settings, bank
transfer controls and encryption backups remain unchanged.

The GitHub release can be merged after all CI passes, but a successful merge
does not authorize production migration, active multi-account rollout or
Android APK replacement.
