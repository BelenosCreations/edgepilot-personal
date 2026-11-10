## Phase 10 (v0.2.16): Dormant per-device account choice and monitoring isolation

The new backend/engine/tenant_api_gateway.py stores a future account
selection **per verified identity session** rather than changing the
legacy global selected account. The disabled-only
backend/engine/tenant_monitor_blueprint.py produces explicit per-account
watchlist plans and supports RAM-only zero-quote synthetic observation
replays for tests. No HTTP endpoint or live worker imports either module.
The static tenant route audit still blocks multi-account production
cutover. See TENANT_SESSION_MONITOR_RUNBOOK.md for limitations,
diagnostics, security tests and future authorization requirements.


# EdgePilot v0.2.15 — Dormant scoped historical summaries and reversible migration gates

**STATUS: INACTIVE.** This release does NOT perform a production migration,
enable a new user, change a Public account, start a tenant worker, place an
order, transfer funds, or activate live trading.

## New dormant data models

The offline owner shadow rehearsal now builds three **source-only/unverified**
history summary tables, with explicit composite user/account/reference FKs:

- `tenant_history_transaction_details`: validated source timestamp, a
  one-way digest of provider transaction ID, optional source symbol, type,
  subtype and side labels; no raw broker transaction JSON or bank details.
- `tenant_history_broker_details`: recorded broker-fill/observed-order/trade
  source labels, timestamp, identifier hash, bounded symbol and validated
  quantity/price/fee where available. **Not a broker-confirmed execution.**
- `tenant_history_audit_details`: bounded audit/run event category, source
  state and timestamp. Raw message, customer details and JSON are excluded.

All rows are permanently labeled `SOURCE_ONLY_UNVERIFIED` in the dormant
tables. Any source row without the expected schema, a valid timezone-aware
timestamp, a valid identifier, finite positive quantities/prices, or the
required account scope is retained **reference-only** and counted as pending.
A mismatched source-row fingerprint or owner aborts staging instead of
allowing a guessed account assignment.

Every history reference remains recorded, even if it cannot be summarized.
The report contains `tenantHistoricalSummaries` with
`supportedSummariesStaged`, category totals,
`referenceOnlyOrUnsupportedRows` and
`fullHistoryPayloadMigrated=false`. **Do not misread summary counts as a
full historical payload migration**. Neither sensitive raw broker payloads
nor the original source transaction IDs are returned by the future-only
identity-scoped read model.

## API and worker boundary audit

`tenant_route_audit.py` examines the API route decorators, the identity
versus legacy cookie and CSRF separation, and existing worker source.
It currently identifies the global legacy selected-account worker and
legacy routes as **not tenant-scoped**. It fails closed if the identity
route inventory or expected authorization structures change without review.
The report is a static source analysis, **not proof of runtime isolation**.
It explicitly returns `crossAccountProductionCutoverAllowed=false`.

Neither `tenant_history_details` nor the tenant route auditor is imported
by Flask or any active Render worker. There is NO history import endpoint,
no tenant history HTTP route, no APK feature and no new user onboarding.

## Rehearsal, rollback and failure acceptance

1. Preserve a verified, encrypted database archive and separate private key.
   Never paste keys in chat, shell history, screenshots or pull requests.
2. Verify checksum and restore to the **actual /dev/shm tmpfs**, not the live
   Render /data database. Use the existing approved memory-backed workflow.
3. Use the opted-in **offline** shadow rehearsal on the restored file only.
   It verifies the same schema, source contents, all-row hash lineage,
   transactional scoped staging counts, strict foreign keys, approved
   account labels and the source's content fingerprint.
4. A failure before the internal commit (or an injected error) stops staging;
   the entire temporary SQLite directory is discarded, leaving the
   read-only restored source unchanged. Production remains unchanged
   regardless of rehearsal outcome.
5. Accept a result only if source and shadow hashes match, every legacy
   reference is preserved, staged typed rows reconcile against approved
   account labels and quarantined rows are not imported. Observe that
   `fullHistoryPayloadMigrated=false` and `cutoverReady=false` remain true
   limitations, not test failures.
6. Keep the verified encrypted backup and Android private key. Delete only
   deliberately named /dev/shm encrypted and restored test files after the
   examination. Review any error instead of rerunning blindly.

**A real production cutover is NOT implemented.** It would require a new
explicit approval and a separate maintenance window, paused and reconciled
workers, immutable pre-cutover backup, independently validated Public
authorization and broker positions, a tested reverse transaction mapping,
new-user MFA/security review, audit of every legacy API and scoped worker,
a detailed rollback trigger, and proof that both accounts and histories
remain isolated after failure.

No v0.2.15 test can meet these future production gates by itself.

## SSH host-key warning

Your Android OpenSSH client displayed a recurring additional host-key
signature verification warning. Do not disable StrictHostKeyChecking or
erase trusted host keys as a workaround. Before another sensitive migration,
independently verify the current Render Ohio host fingerprint using Render's
official SSH documentation; unexpected changes should halt the operation.
The warning has not been resolved or changed by this release.
