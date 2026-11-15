# No-overwrite stage-directory operator rehearsal (synthetic/Linux only)

The v0.2.149 whole-directory `os.rename` prototype can overwrite an empty directory or symlink holding target, and repeating a rename for rollback can overwrite a separately created destination. This milestone tests an **alternative**, `renameat2` with `RENAME_NOREPLACE`, available on the Linux CI runner. The source parent and holding parent are opened with directory descriptors, and both directions of movement use no-overwrite semantics. **The code exists inside the offline unit tests only**; there is no recovery-engine, Android, backend route, or background operator action.

The ten synthetic tests (five scenarios for terminal receipt and five for checkpoint) use a verified staging hard link and separate independently authenticated receipt/witness/ledger evidence:

- **Uncontended park/restore:** the same stage directory inode and note move into and out of a reserved holding parent. The publication remains independently authenticated throughout; ordinary prefix-scoped stage inventory cannot see the parked location until it is restored.
- **Late empty-directory target:** the destination is populated with an empty directory after the initial selection, before the kernel move. `RENAME_NOREPLACE` refuses with `EEXIST`, preserving both source and target directories, unlike plain rename.
- **Late symlink target:** the destination becomes a symlink. The move refuses with `EEXIST`, preserving the symlink and the original staging directory without following the link.
- **Source substitution:** the authentic stage is relocated under a matching stage-prefix name, and an unreviewed directory replaces its original name before the move. No-overwrite cannot authenticate **the source**; it moves the unreviewed directory, the post-move inode recheck refuses, and both the real verified link and unreviewed candidate are preserved without automatic rollback.
- **Rollback collision:** after a valid park, a separate unreviewed staging directory occupies the original name. Reverse `RENAME_NOREPLACE` refuses with `EEXIST`; both the parked verified link and the unreviewed name are retained.

## Security and recovery boundaries

Linux no-overwrite protects only destination name collision at the operation boundary; it does **not** make source identity checks atomic, protect a same-user writable holding namespace, authenticate loose stage bytes, prove power-loss durability, or resolve combined evidence rollback. A parked directory remains outside the normal stage-prefix inventory; an independent reviewable location record and controlled access would be prerequisites to operator use. The prototype must **not** be treated as production-safe cleanup, automatic rollback or a new trusted publication route.

The original independent tenant-archive pin, signed witness and receipt custody, and detached paper preflight are unchanged. Production paper fills, live trading, autonomous orders and bank transfers remain disabled. Public market-history research remains source-attributed and session-only, with any real history limited to targeted owner-device acceptance.
