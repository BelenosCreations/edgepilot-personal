# v0.2.104 — Offline synthetic operator recovery evidence (inactive)

This document describes a **read-only operator decision rehearsal**, not
live brokerage execution, production paper fills, or a recovery procedure
approved for production. The module
`backend/engine/tenant_paper_latch_operator_evidence.py` is not imported
by Flask, a paper-fill writer, a broker adapter, or background workers.

## What the evidence authenticates

An independent **operator HMAC key** (separate from both the synthetic
journal HMAC key and the checkpoint anchor key) authenticates a complete
sequence-numbered, chained evidence record. Every record includes:

- The independently anchor-HMAC-authenticated all-account checkpoint,
  its epoch, and the journal key's stable identifier (never the secret).
- The last record MAC, monotonically advancing sequence, and the exact
  externally retained **latest tip** required for full-chain verification.
- A state: `ACTIVE`, `ROTATION_PENDING` or terminal `QUARANTINED`.
- For a pending rotation, the exact before/after authenticated ticket,
  next journal key identifier, and precommitted next checkpoint.
- Monotonically accumulated compromised-key identifiers and an explicit
  reason for a quarantine record.

This establishes no independent durable witness by itself. The caller MUST
publish the complete operator record chain and latest tip in protected,
independent custody, and must verify that the supplied latest tip really
is the latest. A rollback of *both* fixture and externally entrusted tip
is not detectable, nor is compromise of the external operator signing key.
A hash, timestamp or process memory is not a hardware monotonic counter.

## Offline operating sequence (no activation)

1. Independently retain journal, anchor and operator keys. Use only
   verified Linux `/dev/shm` synthetic fixtures. Confirm that no
   production or real Public account data is present.
2. Verify the current whole-fixture checkpoint. If creating the very
   first operator record, use `genesis_tip()`, then
   `propose_synthetic_operator_record(status="ACTIVE", ...)`.
   No later record may use the genesis tip. Independently publish the
   returned record and `proposedLatestTip` **before** trusting them.
3. For additional simulated account events, make a new, independently
   anchor-authenticated full checkpoint and propose a new `ACTIVE`
   record. It must retain the entire account inventory, must not
   decrease the authenticated event count, and may not silently change
   the journal-key epoch. Independently publish the new latest tip.
4. For journal-key rotation, independently pin the separately signed
   before/after rotation ticket *first*. Propose and independently
   publish a `ROTATION_PENDING` record referencing it before any
   SQLite re-MAC transaction. Without such external publication do
   **not** execute the rotation.
5. Execute only the precommitted offline synthetic rotation. Inspect
   the candidate with `inspect_synthetic_recovery_candidate`.
   `NEW_STATE_NEEDS_INDEPENDENT_PROMOTION` still requires independent
   verification before the operator proposes a new `ACTIVE` record.
   `OLD_STATE_AMBIGUOUS_QUARANTINE` may mean a precommit crash **or**
   a postcommit rollback. Never infer that the old file is safe,
   retry rotation automatically, restore a stale archive or reset stops.
6. If the independent operator suspects rollback, compromise or
   indeterminate evidence, propose `QUARANTINED` with a specific
   reason; optionally append the key identifier to `revokedKeyIds`.
   Publish this new record and tip separately. This policy is terminal:
   it deliberately contains no automatic unquarantine or reactivation.
   Any recovery from terminal quarantine needs a new, independently
   authorized, separately designed protocol and audit.

Always run `verify_synthetic_operator_evidence` against the latest
externally entrusted tip, not a tip reconstructed solely from the
database, the source code, or a possibly stale archive. Never store
operator keys, plaintext account data or encrypted backups in a public
GitHub repository, logs, or source-controlled test fixtures.

## Important refusal semantics

`PINNED_STATE_VERIFIED_NO_ACTIVATION` only means the offline synthetic
database matches the current independent signed operator evidence.
`NEW_STATE_NEEDS_INDEPENDENT_PROMOTION` means the exact pending
post-rotation chain was observed; the promotion record and latest-tip
publication are still separate operator responsibilities.
`OLD_STATE_AMBIGUOUS_QUARANTINE` requires external review, never an
automatic endorsement of a pre-rotation database.
`QUARANTINED_NO_RESTORE` means the operator evidence has a terminal
hold (including suspected compromised keys).

All dispositions return `executionEnabled=False`,
`productionPaperFillsEnabled=False` and
`operatorApprovalRequired=True`. A failed integrity check, wrong key,
missing tip, forged record, altered checkpoint, old archive, truncated
record chain or unsupported transition refuses without returning secrets.

## What this milestone does not solve

- No durable append-only operator evidence store, external quorum,
  key-revocation infrastructure, monotonic hardware epoch or
  cryptographic proof of storage publication.
- No atomic multi-resource commit joining SQLite, encrypted archives,
  external latest-tip publication and durable recovery after host crash.
- No single-transaction integration between paper ledger fills, idempotent
  request decisions, protected-balance spending ceilings, position basis,
  account-specific realized losses and sticky stop-latch enforcement.
- No proof of market-data caching, redistribution, paper-fill rights,
  future price returns, autonomous order safety or production authorization.
- No change to Render service, 1 GB disk, credentials, Public connections,
  tenant/account storage, Android releases or owner-accepted snapshots.

Run focused tests from `backend`:

```bash
python -m unittest discover -s tests -p 'test_tenant_paper_latch_operator_evidence_v02104.py' -v
```

Tests cover two synthetic users and three isolated accounts, historical
latch persistence, old whole-file rollback, stale external tips,
interrupted HMAC rotation, ambiguous pre-/postcommit old state,
authenticated pending transitions, explicit promotion,
compromised-key quarantine, HMAC tampering and prohibition on production
imports or non-tmpfs access.

Next: independently review a dormant transactionally consistent
paper-fill/latch design with full account scoping and exact-cent cost-basis
accounting. Keep all production execution gates disabled until explicitly
authorized following independent verification.
