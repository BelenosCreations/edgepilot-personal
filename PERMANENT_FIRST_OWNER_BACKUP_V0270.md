# v0.2.70: Protected first-owner tenant identity recovery archive

The legacy encryption backup tool requires an original single-user
"settings" table and cannot back up the separate tenant identity
database. The existing tenant_backup_rehearsal is for synthetic RAM
fixtures only, NOT /data/edgepilot-tenants.db.

This version adds a dormant console tool for exactly one newly enrolled
owner in a separate private tenant database. It copies an SQLite-consistent
snapshot into private /dev/shm, checks SQLite integrity and exactly one
active Argon2id identity with no sessions, encrypts with AES-256-GCM using
the separate base64 backup key supplied ONLY through standard input,
publishes a new 0600 RAM archive without overwrite, and verifies a
full authenticated read-only restore into a different private tmpfs file.
The decrypted files are deleted after verification. Owner and tenant
production databases are never changed by this tool.

All worker, staging, trading, real tenant identity/public account and
bank switches must remain dormant. The tool is not imported by Flask
or called by Render startup.

From LOCAL Android Termux (after exiting the remote SSH shell), supply
the phone's previously verified private backup key directly via SSH:
cat "$HOME/.local/share/edgepilot/recovery-key.b64" | ssh -i "$HOME/.ssh/edgepilot_render" srv-dbocnb3m8hqs7386trvg@ssh.ohio.render.com 'cd /app && EDGE_TENANT_OWNER_BACKUP_ALLOWED=true EDGE_SHARED_TENANT_DB_PREPARE=true EDGE_TENANT_SCHEMA_PREPARE=true EDGE_TENANT_DB_PATH=/data/edgepilot-tenants.db python3 tools/backup_permanent_owner_tenant.py --approve "BACK UP PRIVATE EDGEPILOT OWNER"'

The output confirms backup_verified, isolated_restore_verified,
first_owner_count=1, archive_private_0600, and prints archive_sha256.
The archive is STILL ONLY in Render's volatile /dev/shm, named
edgepilot-tenant-owner-YYYYMMDD.epbk using the Render UTC date.
The operator must copy it into the phone's PRIVATE backup directory
without overwrite, compare SHA-256, and upload it to their private
Google Drive backup folder. Do not confuse a temporary server archive
with an off-service backup. Never put keys into shell arguments,
screenshots, GitHub files or Render environment logs.

The distinct EDGEPILOT-OWNER-TENANT-BK1 archive is limited to a
16 MiB first-owner snapshot. This is not a production restore
endpoint or general multi-user long-term backup scheduler.
No login/pilot/passkey activation, legacy owner migration, live
orders, funds transfers or paid services are enabled by this release.
