# v0.2.105 — Offline single-transaction synthetic paper accounting and stop

**Never activate this as a production paper writer.** This milestone is
an independent rehearsal of how a future identity/account-bound paper
wallet, protected spend, position cost basis, realized P&L, sticky
realized-loss stop and request idempotency might share **one** SQLite
transaction. It does not modify the existing
`engine/tenant_paper_ledger.py`, the account-scoped latch experiment,
Flask routes, Public connections, Render disk or user records.

## Isolated implementation

`backend/engine/tenant_paper_atomic_rehearsal.py` can only create a
**brand-new**, 0600 owned SQLite fixture under the verified Linux
`/dev/shm` tmpfs. It refuses other filesystems, symlinks, renamed
existing fixtures and non-matching marker/schema. Plaintext is never
written into a production database. The module is not imported by
production Flask, dormant paper-fill routes, or brokerage adapters.

Each offline synthetic wallet has immutable seed, protected percentage
(0–99), spend cap, per-trade cap and realized-loss limit. A separate
HMAC journal key authenticates the immutable policy, the current wallet
and all current account positions, plus an ordered append-only
request-id journal. Before each request, the entire account's history
is replayed and checked against these MACs. A single `BEGIN IMMEDIATE`
transaction then performs all operations:

- Verify that this synthetic identity/account actually has a registered
  policy; reject a foreign user/account pair.
- Return the original committed result on an identical request ID,
  while refusing changed arguments under the same ID. Historical cash
  is labeled separately from current cash.
- For BUY, deny if any historical realized-loss breach latched a stop.
  Enforce cash, per-trade cap, spend cap and
  `floor(seed * (100 - protected_pct) / 100)` outstanding cost-basis
  exposure. No negative cash, margin or short selling.
- For SELL, limit units to existing assumed holdings, conservatively
  round **up** the basis released on partial sales, compute integer-cent
  realized proceeds and P&L, and update the worst historical cumulative
  realized P&L. A loss equal to or beyond the limit latches a stop
  permanently. Assumed sells may liquidate positions while stopped;
  subsequent gains never clear a prior breach.
- Write wallet cash, position units/basis/realized P&L, event, request
  fingerprint, authenticated MAC chain, historical worst loss and stop
  latch before the **same** SQLite commit. An injected precommit failure
  rolls back *all* of these changes. Concurrent writers serialize under
  the SQLite immediate transaction; the same request ID cannot create
  multiple successful simulated fills.

All prices are manually fabricated integer cents and all units are
**whole-unit only**. There is no market-data provider, source attribution,
real fill observation, execution adapter, fee quote or market-data right
assertion. This synthetic scope intentionally does **not** attempt to
implement production Decimal fractional shares, corporate actions,
real-world slippage, open-order accounting or quote freshness. The
existing dormant paper writer retains its separate, stricter
source-attributed observation gate.

## Independent whole-fixture checkpoint

`make_synthetic_atomic_checkpoint` HMAC-attests **all** fixture
user/account states and event counts under a separate anchor key,
returning a checkpoint with explicit caller-selected epoch.
`verify_synthetic_atomic_checkpoint` checks a fixture against the
**latest independently trusted** checkpoint provided by an operator.
It rejects missing accounts, altered signed events/positions, old
backups and wrong keys **when a newer independent pin survives**.

The module does not store or durably advance the pin. An attacker who
can roll back both the database and the trusted pin may defeat this
experiment. Between a local SQLite commit and external checkpoint
publication there is an unsafe ambiguity; neither `make` nor
`verify` repairs that gap. No journal-key rotation protocol has been
connected to this new schema, and no implicit production integration
with the v0.2.100–104 loss-stop or operator evidence modules exists.

## Test and risk review

Run in `backend`:

```bash
python -m unittest discover -s tests -p 'test_tenant_paper_atomic_rehearsal_v02105.py' -v
```

Tests cover two synthetic users/three accounts, sticky historical
losses followed by gains, conservative partial sells, cash and
outstanding cost-basis protected budgets, request-id conflicts,
historical retry balances, interrupted writes, concurrent duplicate
requests, concurrent protected-budget competition, whole-file
rollback with a latest independent checkpoint, journal/position tamper,
absent wallet and forbidden disk paths.

## Production activation blockers

1. **Identity:** Actual principal must derive from a verified server
   session, and disabled/revoked accounts must be enforced at the same
   transaction boundary. The synthetic UUID arguments alone are not
   authorization.
2. **Licensing:** The existing source-attributed `Observation`
   freshness and persistence-rights gates must be retained and verified
   before any actual paper data is persisted. No rights are inferred.
3. **Accounting:** Integrate the real dormant Decimal fractional-unit
   accounting and protected balance limits with durable stop and
   request journaling, in one account-scoped production transaction,
   without unsanctioned migrations or replacing the deployed database.
4. **Recovery:** Independently durable monotonic checkpoints, backup
   retention/key custody, compromised-key quarantine, crash-safe
   publication and operator approval remain unresolved. tmpfs is
   ephemeral and synthetic testing cannot establish host-crash safety.
5. **Verification:** Independent, negative, concurrent and failure
   injection testing must pass on a separately reviewed design and
   operator-controlled staging environment. No real market orders,
   automatic paper fills, transfers or brokerage execution are allowed
   without explicit activation approval.

No new paid services, Render deployment configuration changes, disk
migration, live trading or account data changes are included.
