## Phase 12 (v0.2.18): Isolated Flask tenant routes and offline account worker orchestration

A new test-gated Flask factory exercises *real HTTP request handling* for
the session-authorized tenant request contract, exclusively with verified
memory-backed synthetic databases. A synchronous, fair per-owner test
orchestrator performs only zero-quote synthetic account observations.
Neither is imported into the live API or Observe worker. Production
account cutover and trading remain prohibited. See
TENANT_ISOLATED_HTTP_ORCHESTRATOR_RUNBOOK.md for test-only limits and blockers.


# EdgePilot v0.2.17 — Dormant tenant request/worker boundaries

**INACTIVE DEVELOPMENT ONLY.** No live multi-account API or per-account
production observer. No production database migration, new identity, broker
API call, new Android APK, quote retrieval, paper or live execution, or
financial transfer. Existing single-account Observe worker remains unchanged.

## Explicit future request boundary

`backend/engine/tenant_request_boundary.py` is a deliberately unregistered
application-service contract built on the v0.2.16
`DormantAccountGateway`. It is **not** a Flask router or a new HTTP API.

An explicit allowlist accepts only:
- GET /tenant/accounts
- GET /tenant/selected
- POST /tenant/selected (exact account_id and valid identity CSRF)
- DELETE /tenant/selected (valid identity CSRF)
- GET /tenant/accounts/{uuid}/summary
- GET /tenant/accounts/{uuid}/history
- GET /tenant/accounts/{uuid}/details
- GET /tenant/accounts/{uuid}/references (bounded paging)

Every operation derives the user exclusively from an authenticated tenant
identity session. Paths and account IDs are canonical; unknown HTTP methods,
user IDs supplied in payloads, extra query arguments, encoded/ambiguous
paths, non-account routes, order submission and transfers fail closed.
Selection is session-local and never updates the legacy account setting.

**IMPORTANT:** Pure request-dispatch tests do not establish production HTTP
security. Before exposing these routes, engineers must independently review
authentication cookie flags, origin and CSRF enforcement, TLS, reverse proxy
headers, rate limiting, JSON/body size, request/session lifetime, security
headers, audit logs, account-scoped SQL and racing revocations. Do not treat
the dormant contract as authorization to register Flask endpoints.

## Inactive worker admission boundary

`backend/engine/tenant_worker_boundary.py` assembles fair, deterministic
observation planning slots based on verified tenant accounts. It enforces a
global number of planned accounts, a per-owner cap, known disabled-only
runtime states and account-specific watchlists. It never schedules a cycle,
fetches a real quote, decrypts a Public key, starts a worker or places trades.

The only optional replay delegates to the already isolated, memory-backed
**synthetic** Observe fixture. It rechecks the account, connection and
watchlist before writing a NO_DATA/zero-quote observation to the disposable
test SQLite file. It does not establish real worker health or a trading
signal. Runtime start, enqueue and submit_order are explicitly denied.

The active legacy worker continues using a global selected account.
The route audit rejects accidental imports of either dormant boundary into
`backend/app.py` or `backend/engine/automation_worker.py`, and still reports
`crossAccountProductionCutoverAllowed=false`.

## Security tests

Synthetic regression tests cover two owners with distinct Public connections,
two accounts under one owner, two independent Android sessions, revoked
sessions/credentials, other-account lookup denial, forged/encoded paths,
account ID and query injection attempts, CSRF on selection changes,
read-only history metadata, deterministic per-owner account quotas,
changed watchlist and revoked-connection revalidation, zero real quote calls,
and unchanged legacy selected-account settings.

These are additive API and worker **contracts**, not complete production
tenant isolation. A full migration requires separately authorized route and
worker refactors, real Public owner-verification, concurrency/rate limiting,
end-to-end authorization, tested rollback and safe Android account switching.

## SSH security posture

The EdgePilot-specific Render Ohio SSH settings were verified separately:
`StrictHostKeyChecking yes` and `UpdateHostKeys no`. This resolved the
additional host-key update proof warning in a one-time connection test.
A separate warning persists that the negotiated SSH key exchange is not
post-quantum. v0.2.17 changes **no** SSH settings or trust records.

## Release and rollback

This release only adds dormant modules and tests, updates version information
and documents future cutover blockers. Its new modules are not imported or
set up by live Flask/worker startup; no old database or runtime mode is
modified. Rolling back the GitHub/Render code release would not require a
data migration, because no production schema work is performed here.

Never read this document as a green light for new Public accounts, live
monitoring or trading. Explicit authorization is required for every later
production change.
