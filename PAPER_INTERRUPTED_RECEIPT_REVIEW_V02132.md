# Interrupted receipt review

The offline rehearsal exits the publishing process after the signed witness
commits terminal quarantine and before the local receipt is acknowledged.
The local reservation stays frozen and the independent receipt retains its
prior tip. Old active checkpoint inspection refuses. To advance the
independent receipt, the operator supplies its exact current tip, the exact
terminal witness tip, and the matching signed terminal record.

Terminal retention now rechecks the independent receipt and witness files
after verifying that evidence and before committing the receipt. The test
substitutes an exact-byte witness copy during retention and verifies that the
independent receipt stays at its prior tip. Once the original file is
restored, exact terminal review advances the independent receipt and permits
local repair. The advanced independent receipt blocks stale active recovery
even if the local files are rolled back.

Active checkpoint readback and reviewed staging cleanup wait while a
cooperating independent receipt writer holds its SQLite transaction. After
rollback, readback verifies the same published inode and cleanup removes
only the selected link. Repeated readback confirms the remaining link count.
Second-generation archive regressions continue to require the exact pin.

The synthetic owner history regression uses the documented lead-in fields
from [Public Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2).
It displays the source bar after the lead-in and leaves the series expected
count absent when only the total is supplied. Real history remains limited
to [owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).

Combined rollback of every retained copy and cross-resource power-loss
consistency remain open. Authenticated paper preflight stays detached from
execution. Production paper fills, live trading, autonomous brokerage
orders, and bank transfers remain disabled.
