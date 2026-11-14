# Terminal handoff readback

The offline rehearsal exits after committing the independent terminal
receipt and before repairing the frozen local reservation. Use
`inspect_terminal_handoff` with the exact independent receipt and matching
signed terminal record to check the existing local receipt. It reports
`localRepairRequired` when the local receipt is frozen or still points to an
earlier event in the same signed witness history. A completed handoff reports
false. Inspection requires an existing verified local receipt.

Use `repair_local_terminal` with the same reviewed evidence. Repair
rechecks the existing local receipt, the independent receipt, and the signed
witness immediately before committing. The rehearsal substitutes an
exact-byte local file before commit and verifies that the original
reservation stays frozen. After repair, repeated inspection and repair
return the same terminal receipt and preserve all three files.

In a separate rehearsal, active checkpoint inspection and cleanup wait
while a cooperating independent writer commits the terminal receipt. Both
operations refuse the old active receipt as soon as they acquire the lock
and preserve the checkpoint, selected link, and unrelated files. The
second-generation archive still requires its exact pin for repeated readback.

The synthetic monthly equity history regression verifies a fresh attributed
bar after a repeat lookup using [Public Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2).
Real history remains limited to [owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).

Combined rollback and cross-resource power-loss consistency remain open.
Production paper fills, live trading, autonomous brokerage orders, and bank
transfers remain disabled.
