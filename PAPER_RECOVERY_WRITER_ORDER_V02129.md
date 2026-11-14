# Recovery writer ordering

An offline active checkpoint depends on the exact signed witness and ledger
state. When a witness quarantine or synthetic ledger fill commits before
review, the old export cannot authorize inspection, cleanup, or publication
to a missing destination. The rehearsal verifies that the published inode,
the selected staging link, and unrelated files survive the refusals.

The process-exit rehearsal pauses reviewed cleanup at unlink while a
cooperating SQLite writer is inside its transaction. A signed witness writer
waits until a process exit before unlink, leaving the staging link present.
A synthetic ledger writer waits until a process exit after unlink, leaving
the published checkpoint as the sole link. In both cases the writer commits
after the process releases its snapshots and fresh recovery refuses the old
evidence. The observed links describe the current filesystem state.

The second-generation archive still supports repeated exact-pin readback and
refuses cleanup of a separate candidate. The owner browser refuses a synthetic
history response with different source attribution. The provider contract is
[Public Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2).
Real history remains limited to [owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).

Combined rollback and power-loss consistency across resources remain open.
Production paper fills, live trading, autonomous brokerage orders and bank
transfers remain disabled.
