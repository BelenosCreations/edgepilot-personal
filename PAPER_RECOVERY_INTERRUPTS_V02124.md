# Recovery interruptions

The offline terminal receipt rehearsal exited immediately before and after
unlinking the selected staging name. Exact readback reported whether the
additional link remained. Two competing cleanup attempts yielded one
successful unlink. The published receipt kept its inode and bytes, and
unrelated staging files stayed in place.

Terminal inspection and cleanup now recheck the independent receipt and
witness paths after verifying the published receipt. Cleanup refused unlink
when the independent receipt disappeared or the witness was replaced by an
older signed copy during the directory sync. The check detects missing paths
and changes to file identity or metadata observed at recheck.

Second-generation archive readback and cleanup reject a missing pin and an
older valid pin even when the current encrypted archive is available.
Exact-pin readback still verifies the quarantined candidate after interruption.

Synthetic Public history coverage verifies that returning from the one-month
view to one week issues a new source request and returns a no-store response.
Real history remains limited to
[targeted owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
Earlier snapshot and MSFT quote acceptance still apply.

Combined rollback of all retained evidence and cross-resource power-loss
consistency remain open. Production paper fills, live orders, autonomous
brokerage orders and bank transfers remain disabled.
