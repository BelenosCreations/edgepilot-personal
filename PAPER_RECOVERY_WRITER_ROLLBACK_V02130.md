# Recovery writer rollback

The offline active-checkpoint rehearsal starts a signed witness update or a
synthetic ledger fill after recovery verifies its SQLite read snapshots. Both
writers reach their write logic and roll back before commit. The witness and
ledger remain byte-for-byte identical to their pre-review state. Exact readback
still sees the original published inode and staging link. A fresh reviewed
cleanup removes the link and leaves unrelated files in the staging directory.

Terminal receipt readback and cleanup also run while a writer holds the
independent receipt transaction with a temporary reservation. Each operation
waits for the writer to roll back. Readback then verifies the original terminal
receipt, and cleanup removes only the reviewed staging link. The original
terminal receipt and independent evidence remain intact.

The second-generation archive rehearsal refuses staging cleanup while a
writer holds the destination database, preserves the link, and verifies the
candidate repeatedly using the exact archive pin after rollback.

Synthetic Public history still attributes the bars to Public and reports the
regular-series expected count only when Public supplies it. Public documents
both the overall and per-series counts in [Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2).
Real history remains limited to [owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).

Combined rollback and cross-resource power-loss consistency remain open.
Production paper fills, live trading, autonomous brokerage orders and bank
transfers remain disabled.
