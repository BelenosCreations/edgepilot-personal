# Publication retirement review

Offline terminal receipt and active checkpoint recovery review the published
file and independent evidence after trying to retire the staging directory.
Successful removal requires the held directory to be unlinked and its former
path to be absent. If an operator file keeps the directory in place, the
original directory must remain identifiable and the staging filename must be
absent. The publication must still be the exact file verified after staging
unlink and sync, with no SQLite sidecars.

Reviewed cleanup checks the staging inode and change time after checking for
sidecars. A same-name replacement during that check is preserved. The
rehearsals cover competing cleanup, destination replacement, moved evidence,
new staging files and process exit around directory removal. Fresh review can
recognize an authenticated publication after an interrupted result. The
filesystem checks narrow the race windows around separate syscalls. They
leave combined rollback of all retained evidence and cross-resource
power-loss consistency open. Tenant archive recovery retains its separate
exact pin and authenticated paper preflight remains detached from execution.

Synthetic Public weekly history keeps its source label and regular-hours
request. A response with only extended or overnight series is refused. See
[Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2)
and [owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
