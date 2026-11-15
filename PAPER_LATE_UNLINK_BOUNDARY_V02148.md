# Late-unlink boundary and operator-only review

The v0.2.147 final directory-name check is useful for detecting a replacement **before** the check. It is not atomic with `os.unlink(stage_name, dir_fd=folder_fd)`. A different process running under the same user can still change the filename or rename the selected directory after that check, even when the cleanup holds a staging-directory `flock`; an uncooperative process need not honor the lock.

## Synthetic boundary cases

The tests run the actual offline terminal receipt and active checkpoint cleanup paths with independently authenticated publications and a verified staging hard link. They interpose at the existing `os.unlink` boundary, after all identity checks:

- **File-name swap:** a competing process renames the verified hard link within the held directory, then places unreviewed bytes under the expected staging filename. The original unlink removes **those unreviewed bytes**. The later link-count readback refuses cleanup; the authenticated publication and renamed hard link survive. Thus a refusal does not establish that no unreviewed data was deleted.
- **Directory-name swap:** a competing process renames the whole selected stage directory and installs a new same-name directory containing unreviewed bytes. The original unlink targets the **held directory descriptor**, removing the verified hard link from the renamed directory. The final directory identity check then refuses. The replacement filename survives, and the authenticated publication still exists with one link.

In both cases fresh authenticated `include_stages=True` inventory describes the state *after* the ambiguous attempted cleanup. The independently retained receipt, witness and ledger bytes are unchanged. Inspecting the current state cannot reconstruct deleted unreviewed file content or prove a specific race mechanism.

## Operator-only safe boundary

When competing same-user writers cannot be excluded, **do not call** `cleanup_local_terminal_stage` or `cleanup_recovered_stage`. Prefer `inspect_local_terminal(..., include_stages=True)` or `inspect_recovered(..., include_stages=True)` with exact independent signed evidence. Preserve returned stage names and metadata for manual analysis; unlinked files and unreviewed stages must never be assumed authenticated or automatically deleted/repaired. Independently control the reviewer's filesystem access before any destructive cleanup. An eventual reversible, collision-safe retention mechanism could reduce irreversible loss, but is *not* implemented or established secure in this milestone.

Focused CI now runs `test_tenant_paper_promotion_checkpoint_v02114.py` ahead of the complete backend regression. Both paths remain offline synthetic research only: authenticated paper preflight is detached from execution and the separately retained exact tenant archive pin is unchanged. Combined rollback of all retained evidence and cross-resource power-loss consistency remain unresolved. Production paper fills, live trading, autonomous orders and bank transfers remain disabled. Public history remains source-attributed and session-only; real data is reserved for targeted owner-device acceptance.
