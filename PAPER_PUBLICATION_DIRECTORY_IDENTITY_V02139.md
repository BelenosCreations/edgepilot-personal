# Publication directory identity

Offline terminal receipt and active checkpoint publication capture the
destination directory descriptor before creating a stage. Publication
compares both descriptors with the reviewed paths around the exclusive hard
link. Readback and cleanup recheck the destination directory, including its
owner and private permissions. If the exclusive link loses to a competing
publication, retirement repeats the independent evidence and staging checks.

The regressions move the staging or destination directory immediately before
and after linking. The verified inode can reach the directory held open by
the publisher. Publication refuses if the reviewed path now names a different
directory. When the staging directory alone moved, readback can still verify
the exact destination. Cleanup requires the selected staging path to link to
the same reviewed inode. A competing publication can also be verified after
fresh review while changed losing stages and unrelated operator files remain
available for inspection.

The rehearsal uses Linux procfs. The checks detect the exercised changes
around filesystem operations. A directory can move during a syscall, and
combined rollback of all retained evidence and cross-resource power-loss
consistency remain open. Tenant archive recovery requires its separate exact
pin. Authenticated paper preflight remains detached from execution.

The synthetic Public weekly history regression requests regular hours and
checks that the returned series and expected count come from
[Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2).
The response stays session-only. Real history is reserved for targeted
[owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
