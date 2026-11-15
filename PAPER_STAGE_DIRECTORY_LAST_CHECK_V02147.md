# Stage-directory last-check review

Offline terminal receipt and active checkpoint cleanup already require an independently authenticated publication and verified staging hard link. This milestone simulates a **noncooperating same-user directory rename and same-name replacement** immediately after the selected staging file's final `os.stat` observation, but before unlink. Cleanup now revalidates the selected directory pathname against its held directory descriptor. If replaced, it refuses before `os.unlink`; the authenticated link remains in the moved directory, while the new candidate's unreviewed bytes stay untouched.

Both terminal and checkpoint synthetic fixtures start with a genuine verified hard link, replace the directory name after the second stage-file observation, prohibit unlink during refused cleanup, and confirm that the old operator selection cannot be silently reused. Fresh independent readback reports the moved folder link as authenticated (`publicationLink: true`) and the new same-name candidate as unreviewed (`publicationLink: false`). Independent receipt, witness and ledger evidence bytes are unchanged. The tests are offline fabricated fixtures, not production crash-durability proofs.

## Unresolved boundary

The directory path recheck and `unlinkat`-style removal via a held directory descriptor are **not atomic** against a noncooperating same-user process that can rename the directory or replace its file after the final check. A later refusal cannot undo an unlink already performed. Stage locks serialize cooperating writers only. Preserve ambiguous candidates, obtain fresh independent evidence, and never automatically retry cleanup or treat unlinked stage bytes as authenticated.

The independently retained exact tenant archive pin, existing signed receipt/checkpoint custody and detached authenticated paper preflight remain unchanged. Combined rollback of retained evidence and cross-resource power-loss consistency remain open. Production paper fills, live orders, autonomous trading and fund transfers remain disabled. Public history remains source-attributed and session-only; real-history checks remain owner-device acceptance only.
