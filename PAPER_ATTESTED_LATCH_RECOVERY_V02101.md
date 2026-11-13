# v0.2.101 — Offline independent synthetic loss-stop checkpoint and key rotation

**Activation status: research-only / disabled.** This is not production paper
trading, actual risk enforcement, a backup/restore service, live brokerage
trading or an authenticated HTTP endpoint. Neither live orders nor transfers
are enabled.

## Trust boundaries

`backend/engine/tenant_paper_latch_attestation.py` is separate from Flask,
the dormant `tenant_paper_ledger.record_paper_fill`, Public connections,
Render's persistent database, broker secrets and production workers. Its only
data input is the original isolated synthetic SQLite latch fixture on verified
Linux `/dev/shm` with owner-only `0600` and one hardlink. All user/account
UUIDs and monetary events are fictional. The fixture never holds HMAC keys,
market quotes or brokerage orders.

Two **independently held** 32–128-byte keys are required: (1) the journal HMAC
key from v0.2.100; (2) a separate checkpoint-anchor HMAC key. Never put either
key in the repository, scratch database, Render settings or printed logs.
The independently authenticated checkpoint is a complete-inventory pin:
sorted user/account policies, current and worst realized integer cents,
sticky-latch state, sequences and final journal MACs. Each account journal is
fully replayed before a checkpoint is issued or accepted. Orphan journal
scopes are refused, and a missing entire policy account is detected against
an **already pinned external checkpoint**.

A trusted external operator must separately preserve the **latest** checkpoint
and its monotonic epoch. Given that latest pin, `verify_synthetic_checkpoint`
rejects a deleted/modified account, appended/missing journal entry, wrong
journal or anchor key, forged pin or whole-database snapshot rolled back to an
older valid HMAC chain. A checkpoint that an attacker can roll back **along
with the database** cannot prevent rollback. The `make_synthetic_checkpoint`
function is a research primitive; do not run it on untrusted restored data
and automatically trust its output as a new pin.

## Atomic journal-key rotation rehearsal

`rotate_synthetic_journal_key` requires an exact, externally pinned snapshot
and an epoch increment of exactly one. `BEGIN IMMEDIATE` authenticates every
scope with the old key, then re-MACs all policy and event chains with a
distinct new key inside the **same SQLite transaction**. It verifies all
new chains before commit. Injected failures roll back every update. After
successful commit, the old journal key fails to verify the current fixture,
and the returned pin is authenticated with the *separate unchanged* anchor
key at the new epoch. The operator must independently promote this new pin
and retire the old key. Old backup copies may remain readable by a holder of
the old key: this is **not cryptographic key destruction or centralized
revocation**.

There is an important unclosed crash window: a process may commit the SQLite
rotation and crash **before** the independent anchor publication. Treat this
as locked/recovery-required, not permission to bypass verification, re-pin an
unknown fixture, or revert to a former epoch. No automatic crash reconciliation,
hardware monotonic counter, durable operator anchor store or atomic cross-store
commit exists here. `/dev/shm` itself does not survive host reboot.

## Dormant paper-ledger integration design — NOT implemented

A future *licensed and explicitly approved* account-scoped paper writer must
use one durable tenant/account transaction for identity authorization,
idempotency, stop policy and latch, event insertion, wallet cash, cost basis,
positions, realized P&L and protected-balance/per-trade checks. Derive the
principal only from an authenticated server session. Acquire the same account
write lock before reading the stop and holdings; reject stale or conflicting
request IDs; replay existing outcomes without producing a second fill. A
previously accepted OPEN/admission decision from this offline rehearsal must
**not** later be interpreted as authorization for a fill. A BUY after a
latch must be rejected; SELL/liquidation reconciliation must have a
separately audited policy that cannot increase risk. Balance protection is
0–99% of designated paper funds, not real brokerage cash. Loss-stop checks
must include historical worst realized P&L, and specify whether licensed
unrealized marks can ever be used; never fabricate them. Key epochs, recovery
anchors, shutdown/restart guarantees, backups and independent operator
attestation must be part of the *same* reviewed safety design.

Before any activation: confirm market-data caching/usage rights, trusted
authentication and account scope, durable backups and restore rehearsals,
external monotonic checkpoint storage and key retirement, atomic lock
ordering with the real paper ledger, recovery from process/power failures,
race/idempotency/fraud tests, and explicit operator approval. Nothing in
v0.2.101 satisfies those production gates.

## Offline tests

Run from `backend`:

`python -m unittest discover -s tests -p 'test_tenant_paper_latch_attestation_v02101.py' -v`

Tests cover two users/three accounts, sticky historical losses, changed
accounts, orphan rows, missing entire policies, wrong/tampered pins, whole
SQLite rollback with otherwise valid journal MACs, independent key refusal,
atomic multi-scope journal re-MAC, invalid epoch, stale input, and injected
pre-commit rollback. No real Public request or owner acceptance retest is
needed.
