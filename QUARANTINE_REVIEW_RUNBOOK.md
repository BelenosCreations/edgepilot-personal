# EdgePilot v0.2.13 — Private, memory-backed history rehearsal

Status: INACTIVE. No live account migration, order execution, new identity
provisioning, worker reassignment, banking action, or data cutover.

## Memory-only constraints

The operator must first restore an already validated encrypted EdgePilot
backup into a standalone SQLite file under Linux /dev/shm. The offline
owner_shadow_rehearsal.py tool now requires:
- /dev/shm must be an actual tmpfs mount as confirmed by /proc/self/mountinfo
- The restored plaintext input resolves within that mount and has the same
  backing device as /dev/shm, rejecting path tricks and disk-backed input
- At least 3x source-file size plus 4 MiB free tmpfs capacity
- All temporary shadow directories created explicitly under /dev/shm,
  and SQLite temporary store set to memory where the rehearsal opens SQLite
- Source opened read-only, all writes confined to disposable copy
- No report is returned until the copy is discarded and directory removed

If any condition fails, the tool must stop. NEVER override this check.
Do not use /data/edgepilot.db; no production DB writes are authorized.

This guarantee is about the OFFLINE SHADOW REHEARSAL. The separately maintained
encrypted-backup/restore utilities have their own scratch-space behavior and
must only be called with the previously approved, verified RAM-based restore
steps. A compromise of the phone or server may still expose key material
in process memory. Do not copy, log, or screenshot recovery secrets.

## Per-record evidence and rollback

The source schema and table row counts, every legacy record content hash,
and source content fingerprint are verified pre/post. The shadow copy
maintains a private per-row mapping index with lineage to the original row.
Any differing row data (even when row counts remain equal), ownership conflict,
bad key, missing storage, unexpected schema or foreign key error fails closed.
After failure, temporary files are removed by context-managed cleanup;
the source is not touched.

Every account-labeled record explicitly matching the selected verified Public
account is still only EVIDENCE OF ACCOUNT REFERENCE, not proof of execution,
order provenance, cash movement, or trading advantage. Blank account records
and unscoped records remain quarantined.

## Quarantined history — manual resolution workflow

The sanitized report includes a quarantineReview section. It classifies
all quarantined or otherwise unexplained rows in disjoint evidence groups:
- unscoped_observations: research-only observation cycles
- automation_market_research: automation quotes/events without account IDs
- automation_runtime: engine state, highwater, risk profile (do NOT resume)
- ephemeral_runtime: old worker leases (do NOT migrate as active)
- paper_simulation: historical paper positions (prove owner first)
- activity_and_ai: activity and AI logs (private archival, require owner)
- configuration_and_watchlists: saved scan preferences/watchlist/risk settings
  (revalidate, never copy active settings automatically)
- ledger_metadata: require independent broker-confirmed reconciliation
- login_security: sessions and failed-login state (reprovision, not reuse)
- credential_security: encrypted broker vault (verified separately)
- ambiguous_account: blank or null explicit account references (verify owner)
- unknown_schema: new table shape requiring audited migration strategy

Each group includes only a count, table names, disposition, and next action.
NO record values, account IDs, keys, row identifiers or hashes are returned.
Groups are **not** authorizations to import. Even previously shadow-copied
observation cycles remain quarantined until ownership evidence exists.

## Operator checklist before running on another encrypted snapshot

1. Preserve separate verified encrypted database archive, recovery key and
   Public credential-encryption key; keep their sensitive values secret.
2. Verify encrypted archive hash before isolated restore to /dev/shm.
3. Confirm the restored plaintext database has integrity=ok, foreignKeys=ok.
4. Supply EDGE_CREDENTIAL_KEY privately as an environment variable using
   an approved mechanism; do not paste keys in shell history.
5. Use only the previously reviewed CLI command with
   EDGE_OWNER_MIGRATION_REHEARSAL_ENABLED=true and the exact approval phrase
   SHADOW REHEARSAL ONLY. It must return temporaryStorageVerifiedMemoryBacked,
   disposableWorkingCopyRemoved, historicalRowFingerprintsVerified and
   sourceContentsUnchanged all true, and migrationExecutedOnProduction false.
6. Preserve a redacted report of quarantine group totals. No production
   migration or flags can be enabled as part of this procedure.
7. Remove only the approved named, temporary /dev/shm encrypted and restored
   files. Keep original Google Drive and Android encrypted backups.

## Remaining production blockers

True per-tenant schema and authorization replacement for all legacy routes;
account-owner evidence for global/unscoped history; atomic and reversible
cutover with full-row parity; account-specific worker isolation; new identity
login and recovery; final review of security keys, brokerage integration and
testing. None are performed in this release.
