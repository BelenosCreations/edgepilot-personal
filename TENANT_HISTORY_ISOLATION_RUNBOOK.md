## Phase 9 (v0.2.15): Dormant typed historical summaries and route boundary audit

The offline owner shadow rehearsal can now stage validated, account-scoped
source-only summaries of transaction, broker observation and audit events,
in addition to the v0.2.14 immutable reference ledger. All references
remain, even for invalid/unsupported records, which are counted as pending.
A new static API and worker inventory explicitly **blocks production
multi-account cutover** while the live legacy routes and worker still
depend on one globally selected account. No live changes occur.
See TENANT_HISTORY_SUMMARIES_RUNBOOK.md for audit limits, rollback
procedure and required future approval.


# EdgePilot v0.2.14 — Dormant tenant-scoped historical references

**Inactive development only:** This is NOT a full trade/order migration, not
a broker trade history UI, and not production account migration. No changes
to the legacy Public connection, active observation worker, risk settings,
trading mode, transfers or bank actions.

## Design

`backend/engine/tenant_history.py` provides an **additive** storage schema
and a future-only session-authorized metadata reader. It is imported only
by the offline owner shadow rehearsal, not Flask, the app, an execution
adapter or the active Render worker. It creates:
- `tenant_history_batches`: a dormant account/user-scoped provenance batch
  with source schema checksum and exact expected row count
- `tenant_history_references`: one immutable-in-purpose source-row reference
  per account, with source table, source row ID, SHA-256 content fingerprint,
  data category and a permanent `REFERENCE_ONLY` status

Strong composite foreign keys bind the batch, user, account and history row.
Unique composite keys prevent duplicate source references within an account.
Indexed queries always filter by **verified session user AND account**.
A reference is not a fill confirmation, authenticated broker record, trade,
realized P&L or an executable instruction.

No source trade payload (raw transaction JSON, customer/account identifiers,
credential values, bank data, provider tokens, free-text notes) is copied
into the new tenant history table. The original legacy rows remain preserved
in the verified source archive. Full tenant-scoped historical payloads require
a separate schema audit and explicit future authorization.

## Shadow rehearsal integration

After account credential verification and the Phase 6 all-row inventory,
Phase 7/8 creates a dormant user-account pair in the disposable database,
then the v0.2.14 staging step copies ONLY matching explicitly account-labeled
source row references. It checks exactly one staged record per attributable
source row, verifies source hashes against the indexed source evidence and
confirms no quarantined/ambiguous row was attached. Failure throws a sanitized
exception; the disposable transaction and its memory-backed directory are
rolled back and removed.

Expected report section: `tenantHistoricalReferences`, with count,
`sourceRowsReconciled=true`, `quarantinedRecordsImported=0`,
`referencesOnly=true`, `rawTradePayloadsMigrated=false`,
`fillsOrOrdersExecuted=false`, `loginOrWorkerActivated=false`,
`cutoverReady=false`.

The session-scoped metadata reader is **not exposed by HTTP**. Its
`summary` and `page` methods require identity_store.principal(token)
and `AccountScopeStore._check`, including disabled-user, disabled-account
and revoked-credential checks. Client-supplied user IDs are never accepted.
Real-session tests cover separate users on different phones and two accounts
owned by one user, crossed IDs, revoked sessions, pagination and invalid
requested accounts. New users are synthetic fixtures only.

## Rollback and cutover restrictions

The live database never receives the new history tables. The isolated
plaintext source is opened read-only, the staging transaction operates
solely in a RAM-backed throwaway copy, and a failure restores the database
to its original state by discarding that copy. The source is compared by
schema, per-row content fingerprints and row counts before and after.
Neither an identity session nor a tenant worker starts during a rehearsal.

No user enrollment, broker connection change, privilege escalation, live
worker switch, automatic order execution, bank transfer, active portfolio
history or historical trading status changes are authorized. Full migration
remains blocked by unscoped records and broader route/worker audit.

## SSH host key warning review (no settings changes)

The prior Android SSH output contained
`client_global_hostkeys_prove_confirm: server gave bad signature for ED25519
key 0: incorrect signature` **after an otherwise successful SSH
connection**. This can occur in OpenSSH's additional host-key update-proof
exchange, rather than initial authentication. Do **not** infer that
host authentication is safe just because SSH succeeded.

Render publishes an official Ohio region ED25519 fingerprint at
https://render.com/docs/ssh:
`SHA256:kRDsLlrHqOyqso58sEKyO6ZFMPj7p24zfNxYJ42yXGI`.
The fingerprint shown in the user's earlier initial-connection prompt
matched that value. Confirm the trusted host key still matches Render's
published value before future sensitive operations. If it changes
unexpectedly, stop and investigate. No SSH config, known_hosts entry,
security flags, or host-key update behavior was automatically modified.

## Next blockers

1. Prove real Public ownership of every requested account and enforce
   session-authenticated routing throughout the legacy APIs.
2. Reconcile the 362 quarantined sample records without implicit owner
   attribution; archive unscoped activity/observations safely.
3. Build fully scoped and validated historical payload schemas, ensuring
   individual broker fills, fees, reversals and provenance are accurate.
4. Rehearse a future reversible migration with fresh encrypted backup,
   account-specific worker quotas, end-to-end access control and rollback.
5. Obtain new explicit user approval before production migration or
   multi-user activation.
