# Terminal publication review

Two cooperating local repairs share the independent receipt lock. When the
first repair finishes normally, the second verifies the same existing
receipt. If the first process exits after linking the destination, the
second repair refuses a write while the extra link is present. Exact
readback verifies the retained receipt, and reviewed cleanup removes the
specific staging link. A subsequent repair returns the same receipt and
preserves the destination inode and the signed evidence.

Handoff inspection and publication readback check the destination again
for SQLite sidecars after reviewing the independent evidence. Reviewed
cleanup checks both names before unlinking. The offline rehearsal injects
a journal, WAL file, and shared-memory sidecar during final review and
verifies refusal with the receipt, link, and sidecar bytes preserved.
Once the test removes the synthetic sidecar, exact review and cleanup
can resume. See the [operator steps](PAPER_TERMINAL_REPAIR_READBACK_V02134.md).
Tenant archive recovery continues to require its independent archive pin.

Synthetic owner history verifies that Public's regular-series expected
count survives exclusion of the provider's chart lead-in. The returned
bars remain source-attributed and session-only. See
[Public Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2)
and [owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).

Combined rollback of all retained copies and cross-resource power-loss
consistency remain open. Authenticated paper preflight stays detached
from execution.
