# v0.2.62 — Read-only inspection before permanent cutover

The existing paid Render Starter service and attached /data disk remain the
approved permanent shared backend. This milestone adds an **operator-console
inspection only**. It does not migrate or decrypt the legacy owner database,
create accounts, rotate credentials, trigger a network request, enable broker
reads, change environment variables or create a paid resource.

## Guarded inspection

The separate tenant file must already be initialized by the v0.2.58
preparation process; the legacy and tenant files must have distinct inodes,
private file permissions and recognized schemas. The inspection checks
SQLite integrity and foreign-key integrity read-only and refuses legacy
credentials appearing in the tenant file. It does not expose stored values,
account identifiers, passphrases or file paths in its output.

Only in a trusted interactive console on the **existing paid service**, after
the operator has independently verified a current encrypted off-service backup
and successful restore test, prepare the isolated tenant DB using the existing
documented dormant flags. Then, for the inspection command only, set
`EDGE_CUTOVER_PREFLIGHT_ALLOWED=true` and run
`python tools/permanent_cutover_preflight.py`.

The tool requires `EDGE_DB_PATH=/data/edgepilot.db`,
`EDGE_TENANT_DB_PATH=/data/edgepilot-tenants.db`,
`EDGE_SHARED_TENANT_DB_PREPARE=true`,
`EDGE_TENANT_SCHEMA_PREPARE=true`, disabled worker/orders and disabled tenant
brokerage features. The owner file and tenant file must exist. It refuses
running before preparation, unsafe permissions or an already activated
tenant-only mode.

A successful response **always** says
`production_backup_and_restore_verified=false` and
`authorized_to_activate=false`. Those questions cannot be established by
GitHub tests or remote Render metadata and require independent operator proof.
This tool does not verify the encryption key, backing up the running SQLite
WAL/journals, or actual owner recovery. A successful inspection is therefore
NOT approval to run owner bootstrap, switch routing, allow Public accounts, or
enable orders or fund transfers.

## Validation and rollback boundary

Synthetic tests create distinct temporary SQLite databases with dummy
ciphertext, verify non-mutation and denial of unsafe flags, permissions,
symlinks, and cross-file schema contamination. Neither test nor deployment
can read the live Render disk. If inspection fails, leave the old owner API
and data intact; do not delete/overwrite either DB. Continue only after
verified recovery, explicit operational review and independent two-user checks.
