# v0.2.58 — Reuse the paid Render service for permanent multi-user storage

**Approved direction, November 11, 2026:** Keep the existing paid Render
Starter service `edgepilot-private-h9tl` and its 1 GB `/data` disk as
EdgePilot's single-instance permanent multi-user backend. Do not purchase
another plan, disk, managed database or paid service. The separate Free
`edgepilot-passkey-staging` remains a disposable test environment only.
The older v0.2.57 suggestion to upgrade staging is superseded.

## What this milestone actually implements

The existing owner's `/data/edgepilot.db` continues holding the legacy
owner settings, encrypted Public secret, snapshots and Observe/Paper data.
A *separate* `/data/edgepilot-tenants.db` is now available to the
independently authenticated tenant users, sessions, passkeys, connection
vault, verified account references, read-only portfolio data and
per-account settings. Every tenant store in Flask now takes this path
rather than the original owner DB when the split is explicitly enabled.
No data, accounts, passkeys, sessions or secrets are automatically
copied from either file, and no existing key is rotated or deleted.

This is a single Render instance with SQLite, **not** distributed tenancy.
Do not scale to more processes/instances with independently mounted disks
or claim completed backups, disaster recovery, multiple phones, Public
authorization, live trading or commercial compliance.

## Safety conditions before enabling on the paid service

1. Confirm the exact existing service ID `srv-dbocnb3m8hqs7386trvg`,
   attached disk `dsk-dbocnbbm8hqs7386ts8g`, mount `/data`, existing
   environment, secrets and `EDGE_DB_PATH=/data/edgepilot.db`.
   Never attach staging to the owner's disk.
2. Verify current production database integrity, durable *encrypted*
   off-service backup and actual restore rehearsal, plus independent custody
   of `EDGE_CREDENTIAL_KEY` and existing `EDGE_APP_TOKEN`.
   Do not print, export to logs, commit or rotate secrets. An old SQLite
   backup without the original Fernet key cannot restore the Public secret.
3. Verify PR and merged-main CI for the exact revision, plus current live
   deployment health. Do not merge or deploy a failed test revision.
4. Stop the legacy global Observe/Paper worker for the storage-cutover phase:
   `EDGE_AUTOMATION_WORKER_ENABLED=false`. Ensure
   `ENABLE_LIVE_ORDERS=false` and bank transfers remain prohibited.
5. Only with those gates, configure on the existing service:
   `EDGE_SHARED_TENANT_DB_PREPARE=true`,
   `EDGE_TENANT_SCHEMA_PREPARE=true`,
   `EDGE_TENANT_DB_PATH=/data/edgepilot-tenants.db`.
   Do not independently enable `EDGE_TENANT_PUBLIC_VAULT_ENABLED`,
   `EDGE_TENANT_PUBLIC_READONLY_ENABLED`,
   `EDGE_TENANT_ACCOUNT_READS_ENABLED`,
   `EDGE_TENANT_MONITOR_PREVIEW_ENABLED` or
   `EDGE_TENANT_WATCHLIST_EDIT_ENABLED` in this milestone.
   Identity/passkey/signup remain separately gated pending recovery
   rehearsal and operator-approved activation path.
6. The app refuses a missing legacy DB, unexpected disk path, symlinks,
   hard links to the owner DB, existing tenant files readable by group/other
   or unrecognized tenant DBs. Newly created file and journals inherit
   process umask 077. Activation with any forbidden flag fails startup,
   rather than silently falling back to the owner's database.
7. Verify a redeploy and restart preserve both database files and
   re-read identity and owner records. Test cross-tenant and cross-session
   access on independent signed-in users. Authenticate and verify broker
   account ownership separately using the **per-user** Public credentials
   only after provider permission and read-only safety gates.
8. Record an encrypted, verified rollback checkpoint. Rollback should
   restore app version/configuration and original database *without*
   overwriting new tenant data. Never join or alias owner/tenant tables
   and never use one member's token as another member's identity.

## Deliberate restrictions / later milestones

- The legacy owner dashboard and its original credentials remain
  recoverable while the owner account is migrated. Tenant identities
  cannot inherit its owner cookie or use its global Public APIs.
- A separate owner enrollment/account-linking workflow and careful
  historical record attribution are still required; ambiguous legacy
  records must be quarantined, never assigned to a new member.
- The dormant tenant Public adapters and monitor worker need further
  authorization and account-specific fencing before activation.
- Current one-phone staging passkey success is not proof of two-device
  permanent deployment or successful backup/restore.
- The paid service is currently auto-deployed from `main`; merging
  safe dormant code alone does not set any migration flags.
- `render.yaml` describes earlier service creation. Do **not**
  apply it as a new Blueprint; change only the existing Render service.
- No new recurring paid services, real orders or bank transfers are
  authorized by this release. Explicit owner approval is required for
  any later live trading or transfers.
