# EdgePilot v0.2.24 — Offline synthetic work-stage fencing

**Release classification: code-only, disconnected test rehearsal.**
No Public credentials, real broker calls, account activation, live order execution,
fund transfers, background worker launch, Android changes or production migration.

## Purpose

The v0.2.23 disconnected SQLite fixture enforces atomic admission, account pause,
revocation and emergency stop. That does NOT guarantee that downstream work
will cease if a stop happens after a prior lease validation.

v0.2.24 adds backend/engine/tenant_public_offline_work_gate.py, a STRICTLY
synthetic work-progress ledger on the already isolated v0.2.23 fixture.
Every stage is a database write only: no injected callback, market scan, quote
fetch, order operation, API client, broker account or real work is executed.

## Atomic order guarantee within one SQLite fixture

A fake lease from v0.2.23 must be bound to exactly one canonical synthetic
owner ID and account ID, have an unexpired lifetime and match the current
account and global safety revisions. All checks happen in BEGIN IMMEDIATE
alongside the stage record, allowing a concurrent emergency stop/pause/revoke
to serialize with a stage. If the stop commits first, the stage is denied.
If a stage commits first, it remains visible in historical test records and
is not undone. There is no impossible claim of canceling already completed
work.

The only permitted stages are BEGIN -> CHECK -> FINISH, each once per lease,
with strict previous-state and version checks. Out-of-order, duplicate,
unknown/free-text, expired, paused, revoked, cross-owner and stale operations
fail closed. A stage failure rolls back both progress and audit writes.
Idempotent retry or crash-resume is NOT provided. A new process can manually
present a still-valid fake lease, but no scheduler or automatic resume exists.

The test schema is installed *only* in an explicit private synthetic fixture.
DDL is executed under the same database transaction, using execute() rather
than executescript(), which would implicitly commit the guard lock.
The two test tables hold lease UUID, fake owner/account UUID, stage/revision
and an append-only event log containing ONLY the stage and integer timestamp.
Read-only redacted aggregate status remains available after a stop; no
identities, secrets, ledger entries or trading values are returned.

## Threat model and limits

This is **single-fixture ordering evidence**, not a real multi-node safety
service. Race-proof stop vs fake state write is not the same as cancelling a
network request, broker order, already dispatched worker, queued task, or
request in another region. The executable production worker is unchanged
and imports none of the rehearsal code. Static tenant_route_audit.py refuses
future accidental live imports of the gate in Flask and Observe worker.

Local disk cloning/rollback, corrupt database, abandoned leases, unavailable
disk, multi-host split-brain, third-party credential rights, malicious local
operators and broker-side execution require further architecture and review.
Actual broker identity/ownership verification and Public personal/noncommercial
terms also remain production blockers. No positive result here constitutes
real activation approval.

## Regressions and release checks

Tests include normal stage progression, duplicate/out-of-order rejection,
wrong owner/lease, pause/resume revision fencing, revoked accounts, invalid
clock, expired lease, cross-process exactly-once stage admission, race between
stop and final stage, stopped-state forensic summary, partial-write rollback
on missing audit schema, ordinary SQL audit rewrite denial, and static checks
proving no live HTTP/worker import and Public network still disabled.

Before publishing: PR Python/Flask/unit tests, compileall, JS syntax, plus
post-merge CI on main must succeed. Routine Render redeployment of the
unchanged execution model is authorized during approved development, but
activation of real brokerage or trading is not.

Rollback is source-only; there is no production schema/data migration. Existing
encrypted backups and Android installation are unchanged.
