# Active checkpoint publication

The offline receipt store stages terminal receipts and active promotion
checkpoints with the original protocol key and filename for each. The publisher
holds an exclusive lock on the staging directory. It checks evidence before
creating the destination hard link, syncs the destination directory, then
rechecks the evidence and verifies that both names still identify the published
inode. A competing publisher cannot replace an existing destination. If the
exclusive link already exists, the losing publisher removes only its own
unpublished stage.

Tests remove the local receipt, signed witness or ledger after staging and
replace each file with an exact copy after linking. The first interruption
leaves no destination. The second leaves both names. An operator should run
`inspect_recovered` with the exact authenticated export and trusted receipt,
review the staging path, and then use `cleanup_recovered_stage`. Cleanup
independently verifies the evidence and the same inode and refuses an active
publisher. It syncs the destination directory before unlink and the staging
directory afterward. Exact readback and explicit cleanup also apply to the
terminal receipt. Second-generation archive readback still requires the exact
archive pin and succeeds repeatedly after the original candidate returns.

SQLite transactions hold the evidence snapshots while the cooperating
publisher or reviewer works. The staging lock excludes competing operations
on the same stage. Path rechecks detect observed replacement and in-place
changes. Changes outside this cooperation after the final check, simultaneous
rollback of all retained evidence and cross-resource power loss remain open.

The synthetic Public history test returns a changed source close on a repeat
request and verifies source attribution and no-store behavior. Real history
remains limited to [owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
Production paper fills, live trading, autonomous brokerage orders and bank
transfers remain disabled.
