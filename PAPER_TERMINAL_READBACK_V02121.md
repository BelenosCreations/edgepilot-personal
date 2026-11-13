# Terminal quarantine readback

A process exited after committing signed terminal quarantine in the witness
and before retaining it in the local receipt store. The local reservation
remained frozen and the independent receipt stayed at the earlier tip. An
operator supplied the previous independent receipt, the exact observed
witness receipt and the matching signed quarantine record. Two concurrent
reviews could advance the independent receipt only once.

With that independent receipt and the terminal witness intact, explicit
repair could acknowledge the frozen reservation, advance a stale local
receipt authenticated as an ancestor, or publish a missing local receipt
exclusively from a verified private stage. A different quarantine record was
refused. The ambiguous earlier ledger was preserved byte for byte and
terminal quarantine remained in force. Existing recovery still requires
its usual ledger and receipt checks.

Second-generation tenant restore cleanup syncs the destination directory
before and after unlink. The rehearsal exits on either side of unlink and
uses the exact latest archive pin to inspect the published inode. The older
archive and its valid pin cannot authorize cleanup. The published bytes,
scoped requests, loss stops and quarantined bindings are preserved.

The owner history endpoint still uses session-only data. A synthetic route
test confirms that a refused period returns a no-store response without
bars. Real Public history still needs
[targeted owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
Earlier snapshot and MSFT quote acceptance still apply.

Combined rollback of all evidence and cross-resource power-loss consistency
remain open. Production paper fills, live orders, autonomous brokerage
orders and bank transfers remain disabled.
