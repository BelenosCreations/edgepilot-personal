# Synthetic receipt quarantine and interrupted archive publication

A frozen receipt reservation now has an explicit terminal resolution. The
operator independently reviews the reserved receipt and the exact current
witness receipt, then signs a quarantine record. The offline helper verifies
both receipts and the signed transition before publishing quarantine and
retaining its receipt. It can acknowledge a quarantine that already committed
when the original response was lost. The resolution does not replay rotation,
promote an active state, or open the ledger for writing.

If the witness has advanced since review, obtain its exact current receipt
and review again. Keep the latest receipts independently. A local SQLite
reservation is not a monotonic record against rollback of all resources and
their retained evidence. No automated thaw or prepared-target promotion
through a frozen reservation is provided. Cross-resource power-loss testing
and independent operator deployment remain open.

The rotation handoff also retains file descriptors until acknowledgment and
rejects a replaced ledger or witness before entering the write. This protects
the observed handoff boundary in the synthetic fixture. It does not provide a
filesystem authorization guarantee against a privileged concurrent actor.

An exact-pin synthetic tenant restore interrupted after its final link may
leave a quarantined candidate and a second link at the private stage. Use the
read-only publication audit with the original ciphertext, policies and
independently retained pin. It verifies the schema, paper rows and request
digests, immutable policies and historical loss stops, quarantined account
scope, and invalidated sessions. It reports whether a second link exists.
It leaves all names and bytes in place. The operator must verify that a
candidate staging name refers to the same inode before manually removing
it. A verified candidate remains quarantined and the restore refuses to
overwrite it.

Owner history stays source-attributed and session-only. The browser and
synthetic provider regressions are included. Follow the
[owner-device history acceptance steps](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance)
when the owner is available. The earlier snapshot and MSFT quote checks apply.

Production paper fills, live or autonomous brokerage orders and bank
transfers remain disabled.
