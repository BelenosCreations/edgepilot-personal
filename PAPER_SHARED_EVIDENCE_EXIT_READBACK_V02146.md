# Shared-evidence publisher exit readback

The offline synthetic receipt and checkpoint publisher now have a second regression path that uses the exact same independent evidence files as the reviewing process. Unlike the v0.2.145 competing-publisher scan test, no cloned evidence store is used. Each publisher is a forked child, stopped with a real process exit immediately before or after `os.link`. The reviewer waits for that exit and starts a fresh authenticated inspection after the child releases its SQLite locks.

## Observations an operator may rely on

- **Before link:** Default `inspect_local_terminal` or `inspect_recovered` refuses the missing publication. With `include_stages=True` and required current independent evidence, `publicationMissing: true` lists only the stage's immediate names and metadata. `publicationLink: false` does not authenticate the stage content, and must not authorize a retry or cleanup.
- **After link, before stage retirement:** Authenticated readback returns `additionalLinkPresent: true`; stage inventory identifies the specific entry with `publicationLink: true`. This proves the selected hard link belongs to the authenticated publication at review time. It does **not** prove a unique crash point, exclusive link ownership by other processes, or the state of unlinked stages.
- **After explicitly reviewed cleanup:** The selected matching stage hard link is removed and `additionalLinkPresent: false`. The stage directory is retained, and the earlier unreviewed candidate and independent witness, receipt, ledger and archive evidence are unchanged.

Both terminal receipt and active checkpoint paths exercise the sequence in tests. A checkpoint missing from storage still requires a separate `recovery_receipt`. Inspection only reports current, authenticated state and refuses mismatched evidence; these rehearsals do not add a production recovery route or enable paper fills.

The independently pinned tenant archive is unchanged. Authenticated paper preflight remains detached from execution. Symlinks, sidecars and noncooperating writers may require separate operator intervention; final path review and unlink are not atomic against a noncooperating same-user process. Combined rollback of all retained evidence and cross-resource power-loss consistency remain open.

For Public market history, retain source attribution and session-only data without claiming retention/redistribution rights. Real-history acceptance remains targeted to the owner's device as described in [v0.2.110 acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
