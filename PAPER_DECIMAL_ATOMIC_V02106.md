# v0.2.106 — Dormant fractional-Decimal atomic accounting research

**Do not activate.** This is a NEW private 0600 SQLite fixture created only on
verified Linux `/dev/shm`. It does not read, replace, copy or migrate live
Render storage, real account identities, brokerage secrets or tenant records.
There is no Flask import, background worker, broker call, production paper fill,
autonomous/live order or bank action. Prices and quantities are fabricated
test assumptions; they are **not** Public or other licensed market observations.

## What changed

`backend/engine/tenant_paper_decimal_atomic_rehearsal.py` bridges the exact
Decimal boundary and cent-rounding functions of the existing dormant
`tenant_paper_ledger.py` to an independent transactional synthetic paper
model. Unlike the separate v0.2.105 whole-unit rehearsal, quantity may be
fractional (maximum scale 18 decimal places) and is normalized in the request
fingerprint. The new schema is purposely incompatible with production tables.

One SQLite `BEGIN IMMEDIATE` transaction first authenticates the immutable
per-scope policy, replays the entire HMAC-protected event chain, recomputes
current cash, position fractions, cost basis, realized P&L, worst cumulative
realized P&L and historical stop state, and compares every position with
its signed wallet state. It then either returns a matching historical
request's original balance, refuses a conflicting request, or commits cash,
position, event MAC and stop together. BUY rounds assumed all-in cost UP;
SELL rounds assumed proceeds DOWN and partial basis release UP. Protected
cost-basis exposure, spend caps and per-trade caps remain immutable. A
historically breached stop blocks subsequent assumed buys permanently but
permits liquidation of positions already held. No short selling or leverage.

The fixture requires externally held journal HMAC key bytes. An independent
anchor key can sign a candidate whole-fixture account inventory checkpoint.
Verification against a separately trusted **latest** checkpoint detects a
restored old fixture, missing account or altered state; it cannot provide or
advance that independent trust store itself. Account UUIDs label isolated
synthetic scopes and **do not prove authentication**. Real account access
must instead derive from a verified server session and check disabled users,
revoked connections and account ownership inside the final transaction.

## Focused testing

Run from `backend` on Linux:

```bash
python -m unittest discover -s tests -p 'test_tenant_paper_decimal_atomic_v02106.py' -v
python -m unittest discover -s tests -v
```

The focused suite tests fractional cost and basis rounding, realized sticky
losses and gain-after-stop liquidation, 2 synthetic users/3 accounts, immutable
policy and cross-scope refusal, normalized idempotent replay, invalid numeric
inputs, concurrent protected-budget contention and duplicate requests,
precommit crash injection/rollback, wrong keys, tamper, stale externally held
pin, missing accounts, forbidden disk paths and symlinks.

## Unsolved blockers

1. The prototype does not process actual source-attributed Observation
   evidence. No source rights, fresh timestamp, quote storage permission,
   spread, execution cost or slippage is verified by fabricated inputs.
   Retain the existing `Observation.validate` and explicit cache-rights
   check in any future reviewed integrated design; never invent rights.
2. The model does not authenticate a real session or inspect tenant disabled
   users, revoked Public connections or live account selections.
3. All policy/event HMAC checks are offline research; the external checkpoint
   is caller-held, **not durably published**, independently monotonic, or
   crash-atomic with the SQLite commit. No compromised-key quarantine or
   key-rotation crash protocol is wired into this new schema.
4. The fixture is ephemeral /dev/shm, not a production durability guarantee;
   no encrypted backup/restore integration or operator approval workflow.
   A malicious rollback of both the database and latest trusted pin is not
   detectable by this isolated test.
5. No real paper execution, production risk enforcement, fractional stock
   venue restrictions, corporate actions, open-order reservation, market
   data retention, historical return claim or brokerage integration.

Do not enable production paper fills until licensing, authenticated scope,
durable monotonic custody, crash-safe rollback policy, independent testing and
explicit operator authorization are complete. Existing Starter Render service,
1 GB disk, Public connections, owner acceptance evidence and all credentials
remain untouched. No new paid services.
