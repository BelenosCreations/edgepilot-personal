## Phase 6 (v0.2.12): Historical reconciliation and provenance (inactive)

The owner shadow rehearsal now calls
`backend/engine/historical_reconciliation.py` to inventory each legacy
history row and create a temporary provenance index. Known explicit broker
account references must match the previously verified Public account;
blank references and unscoped automation, quotes, paper records, risk
configurations and activity are quarantined without owner attribution.
Conflicting explicit account references fail closed, and unrecognized
tables are reported for review. The source DB remains read-only and all
index rows, fingerprints and disposable tenant mappings are destroyed
after the test. Read `HISTORICAL_RECONCILIATION_RUNBOOK.md` for exact
classes, limitations and cutover gates.

**Inventory completeness does not mean migration completion.** No
unscoped paper fills, global observations or activity are assigned to
an owner without independent evidence. No production rollout, new
login, Public connection, worker or trading mode is activated.


# EdgePilot v0.2.11 — Owner-to-tenant shadow migration rehearsal

**APPROVED SCOPE:** Develop and test mapping on an isolated copy. No production
data migration, login provisioning, tenant activation or worker switching.

## Safety boundaries

`backend/engine/owner_shadow_migration.py` is an offline-only simulator, not
imported by Flask, Android, cron or the active automation worker. It opens the
source database in SQLite read-only mode, copies it with SQLite's native
backup API into a new private temporary workspace, performs all mapping
operations inside that disposable copy, validates source/table inventories
and referential integrity, and destroys the workspace. It rejects the known
Render production disk mount `/data`. A separate flag
`EDGE_OWNER_MIGRATION_REHEARSAL_ENABLED=true` and approval phrase
`SHADOW REHEARSAL ONLY` are mandatory. Both are absent from production.

The existing Public account ID and encrypted broker credential must be
present. The offline operator supplies the original `EDGE_CREDENTIAL_KEY`
through an approved private environment. The rehearsal proves the ciphertext
decrypts without displaying, logging, changing or making any Public API call
with the secret; it then copies the **same encrypted ciphertext** into a
dormant tenant connection in the disposable copy.

The test creates a temporary owner identity record, a linked tenant account
and read-only disabled runtime status. It copies validated account snapshots
and existing observation cycles with lineage mapping from original row IDs
to target row IDs. All original legacy tables remain intact. A quarantined
settings table preserves the original configuration without activating it.
Account-facing settings are limited to a harmless profile label; original
risk percentages, saved Auto-Trade state, API/AI preferences and exposure
settings are **not used by the new runtime**.

Every other legacy table—including automation events/quotes, orders,
transactions, ledger, watchlists, reconciliation, paper positions and
unassigned records—is inventoried as *pending*, not silently moved.
Unrecognized or conflicting multi-account references, invalid history,
existing tenant records, missing credential keys and failed integrity checks
stop the rehearsal. No account is claimed to be cutover-ready.

**Important:** The original backup contains material that is recoverable
with the separate database recovery key and Public credential key. Use
encrypted temporary storage; the simulator's plaintext copy should not
be created on an untrusted disk or uploaded to GitHub/chat.

## How to run in an isolated test environment only

After creating an already-restored, throwaway database copy on an encrypted
workstation or verified memory-backed volume, configure these two secret
values privately in the process environment:

- `EDGE_OWNER_MIGRATION_REHEARSAL_ENABLED=true`
- `EDGE_CREDENTIAL_KEY=<original encryption key from secure vault>`

Do not paste the key into shell commands, screenshots, GitHub, messages,
test fixtures, notes, or this chat.

Then:

```sh
python backend/tools/owner_shadow_rehearsal.py \
    --database /secure/isolated/edgepilot-restored.db \
    --approve "SHADOW REHEARSAL ONLY"
```

Expected sanitized results: `stagingOnly=true`,
`cutoverReady=false`, `workerEnabled=false`,
`paperEnabled=false`, `liveEnabled=false`,
`sourceLogicalInventoryUnchanged=true` and
`migrationExecutedOnProduction=false`. Counts for copied history and
pending table names are provided without account IDs or credential values.

The test does **not** retain a migrated database: this is intentional.
Do not run against the production Render database or try to re-enable
identity/account feature flags after the rehearsal.

## Remaining blockers before a future production cutover

1. Preserve a fresh encrypted database snapshot plus separate recoverable
   backup and Public credential keys. Verify archive digest and test restore.
2. Freeze legacy writes/worker at a separately agreed maintenance window.
   Validate broker ownership through Public's permitted API and verify correct
   account authorization and any additional Public terms for multi-user use.
3. Resolve every `pendingHistoricalTables` source into tenant-scoped target
   models, explicit immutable legacy archival reads, or justified exclusions.
   Record IDs/digests and handle conflicting cross-account rows. Do not
   declare full history migrated while these are pending.
4. Implement fully tenant-scoped legacy API replacement, signed owner
   provisioning, MFA/recovery, account switching UI and per-account workers
   with quota and risk enforcement before enabling any new user.
5. Rehearse reversible cutover on fully restored test environment, including
   old/new data parity, a rollback time window and no order placement.
6. Obtain a new explicit approval to run any live migration or change Render
   flags. Keep real-money orders and bank transfers disabled.
