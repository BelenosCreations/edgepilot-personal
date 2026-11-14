# Publication cleanup readback

Offline terminal receipt and active checkpoint cleanup compare the selected
staging directory with the directory opened for its lock. If a directory moves
and a replacement appears during the open, cleanup refuses even if the
replacement contains the link to the same receipt.

After unlinking the staging name and syncing its directory, cleanup rechecks
the published file identity, the expected single link, file metadata and the
independent evidence. It also checks the reviewed directories and refuses
new SQLite sidecars or a replacement staging name. A refusal after unlink
can leave the published file with one link. Fresh authenticated readback
reports the current state and an unrelated or ambiguous staging file remains
available for inspection.

The rehearsals exercise byte-identical destination replacement, loss of
independent evidence, late sidecars, a recreated staging name and process
exit around cleanup. These are offline checks around filesystem operations.
They leave combined rollback of all retained evidence and cross-resource
power-loss consistency open. Tenant archive recovery retains its separate
exact pin and authenticated paper preflight remains detached from execution.

The synthetic owner history browser check verifies that a reported zero
expected count remains visible with the Public source label, and that a
response marked as persisted is refused. See the
[Get bars v2 schema](https://public.com/api/docs/resources/market-data/get-bars-v2)
and [owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
