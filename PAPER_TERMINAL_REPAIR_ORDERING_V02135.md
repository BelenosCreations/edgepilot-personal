# Terminal repair ordering

The offline rehearsal pauses a cooperating local repair after it stages
the updated receipt. Exact inspection waits at the independent receipt
lock. After rollback it reports that repair is required and verifies the
same frozen local receipt. After commit it reports a completed handoff.
Both outcomes preserve the independent receipt and the signed witness.

Missing-receipt inspection checks the local target and SQLite sidecars
after rechecking the independent receipt and witness files. Staged
publication also checks for SQLite sidecars after reviewing those files
and uses an exclusive link for the target. The rehearsal inserts a
receipt, rollback journal, WAL file or shared-memory sidecar during
review. Inspection and repair refuse the new evidence, preserve its
bytes and allow exact review again once the ambiguity is resolved.
See the [operator steps](PAPER_TERMINAL_REPAIR_READBACK_V02134.md) for
local receipt repair and separately pinned tenant archive recovery.

The synthetic owner history route checks Public's regular-series
expected count when supplied and keeps the count absent when only the
overall count is supplied. The response stays source-attributed and
uses `Cache-Control: no-store`. See
[Public Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2)
and [owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).

The rehearsal covers cooperating repair and observations at specific
review points. Combined rollback of all retained evidence and
cross-resource power-loss consistency remain open. Authenticated paper
preflight stays detached from execution.
