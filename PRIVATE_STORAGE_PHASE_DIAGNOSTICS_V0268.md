# v0.2.68 — Safe phase diagnostics for independent tenant database preparation

The previously verified production owner file, backup/restore, encrypted
owner-token recovery and Fernet key recovery remain unchanged. This
release adds **only nonsecret diagnostics** to the existing manual
v0.2.63 empty tenant SQLite initializer.

On failure, the trusted interactive initializer displays a fixed
`PRIVATE_STORAGE_BLOCKED_AT_...` code. Examples include:

- `RUNTIME_FLAGS`: one or more prohibited live features or worker switches
- `STORAGE_SELECTOR` or `DISK_LAYOUT`: paths/permissions or configured disk
- `LEGACY_READONLY_CHECK` or `LEGACY_RECHECK`: owner SQLite integrity or inode
- `PRIVATE_STAGE_CREATE`, `TENANT_SCHEMA_CREATE`, `IDENTITY_SCHEMA_CREATE`
- `STAGE_PRIVATE_MODE`, `TENANT_READONLY_CHECK`, `EMPTY_IDENTITY_CHECK`
- `DESTINATION_RACE_CHECK`, `STAGE_FSYNC`, `NO_REPLACE_PUBLISH`,
  `STAGE_CLEANUP`

These identifiers contain no account details, paths, credentials, SQL,
exception text or server configuration values. The initializer remains
default off, requires a trusted interactive console, exact approval,
fixed existing paid disk, separately verified encrypted backup/restore,
disabled background worker and live trading, protected old database,
empty target, and no live tenant features. Re-running after partial
publication MUST first check whether the destination exists; never
replace any existing private tenant database.

**No production initialization is performed by merging or deploying this
change.** Report the fixed phase identifier to the developer for diagnosis.
`prepared=true` still requires a subsequent independent v0.2.62
read-only storage preflight before the separately approved first-owner
bootstrap. Real two-device and Public read-only acceptance still pending.
