# EdgePilot v0.2.19 — Controlled fake Public account binding and offline recovery

**Test-only. Inactive. Not a production Public account ownership verifier.**

The owner-authorized v0.2.19 development adds a controlled, fully local
synthetic Public adapter, a per-account recovery latch, a one-pass fake
provider binding rehearsal, and a static inventory of legacy global-account
dependencies. This release does not make any actual provider request,
decrypt credentials, enroll real users, trade, transfer funds, schedule a
worker, migrate any production database or change the Android app.

## Controlled fake Public account contract

`tenant_test_public_binding.py` accepts explicit `user_id`, `account_id`
from a trusted test caller and uses `AccountScopeStore._check` to require
an active account owned by that user with a non-revoked connection.

It compares the already linked database account reference and its exact
connection ID against a **manually supplied in-memory fake provider
fixture**. It does not call Public, receive a provider-signed claim, prove
that a real human owns the account, or authorize account linking. The
result is always marked `real_public_ownership_verified=False` and has
zero network calls and zero orders. A mismatch fails closed and exposes
no credential ciphertext or raw account data in errors.

This is a useful test of **binding and attribution logic**, not real
provider ownership. Actual ownership verification requires a separately
designed authenticated read-only Public API adapter, documented provider
semantics and permission review.

## Per-account synthetic recovery gate

`tenant_test_recovery.py` runs only on verified detached SQLite in real
`/dev/shm` and creates a test-only recovery table. A binding failure
latches that exact `user_id/account_id` into PAUSED. No other account is
paused. A manual synthetic-only review with an exact approval phrase
and current revision moves it to CLEARED_SYNTHETIC_ONLY. Revision fencing
rejects stale approvals, and a new failure relatches the account.

A cleared account may only run a future **synthetic** NO_DATA test. No
automatic resumption, real Public recheck, live worker operation, trade
or funds transfer is authorized or available. Revoked accounts cannot
read, update or clear their recovery status.

`tenant_test_binding_rehearsal.py` combines controlled fake binding with
the preexisting detached worker slots. A mismatch pauses only that
account, while valid accounts may complete their zero-quote local
observation. Revoked accounts fail closed, and programming/database
errors do not become false successes. Results explicitly report zero
real Public ownership proofs, zero network calls and zero orders.

## Replacing global dependencies — test path only

The offline path calls the account planner and worker using explicit
`user_id/account_id`, **never** `selected_account()`. The static
`tenant_legacy_dependency_audit.py` separately counts global account
calls in the existing Flask app and legacy monitoring worker.

This is a preparation for removing single-owner assumptions, not an
actual replacement in the live app. v0.2.19 intentionally changes no
production API route or worker. Global dependencies remain an explicit
blocker for any real multi-account cutover.

## Security and rollback

- All synthetic test databases must be detached, located under verified
  RAM-backed /dev/shm, with no active WAL. Real production /data databases
  are rejected by the test components.
- No production schema preparation or identity activation is performed.
- No credentials, recovery keys, device SSH configuration or broker
  account references are copied outside isolated fixtures.
- An explicit synthetic-only test approval is required per rehearsal.
- All new modules are blocked from being accidentally imported into the
  live Flask server or legacy automation worker by
  `tenant_route_audit.py`.
- Legacy settings, background Observe worker, account secrets and
  encrypted November 9 backup remain unchanged.
- Rolling back a code-only inactive deployment requires no database
  reversal because none of these modules is invoked at application
  startup; synthetic fixtures are disposable.

## Required future approval gates

Before any real provider ownership check or actual per-account workers:
review current Public API contracts; verify read-only authentication
mechanics and account ID semantics; prevent forged binding, cross-owner
reuse, key leakage and replay; test rate limits, provider outages and
revocation; establish audit trail and emergency shutoff; and rehearse
a reversible cutover with independently verified backup. Android account
switching, real multi-account API isolation and live worker segregation
remain inactive.

The verified Android SSH host identity and host-specific
`StrictHostKeyChecking=yes` / `UpdateHostKeys=no` configuration are
unchanged. The separate non-post-quantum key exchange warning remains.
