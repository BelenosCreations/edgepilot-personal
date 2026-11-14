# Staging inventory after publication interruption

Pass `include_stages=True` to `inspect_local_terminal` after an interrupted
offline terminal receipt publication. Use the independently retained exact
receipt and signed terminal record as for ordinary readback. For
`inspect_recovered`, supply the independently retained `recovery_receipt`
in addition to the signed checkpoint export, exact promotion evidence and
audited ledger.

When the destination is absent, the result includes `publicationMissing:
true`, the exact receipt, and the matching stage inventory. Each entry's
`publicationLink` is false because the destination has no published inode.
The scan reads direct stage names and metadata, including an expected
filename if present. Stage contents remain unauthenticated. The scan
preserves candidates, symlinks and sidecars for operator review. A late
destination, a destination SQLite sidecar or changed independent evidence
causes the operation to refuse.

An authenticated existing publication retains its established result
format. Explicit cleanup requires that publication and a verified hard
link. It checks the selected name again immediately before unlink.
Cooperating writers use the staging-directory lock. The pathname check and
unlink are separate operations, so a noncooperating same-user process can
still race the final check.

The tests exercise process exit before exclusive publication and a
same-name replacement after the first staging-file observation.
Combined rollback of retained evidence and cross-resource power-loss
consistency remain open. Tenant archive recovery retains its separate exact
pin. Authenticated paper preflight remains detached from execution.

Synthetic Public history checks cover the source and cleared session data.
See [Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2)
and [owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
