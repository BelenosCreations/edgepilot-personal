# Terminal repair readback

1. Supply the exact independently retained receipt and its matching signed
   quarantine record to `inspect_terminal_handoff`. A verified frozen or
   stale local receipt reports `localRepairRequired: true`. A missing target
   in a verified private directory also reports `localReceiptMissing: true`
   when the SQLite sidecar paths are absent. An invalid local receipt,
   a symlink, or ambiguous sidecar evidence yields a refusal.
2. Use `repair_local_terminal` with the same reviewed evidence. If the
   process exits after committing an existing local receipt, reopen all
   three stores and repeat the inspection. The committed repair reports
   `localRepairRequired: false`. If a missing receipt was published with a
   staging link still present, use `inspect_local_terminal` to verify the
   publication and `cleanup_local_terminal_stage` for the exact reviewed
   link. Inspect the publication again after cleanup.
3. For a separate interrupted tenant archive publication, supply the
   independently retained archive pin and original policies to
   `inspect_pinned_paper_publication`. Use
   `cleanup_pinned_paper_staging_link` with the same evidence and the
   exact staging link, then repeat inspection. The rehearsal refuses the
   previous archive pin, the terminal receipt MAC, and a byte-identical
   file on a different inode. It preserves that file and the verified
   quarantined destination.

The local repair rehearsal exits immediately after SQLite commits, before
the caller receives a result. Reopened stores verify the signed terminal
state and repeated repair preserves the files. Combined rollback of every
retained copy and cross-resource power-loss consistency remain open.
Authenticated paper preflight stays detached from execution.

The synthetic owner history regression refreshes attributed monthly bars
and checks a subsequent weekly entitlement refusal. The weekly request
uses the documented regular-hours selection in
[Public Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2).
Real data acceptance remains on the
[owner's device](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
