# Terminal receipt staging cleanup

`DecimalRecoveryReceipt.cleanup_local_terminal_stage` takes the operator-selected
staging path, the exact independent receipt and the matching signed terminal
witness record. It verifies that the selected name links to the published
inode. The destination directory is synced before unlink and the staging
directory is synced afterward. Other staging names and files stay in place.
An active publisher, unavailable independent evidence, a stale witness,
a copied receipt, a symbolic link or SQLite sidecars cause refusal.

If cleanup returns an ambiguous result, use `inspect_local_terminal` with the
same evidence before attempting any further cleanup. It verifies the published
receipt and reports whether an additional link is visible. If the additional
link is present, verify the operator-selected path again before retrying. If it
is absent, no further unlink is needed. Inspection establishes the filesystem
state visible to the running process. Combined rollback of retained evidence
and cross-resource power-loss consistency remain open.

Synthetic regressions exercise real process exit during publication, an active
publisher, missing or mismatched evidence, and directory sync errors before
and after cleanup unlink. Archive restore coverage includes the existing
restore, exact-pin inspection and reviewed cleanup paths. The synthetic Public
history HTTP test checks one-week and one-month attribution and no-store
responses. Real history remains limited to
[targeted owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
Earlier snapshot and MSFT quote acceptance still apply. Production paper fills,
live trading, autonomous brokerage orders and bank transfers remain disabled.
