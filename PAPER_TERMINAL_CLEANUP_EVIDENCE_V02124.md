# Terminal cleanup evidence

Offline terminal cleanup holds the existing evidence transactions and rechecks
both evidence paths immediately before unlink. Inspection makes the same check
before returning a result. Inode and timestamp checks detect disappearance,
replacement or in-place changes while an open SQLite transaction can still
read its previous snapshot. Tests remove or roll back the independent receipt
and the signed witness individually after the initial verification. Cleanup
refuses and leaves the selected link available for review.

Child processes exit immediately before and after unlink. Repeated inspection
with the same evidence identifies the surviving names and verifies the original
receipt. Two competing operators produce one successful unlink. The published
inode, receipt bytes and a neighboring operator file survive.

Second-generation archive tests refuse a missing archive or pin, including
readback with a missing pin after an ambiguous cleanup. The exact archive and
its independently retained pin still verify the quarantined candidate. This
rehearsal leaves simultaneous rollback and cross-resource power-loss
consistency open. The path checks also leave a window between the final check
and unlink for external filesystem changes.

The synthetic Public history route test verifies that logout blocks another
history request before it reaches the provider and returns a no-store response
without bars. [Owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance)
remains pending. Production paper fills, live trading, autonomous brokerage
orders and bank transfers remain disabled.
