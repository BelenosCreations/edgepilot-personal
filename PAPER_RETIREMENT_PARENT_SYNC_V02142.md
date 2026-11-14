# Staging-directory removal and sync

Offline terminal receipt and active checkpoint recovery remove an empty
staging directory relative to the open destination directory descriptor.
Relocating the destination parent and reusing its pathname cannot redirect
the removal to the new parent. After removal, the held staging directory
must have no remaining link. The publisher syncs the held parent directory
and then rechecks the reviewed paths, published file and independent evidence.

The rehearsals move the staging directory and reuse its name with operator
files at both locations. They also move the parent and preserve files under
its replacement. After a parent sync error or process exit, fresh exact
readback identifies the publication. When readback competes with cleanup
after a process exit before unlink, one cleanup succeeds. After unlink,
fresh readback recognizes the single link and retries refuse further cleanup.
Missing independent evidence prevents both operations.

A same-parent empty directory replacement can still race name-based
removal. Separate filesystem operations also leave combined rollback of all
retained evidence and cross-resource power-loss consistency unresolved.
Tenant archive recovery retains its separate exact pin. Authenticated paper
preflight remains detached from execution.

The synthetic weekly history regression verifies source-attributed,
session-only, read-only output. See [Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2)
and [owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
