# EdgePilot v0.2.23 — Disconnected disk-backed safety rehearsal

**Status: INACTIVE TEST-ONLY CODE.** Nothing here connects to real Public, activates
a new brokerage account, changes a production database, serves an HTTP route,
executes a trade, starts a worker, transfers funds, or changes the Android APK.

## Why this exists

v0.2.22 persists its synthetic emergency stop and account budgets inside
verified /dev/shm SQLite. The guard survives the reconstruction of a controller
object but is erased by a host restart. v0.2.23 adds a **separate** local,
disk-backed, disposable SQLite fixture to test restart-surviving safety state
and atomic writes across several unrelated Python processes. Neither component
is a production-durable safety service.

The module is backend/engine/tenant_public_durable_safety_rehearsal.py. It is
not imported by the production Flask API, Observe worker, Android, live Public
HTTPS code or the earlier test adapters. The static tenant_route_audit.py check
prohibits accidental production imports.

## Strict synthetic fixture rules

- Only an explicitly created **empty**, mode-0700 owner-controlled temporary
  directory under Linux /tmp or /var/tmp, also inside the configured OS
  temporary root, is eligible. Redirecting TMPDIR to /data or a nonstandard
  mount fails closed. It never uses Render's persistent /data, the real
  EdgePilot database or a brokerage credential store.
- The database and synthetic-only sentinel are mode-0600 owner files.
  Symlinks, absent files, changed ownership/mode, missing sentinel, missing
  SQLite schema, invalid state or corrupted SQLite all fail closed.
- Creation requires the exact fixture phrase. Opening an existing fixture
  NEVER creates or resets it, so a mistaken restart cannot erase a stored stop.
- The test accepts only canonical UUID-style *fake* owner/account identifiers,
  which do not come from Public. No real identity session, token, secret,
  account number, provider response or investment payload is stored.
- A new explicitly created fixture starts fresh and cannot prove the status
  of any prior fixture. Losing the disk, switching directories, restoring an
  old disk image, cloning a replica or manually manipulating the DB all
  defeat production stop assumptions. This is why activation remains blocked.

## Concurrency, admission and revocation

SQLite BEGIN IMMEDIATE serializes synthetic admissions, pauses, revocations,
manual pause clearance, and emergency stops across independent processes.
Every guard reads the same on-disk state. A simulated admission is capped at
two/account and ten globally per rolling 60 seconds. The SQLite connection
uses FULL synchronous durability, closes on initialization/verification failures,
rejects backwards clocks for both admission and lease revalidation, prunes
expired leases on new admission, and fails closed on errors or lock timeouts.

Admission returns a **fake, ten-second lease** with the guard epoch and the
account revision. A later explicit revalidation denies leases after pause,
revocation, emergency stop, expiry or version change. The pause may be cleared
only with an exact test phrase plus the current expected revision. Revocation
has no un-revoke method. A stopped fixture is one-way through the public class
API and through test SQLite triggers; audit records also reject deletion or
rewrites. Auditing stores only event type and integer timestamp, not identifiers.
A stopped fixture remains available for a redacted read-only incident summary;
this does not permit resumption or network access.

**Important race limitation:** an admission or revalidation can finish before
a concurrent stop. This does NOT ensure that a network request is cancelled
after the stop. There is no network request in this module. Real deployment
needs execution-side fencing, cancellation/draining of in-flight work,
distributed consistency, replicated and highly available durable storage,
startup behavior during outages, regional failure testing and alerting.
Local SQLite is NOT a multi-node consensus or high-availability control.

## Acceptance tests

The isolated v0.2.23 suite tests:
- a stopped fixture reopened by an independent Python process;
- concurrent multi-process quotas and per-account fairness;
- global quotas, stale clocks, wrong-owner and revoked account refusal;
- pause and revision-fenced manual recovery with stale lease invalidation;
- expired leases and incomplete/corrupted/deleted fixture refusal;
- failure to unstop or delete audit records through ordinary SQL;
- redacted audit summary; no production import and disabled live Public network.

The GitHub full Python, compile and JavaScript tests must pass on the pull
request and again after merging before calling the milestone complete.

## Future prerequisites (not approved by this release)

Actual production safeguards would require an independently approved safety
architecture: secrets-free replicated storage, fail-closed shared start/stop,
worker request gate, fencing for stale processes and account revocation,
observable incidents, runbooks with operators and on-call coverage, audited
break-glass controls, and rollback drills. Public's Individual API ownership
and personal/noncommercial terms also need independent review. All legacy
single-owner Flask/worker cutover blockers remain.

No real Public credentials, production deployment, new owners, user enrollment,
trade order methods, financial transfers, or protected encrypted backups are
modified. Reverting this code needs no production data rollback.
