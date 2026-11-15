# Reversible whole-directory stage-parking prototype (synthetic only)

The previous deletion race has no guaranteed safe resolution through another identity check followed by `os.unlink`: a noncooperating same-UID writer can substitute the final pathname. This milestone tests a **non-deleting alternative** on fabricated data: reserve a same-filesystem holding directory, rename the entire observed staging directory into an unused location inside it, inspect the directory inode and independently authenticated publication after the move, and, **only if uncontended**, rename it back. This preserves stage notes, the signed receipt/checkpoint publication hard link and unrelated evidence.

The prototype is a helper **inside the offline unit-test class only**. It is not imported or invoked by the recovery engine, API, Android application or scheduled processing.

## Verified scenarios in synthetic fixtures

- **Uncontended park/restore:** terminal receipt and checkpoint cases move a directory without deleting stage bytes and restore it while maintaining the original verified hard link, stage note and independent evidence. The ordinary `include_stages=True` inventory temporarily cannot see a parked folder because its reserved holding path is not under the stage prefix; publication `additionalLinkPresent` remains true. An explicit operator record of this path would be required for future review.
- **Source-directory replacement immediately before rename:** the original verified directory is moved to another stage-prefixed name, and an unreviewed replacement becomes the source. The attempted park moves the replacement, detects the inode mismatch and refuses automatic reversal. Both the displaced authenticated stage and unreviewed candidate survive; fresh inventory identifies only the real publication link.
- **Nonempty reservation collision immediately before rename:** a competing writer populates the requested holding name with evidence. Directory rename refuses instead of overwriting the nonempty target. Both original stage and colliding evidence remain.

## Not established or approved

An ordinary `os.rename` can replace a symlink or empty directory at the destination. A same-UID opponent can also mutate a holding directory even with `0700` permissions, or substitute a source or target immediately after review. The prototype's observed identity checks are **not** atomic authorization; the successful uncontended reversal is not a safe general-purpose rollback. Do not expose this prototype as an operator API or invoke it on actual evidence. Further research must consider protected namespaces, descriptor-bound operations, no-overwrite semantics and separately controlled access. Without proven isolation from competing same-user writes, **keep destructive cleanup disabled and use authenticated read-only stage inventory**.

The existing signed evidence, independently pinned tenant archive and detached authenticated paper preflight are unchanged. Whole-evidence rollback and multi-resource power-loss consistency remain unresolved. Production paper fills, live trading, autonomous orders and bank transfers remain disabled. Public history remains source-attributed and session-only; real history checks are limited to owner-device acceptance.
