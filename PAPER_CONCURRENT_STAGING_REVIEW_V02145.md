# Concurrent staging review

Missing-publication inventory obtains a nonblocking shared lock on each
eligible stage directory while reading its names and metadata. When a
cooperating publisher or cleanup already holds the exclusive stage lock,
the scan refuses. The inventory already holds evidence locks, so waiting
for the stage lock could deadlock with a cleanup that acquired it first.
An authenticated existing publication follows the established inventory path.

The scan opens stages relative to the held parent and checks whether the
observed name still identifies the same directory after it reads the
entries. Two observations and the destination and evidence rechecks
protect the returned point-in-time inventory. A fresh review can list both
a moved stage and its same-name replacement. Their contents remain
unauthenticated and available for operator review.

The offline tests use separate synthetic copies of authenticated receipt
files so that SQLite locks on shared proof cannot hide a filesystem race.
They exercise a real publisher paused before linking, a publisher that
finishes while inventory is in progress, a renamed stage and a stale
independent pin. A lock applies only during each stage observation. Changes
after an observation and processes that bypass stage locks remain possible.
Combined rollback of retained evidence and cross-resource power-loss
consistency remain open. Tenant archive recovery retains its independent
exact pin. Authenticated paper preflight remains detached from execution.

The synthetic Public history browser check confirms that a duplicate
refresh while the first is pending sends a single request and displays the
source data for the selected period. Real history remains part of targeted
[owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
See [Public Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2).
