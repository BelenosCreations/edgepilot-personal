# v0.2.102 — Precommitted offline synthetic rotation recovery ticket

**Status:** INACTIVE TEST REHEARSAL. This does not enable paper fills,
autonomous/live orders, bank transfers, retained brokerage quote usage, any
production migration, HTTP route, additional paid service or Render change.

## Why this exists

v0.2.101 can reauthenticate synthetic latch journals under a new HMAC key
inside a SQLite transaction, but the operator's **independent** checkpoint
update is a different operation. A crash may happen after the SQLite commit
but before the new checkpoint is published, leaving a dangerous ambiguity.

The new isolated module
`backend/engine/tenant_paper_latch_rotation_ticket.py` lets a trusted
offline operator prepare an **authenticated before-and-after ticket** before
starting the write. It verifies the current, previously independently pinned
whole-fixture checkpoint, replays every synthetic user/account journal,
predicts the entire new-key MAC chain **without mutating the database**, and
produces a ticket signed by the distinct external anchor key. The predicted
new checkpoint includes *all* registered users/accounts, sticky latches,
integer-cent state, journal counts and the exact next key epoch.

An operator must durably save that ticket to an independent, protected
location **before** starting the rotation. This module does **not** persist
or validate the external publication. A ticket kept only in the process,
the same `/dev/shm` tree, or the restorable SQLite database is insufficient.
Do not log the keys, user/account records, or account-specific paper data.

## Synthetic rehearsal procedure

1. Hold independent journal-old, journal-new and anchor HMAC keys. Confirm
   operator access to the **current** trusted, separately saved checkpoint.
2. Call `prepare_synthetic_rotation_ticket` and securely publish the ticket
   outside the database, independently from the original checkpoint. Ensure
   only an exact +1 key epoch is proposed.
3. Only after that publication, call `execute_synthetic_prepared_rotation`
   with the exact ticket. The function checks the same proposed transition
   against the still-current fixture, then invokes the existing single
   `BEGIN IMMEDIATE` authenticated re-MAC transaction. A mismatch or injected
   pre-commit failure refuses the write.
4. After normal commit, verify the returned next checkpoint against the
   fixture and obtain independent operator approval before externally
   promoting it. Retire the old journal key and any applicable older backups
   through a separately verified external process.
5. If the process crashes or reports an uncertain outcome, call
   `inspect_synthetic_rotation_outcome` with the **externally retained**
   ticket and both keys. `NEW_STATE_VERIFIED` means the exact prepared new
   HMAC state exists. `OLD_STATE_AMBIGUOUS` means the old state verifies but
   **it may be either a precommit failure or a rollback after commit**.
   Neither result authorizes fills or automatic changes. If neither matches,
   fail closed and quarantine the fixture for independent review.

A key safeguard: **never automatically retry a rotation, reset a latch or
accept a restored old fixture because OLD_STATE_AMBIGUOUS was returned.**
The operator must investigate external audit evidence and the last known
trusted checkpoint. A malicious rollback after commit can look exactly
like a crash before commit when only a prepared ticket survives.

## Remaining production gates

External storage for monotonic pinned epochs and key revocation, crash-safe
durable recovery with explicit commit/publication coordination, stale backup
quarantine, authenticated session and scope binding, confirmed market-data
rights, exact position/protected-balance accounting under the same transaction,
and formal independent activation approval are **not solved**. Linux
`/dev/shm` fixtures are ephemeral; the module cannot access or modify the
existing Render Starter service, 1 GB disk, secrets or brokerage accounts.

Run focused tests from `backend`:

`python -m unittest discover -s tests -p 'test_tenant_paper_latch_rotation_ticket_v02102.py' -v`

The tests exercise two users/three accounts, predicted vs committed MACs,
sticky-loss preservation, precommit rollback, postcommit stale-fixture
ambiguity, stale/mutated tickets, wrong keys, invalid epochs and isolation
from Flask and the dormant paper writer. Owner brokerage snapshot/quote
acceptance need not be repeated.
