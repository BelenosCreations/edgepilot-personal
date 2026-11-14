# Publication cleanup and readback

Offline terminal receipt repair and active checkpoint recovery now use the
same staging-link removal code during initial publication and reviewed
cleanup. It syncs the destination directory and verifies the published inode,
its link count, the staging path and the locked directory. It also checks for
SQLite sidecars and rechecks the independent evidence before unlink. It then
syncs the staging directory. Initial publication can remove its empty staging
directory. Reviewed cleanup removes only the named link.

An interrupted cleanup can already have removed the staging name. Use
`inspect_local_terminal` with the exact independent receipt and signed terminal
record, or `inspect_recovered` with the authenticated checkpoint export and
exact recovery evidence. Readback shows whether an additional link is still
present. If it is, review the specific staging path and use the corresponding
cleanup operation. A visible readback describes the current filesystem state.

Synthetic tests exit the publishing process after unlink and inject a failure
at the staging-directory sync. Both paths preserve unrelated staging names and
allow repeated exact readback. Reviewed cleanup refuses an exact-byte
replacement at either file path and a redirected staging directory while a
cooperating SQLite writer is blocked. A second-generation restore refuses a
replaced stage and still supports repeated readback at the exact archive pin.

Public's [Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2)
documents the regular-market series and its expected bar count. The browser
test confirms a repeat manual lookup clears the previous bars and displays the
fresh synthetic close with Public attribution. Real history remains limited to
[owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).

Combined rollback of all retained evidence and cross-resource power-loss
consistency remain open. Production paper fills, live trading, autonomous
brokerage orders and bank transfers remain disabled.
