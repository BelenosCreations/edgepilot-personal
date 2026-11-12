# v0.2.74 — Recoverable first owner + verified Public connection

**Operator checkpoint, November 12, 2026.** The user provided an
Android screenshot showing a saved encrypted Public connection,
provider discovery of a brokerage account, and a linked Public
BROKERAGE with **ownership verified**. No account identifiers or
secrets are repeated here. The existing legacy Public account
was never migrated. Portfolio balances, trading, bank transfers,
monitoring, member signup and workers remain disabled.

The earlier v0.2.70 encrypted first-owner backup predates the linked
Public account and refuses active sessions/feature flags, so it
cannot correctly capture the current new tenant credentials.
This v0.2.74 operator-only separate archive uses the same
pre-existing, phone-held 32-byte offline recovery key, but a
distinct magic header (EDGEPILOT-TENANT-LINKED-BK1).
It also verifies that the existing server Fernet credential key
can decrypt active encrypted Public secrets WITHOUT printing them.

**Live databases are read-only.** The tool requires a private,
singleton owner on the pre-existing paid `/data` disk and at least
one valid, linked Public account. It copies a consistent SQLite
snapshot to private `/dev/shm`, then deletes browser session
hashes and failed-login tracking entries ONLY INSIDE THE RAM
SNAPSHOT. It AES-256-GCM encrypts that SQLite snapshot, publishes
an immutable no-overwrite private 0600 ephemeral archive and tests
decryption and restored relational integrity into a NEW isolated
RAM file. No browser is signed out because live sessions are untouched.
The original owner DB and tenant DB cannot be written by this tool.

Prerequisites: merged-main GitHub tests and existing Render deploy
for v0.2.74 pass, `EDGE_TENANT_PUBLIC_DISCOVERY_ONLY=true`,
stable server `EDGE_CREDENTIAL_KEY`, disabled worker and orders,
no tenant-only mode, and the user's private recovery key file
on Android:
`~/.local/share/edgepilot/recovery-key.b64`.

**Operator command from LOCAL Termux** (if SSH prompt shows
`root@...`, type `exit` first):

```bash
cat "$HOME/.local/share/edgepilot/recovery-key.b64" |
  ssh -i "$HOME/.ssh/edgepilot_render" srv-dbocnb3m8hqs7386trvg@ssh.ohio.render.com   'cd /app && EDGE_TENANT_LINKED_BACKUP_ALLOWED=true python3 tools/backup_linked_owner_tenant.py --approve "BACK UP LINKED EDGEPILOT ACCOUNT"'
```

Output includes the *temporary* server archive
`/dev/shm/edgepilot-tenant-linked-YYYYMMDD-HHMMSSZ.epbk`,
`backup_verified=true`, `isolated_restore_verified=true`,
`credential_decryptable=true`, `restored_login_sessions=0`,
a sanitized archive SHA-256 and
`off_service_copy_verified=false`.

**Immediately copy archive off Render** with a safe SSH read
to a private `~/.local/share/edgepilot/backups/` temporary
file, compare downloaded file SHA-256 to the printed value,
rename only if target filename does not already exist, and
upload the encrypted archive to the existing private Drive
`Edgepilot backup` folder. DO NOT delete any old backup
or overwrite files. Keep the phone-side backup key and GPG
credential-key recovery independent of Google Drive archives.
Do not transmit the Public API secret or the recovery key in chat.

**Important restoration limitation:** The archive contains
Fernet-encrypted Public credentials but not the separate Render
Fernet encryption key. Actual recovery needs BOTH the phone's
AES archive key and the previously backed-up server credential
key. Restored login sessions are deliberately cleared, so
the user must sign in again. No production restore automation
or brokerage trading authorization is supplied.

**No new service, APK update, live trading, bank transfers,
portfolio reads, new member signup or credential migration.**
