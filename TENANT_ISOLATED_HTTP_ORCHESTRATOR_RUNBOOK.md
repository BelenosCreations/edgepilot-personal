# EdgePilot v0.2.18 — Isolated HTTP tenant routing and synthetic orchestrator

**Status: test-only.** This release contains real Flask request handlers and
a bounded tenant observation batch, but neither is mounted in the live
application nor authorized to connect to Public. The test factory refuses
startup without an explicit test environment gate and a verified detached
SQLite database on **real /dev/shm tmpfs**. No production migration, new
account enrollment, active background worker, brokerage quote request,
transaction, live trade, funds transfer or Android APK update.

## Real HTTP routing in a detached test app

`backend/engine/tenant_test_http.py` exposes Flask handlers for
`/tenant/accounts`, `/tenant/selected`, and
`/tenant/accounts/<uuid>/{summary,history,details,references}` **only inside
the independently instantiated test Flask app**. It delegates all identity,
account selection and scoped reads to the existing
`DormantRequestBoundary`/`DormantAccountGateway` layers.

The integration test exercises real Flask/Werkzeug HTTP handling, parsing
and response behavior including:
- An HTTP cookie with tenant-identity token is required (no client-supplied
  user ID or bearer authorization fallback).
- Secure HTTPS and an exact synthetic Host; mutating operations require
  exact Origin, same-site fetch metadata, and identity CSRF header.
- Mutation accepts a constrained JSON object; only one canonical account
  UUID is allowed. Unknown routes/actions and cross-account reads fail.
- GET views accept only allowlisted pagination parameters with strict
  bounds. Invalid/encoded paths, duplicate query values and oversized
  payloads are refused.
- No-store, no-cache, no-framing, no-sniff and strict CSP response headers;
  no CORS credentials or public origin authorization.
- Independent sessions on different phones can select different accounts,
  and logouts/connection revocations invalidate future reads.

These checks are **not a complete deployment security audit**. Before a real
HTTP route could ship, review TLS termination/proxy trusted headers, CSRF
bootstrap, cookie issuance/SameSite/Secure rules, login rate limiting,
concurrency, slow-body controls, request smuggling, account ownership,
error logging, traffic monitoring and tested external penetration methods.
Neither this test app nor its origin should ever be publicly hosted.

## Bounded, offline multi-account observation orchestration

`backend/engine/tenant_test_orchestrator.py` implements one synchronous,
explicitly invoked pass over a fair per-owner quota of account-scoped
disabled observation slots. It requires an approved **offline synthetic
batch** phrase and verified `/dev/shm` storage.

Each account's watchlist and connection are revalidated before the
simulation. A stale or revoked account is rejected independently without
blocking other valid accounts; an unexpected DB/programming error is
propagated rather than falsely declaring success. Synthetic observations
record **NO_DATA, 0 accepted quotes, 0 rejected quotes**. No worker
scheduler, network client, Public credential, quote fetcher, trading
execution adapter or banking operation is imported. The results clearly
report zero provider calls and zero order submissions.

This is not evidence of real-time monitoring performance or successful
Public authentication. Live Observe continues on the existing legacy
single-owner architecture.

## Safety and release boundaries

- `tenant_route_audit.py` rejects accidental imports of the isolated
  test HTTP app or orchestrator into live `backend/app.py` or
  `backend/engine/automation_worker.py`.
- Version and changelog changes affect release metadata only.
- No new tables are created in production: the tests initialize synthetic
  tenant tables only in their private temporary SQLite databases.
- No full-history import or identity cutover is authorized.
- All legacy selected-account settings and live monitoring remain unchanged.
- Real Android account switching and per-account background monitoring
  require separate development and explicit deployment approval.
- The previously saved Android SSH settings remain
  `StrictHostKeyChecking yes` and `UpdateHostKeys no`.
  The separate non-post-quantum SSH key exchange warning remains documented;
  this release does not change SSH settings.

## Test acceptance and next blockers

GitHub CI must pass all Python/Flask route tests, source compilation and
browser JS checks before merge. Test fixture validations include two owners,
one owner with multiple accounts, separate phone cookies, foreign-account
requests, forged ID/query/CSRF/Origin, revoked sessions, worker owner fairness,
rejected stale accounts, and precise synthetic replay counts.

Even after CI, **production cutover remains blocked** by unconverted legacy
API routes and the single-owner worker, Public owner verification, credential
life-cycle, device enrollment, complete migration/rollback and user-facing
account controls. A future isolated rehearsal against the encrypted backup
requires separate user approval before any operational changes.
