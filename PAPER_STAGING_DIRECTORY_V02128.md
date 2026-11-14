# Staging directory recovery

Offline publication syncs the destination directory before unlinking the
staged database, then syncs the staging directory. It attempts to remove the
staging directory after that sync. If the directory now contains unrelated
files, publication returns successfully and leaves those files in place.
Other directory removal failures still require exact readback.

The tests exit immediately before and after directory removal and inject a
removal error. In both recovery paths, repeated readback verifies the exact
published database and reports a single link. For a terminal receipt, use
`inspect_local_terminal` with the independent receipt and signed terminal
record. For an active checkpoint, use `inspect_recovered` with the authenticated
export and exact recovery evidence. An empty staging directory has no
candidate to verify. If a directory contains a file with the expected database
name, compare it to the published inode before offering that path to reviewed
cleanup. Leave other names in place.

During reviewed active-checkpoint cleanup, a signed witness writer and a
synthetic ledger writer can each begin under SQLite's rollback journal. Their
commits wait for the recovery readers to release the snapshots. After either
writer commits, a fresh readback refuses the previous checkpoint evidence.
The second-generation restore still uses the exact archive pin and preserves
an unrelated staging candidate when the reviewed path is replaced.

The simulated browser test discards late Public history after the symbol
changes. Public's [Get bars v2 documentation](https://public.com/api/docs/resources/market-data/get-bars-v2)
describes the provider's historical data endpoint. Real history remains
limited to [owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).

Combined rollback and power-loss consistency across resources remain open.
Production paper fills, live trading, autonomous brokerage orders and bank
transfers remain disabled.
