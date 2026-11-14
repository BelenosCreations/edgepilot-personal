# Independent checkpoint evidence

Authenticated paper preflight verifies an identity session, CSRF, account
scope, and synthetic ledger history in one SQLite transaction. It projects
a proposal and rolls back. The test restores an earlier copy of that
database after a synthetic request is written. Preflight sees that request as
new again because the identity and ledger evidence come from the same copy.
The projection has no fill authority and writes no state.

The tenant archive can reject the same older state when given the current
pin from independent custody. Restoring the current archive still clears the
old session and quarantines account bindings. A new login alone cannot make
the restored account eligible for preflight. The archive path preserves the
tenant schema, request digests, and policy mapping. The separate Decimal
rehearsal has its own storage and signed ledger history. There is no shared
transaction binding a preflight result to a recovered checkpoint or any fill.

Offline active checkpoint recovery, inspection, and reviewed cleanup can
all take the separately keyed `recovery_receipt`. When supplied, the receipt
must match the authenticated export and the exact signed witness tip. Its
transaction stays open through the operation and its path is rechecked before
publication and unlink. Existing offline callers using the export alone
retain that behavior.

The rehearsal interrupts a quarantine handoff after the witness commits and
before the local receipt acknowledges it. Old checkpoint inspection refuses
while the witness is ahead. Explicit terminal review advances the separate
receipt. When the local receipt, witness, and ledger are then rolled back,
the updated independent receipt rejects stale checkpoint inspection,
publication, and cleanup. Another test replaces that independent file
with an exact copy during publication. Recovery preserves the staged link
for review and accepts it after the original independent evidence returns.

The independent receipt must be current to detect this rollback. A rollback
that includes every retained copy and cross-resource power-loss consistency
remain open. Production paper fills, live trading, autonomous brokerage
orders, and bank transfers remain disabled.

Synthetic monthly equity history verifies the provider period, attribution,
and regular-series expected count from [Public Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2).
Real history remains limited to [owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
