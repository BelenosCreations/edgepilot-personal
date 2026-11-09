## Phase 7 (v0.2.13): Verified memory-backed rehearsal and quarantine review (inactive)

Phase 6 now reports audited evidence-based review groups within historicalReconciliation.quarantineReview, including every quarantined row. Global watchlists/risk configurations, paper simulation, market observations, session tokens and credentials are never silently attributed or activated. Matching timestamps, SPY symbols, or a single selected account do not provide proof of record ownership.

Plaintext safety: The restored source MUST be under a genuine Linux /dev/shm tmpfs. The tool rejects disk-backed inputs, symlinks pointing off tmpfs, and missing/insufficient memory capacity; creates its working copy with TemporaryDirectory(dir="/dev/shm"); verifies every original row's content fingerprint against the staged index; and discards that directory before reporting success. No default system temp directory is used for plaintext in this shadow rehearsal. Standalone migration_preflight backup/restore utilities remain separate and must be run only with the already approved memory-backed procedure.

Detailed runbook: QUARANTINE_REVIEW_RUNBOOK.md. Live migration, new accounts, and trading activation require separate future approval.


# EdgePilot Phase 6 — Historical provenance and account attribution

**Status: inactive, synthetic/isolated rehearsal only.** No production data
migration, no new account, no enabled identity, no paper/live trading.

## Scope and meaning

The Phase 6 `historical_reconciliation` module runs only inside the disposable
Phase 5 owner shadow rehearsal. Every legacy source row is inventoried in a
temporary, per-row provenance index with its SQLite row identifier and an
internal SHA-256 content fingerprint. Index rows are checked against source
row counts. No raw values, account identifiers, credential ciphertext, row
hashes, user IDs or sensitive order details are returned in the report.
The original database tables remain intact; the temporary index is discarded.

The account scope categories are:

| Class | Meaning | Can be activated? |
| --- | --- | --- |
| ACCOUNT_LABEL_VERIFIED | Explicit legacy `account` value matches the selected owner Public account; **not** proof of fills/trade provenance | No |
| ALREADY_SHADOW_MAPPED | A separately mapped portfolio snapshot with explicit matching broker account | No |
| BLANK_ACCOUNT_REFERENCE | Legacy account column is null/empty; owner cannot be determined | No |
| NO_ACCOUNT_EVIDENCE | Global configuration, automation, paper, watchlist, observation or activity; no trustworthy account reference | No |
| SYSTEM_EXCLUDED | Session/auth/settings/credential tables; never treated as trade history | No |
| UNKNOWN_REVIEW | Unrecognized source table requires explicit schema review | No |

Any non-empty explicit account value that is **different** from the
verified owner's selected account causes the entire rehearsal to fail.
Source tables with a known explicit account column must retain that column.
Unknown source tables are inventoried as `UNKNOWN_REVIEW`, never attached
to the owner's account. **A completed inventory does not mean every row
has been migrated or attributed to an owner.**

Known account-labeled categories: broker fills, attributed positions,
interventions, broker order/trade observations, audit alerts/runs,
submitted order provenance, local orders, scan runs, sync snapshots,
transactions, alerts and runs, portfolio snapshots.

Known unscoped categories: automation master/engines/events/quotes,
paper positions, watchlists, run-time leases, observation cycles,
activity, AI run logs, scan/discovery settings, global engine configs
and ledger metadata. These are quarantined until additional evidence
can establish ownership. Phase 5's old observation-cycle shadow
mapping is *not* counted as independently owner-verified.

**Broker execution rules:** A matching account value is not evidence that
a fill executed or originated from EdgePilot. Phase 6 never infers fills,
P&L, order status, ownership of global paper trades, or bank transfers
from historical quotes, transaction records or orders.

## Verification and rollback

- Only start the offline shadow tool from an **already isolated, restored
  and integrity-verified database** on encrypted or memory-backed storage.
- The tool refuses live Render `/data`; two explicit gating mechanisms
  remain required. No production Flask endpoint or background worker imports
  the reconciliation module.
- All working writes and reconciliation indexing occur in the disposable
  copy; source database remains in read-only mode. Any mismatch causes a
  fail-closed error; the disposable copy is removed.
- Read-only report includes per-category row counts and table names but
  never values or hashes. No trade or account setting is activated.
- Original legacy tables, encrypted database backup and recoverable secrets
  remain available for separately approved future rollback.

## Outstanding blockers to real cutover

1. Resolve every `quarantinedTables` and `unknownTablesNeedingReview`
   that has meaningful user data; classify global/system records separately.
2. Implement tenant-scoped target schemas and immutable migration lineage
   for broker fills, sync, orders and audit tables, with proven broker
   account ownership, signed execution provenance and fees where relevant.
3. Freeze old writes and replay a fresh verified backup; test total row
   counts, source/target hashes, idempotency, rollback and cross-account
   queries using all data and settings. Do not copy activity/paper
   records without account ownership evidence.
4. Audit every legacy API and background worker for session/account scope.
   Implement and test independent user onboarding, authorization and
   rollback before enabling new logins.
5. Seek a new explicit approval for a production migration or activation.
   Keep transfers, real orders and new user enrollment disabled.
