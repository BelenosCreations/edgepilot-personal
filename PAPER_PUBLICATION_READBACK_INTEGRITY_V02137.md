# Publication readback integrity

Offline terminal receipt and active checkpoint readback verify the published
file again after reviewing the independent evidence. Each compares the
verified file identity, change time and link count with the current path.
Terminal handoff inspection also checks its reviewed local receipt after
rechecking the independent receipt and signed witness.

The rehearsal unlinks the published name, substitutes an exact-byte copy,
or removes the staging link during review. Readback refuses each change.
Once the original link is restored, a fresh verification returns the same
receipt. Keep the independent evidence available for the fresh review.

Reviewed cleanup checks for SQLite sidecars at the staging and published
names before unlinking. The rehearsal inserts rollback journal, WAL and
shared-memory sidecars after syncing the destination directory. Cleanup
refuses and preserves the sidecar, receipt and link. Readback of the
published name also refuses if a sidecar appears there during review.
Tenant archive recovery continues to require its independent exact pin.

Synthetic weekly Public history verifies that only the regular-series
expected count accompanies regular-session bars when other series also
carry counts. History remains source-attributed and session-only. See
[Public Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2)
and [owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).

Combined rollback of all retained copies and cross-resource power-loss
consistency remain open. Authenticated paper preflight stays detached
from execution.
