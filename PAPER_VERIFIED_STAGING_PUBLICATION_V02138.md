# Verified staging publication

Offline terminal receipt and active checkpoint recovery hold the verified
SQLite file open while reviewing independent evidence. Before linking, they
recheck file identity, change time, link count, both directories and SQLite
sidecars at the staging and destination names. The exclusive hard link uses
the open file descriptor. Replacing the staging name with a byte-identical
copy during the link cannot publish that copy.

If review refuses before linking, keep the staged file, sidecars and any
operator files. A fresh attempt using the exact independent evidence creates
its own staging candidate. If a staging sidecar arrives during the link, a
destination name can already refer to the verified file. Cleanup refuses and
preserves both links and the sidecar. After resolving the sidecar, rerun
exact readback and explicitly review the selected staging link before
cleanup. The regression exercises both recovery paths and preserves
independent evidence and unrelated staging files.

The descriptor-based hard link uses Linux procfs. The checks bound the
rehearsed race windows. Combined rollback of all retained copies and
cross-resource power-loss consistency remain open. Tenant archive recovery
requires its separate exact pin, and authenticated paper preflight remains
detached from execution.

The synthetic Public history regression preserves a reported zero
regular-series expected count, exact source bars and session-only handling.
See [Public Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2)
and [owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
