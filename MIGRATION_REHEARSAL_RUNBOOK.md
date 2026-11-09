# EdgePilot — Phase 4 offline migration rehearsal runbook (v0.2.10)

**STATUS: Code and tests only. NO production backups, restores, account
migration, user activation or Public credential movement performed.**

This runbook prepares an isolated, encrypted backup/restore rehearsal for a
**future approved maintenance window**. A passing rehearsal is NOT permission
to start migration. The hosted EdgePilot server and Android app do not load or
run the migration scripts.

## Scope and protections

- `backend/engine/migration_preflight.py` supports read-only schema/integrity
  inspection, an encrypted **consistent SQLite backup**, authenticated
  restoration to a **new** file, and a temporary end-to-end rehearsal.
- `backend/tools/migration_rehearsal.py` is an offline-only operator command.
  It has **no migration command** and is not connected to Flask, Render
  startup or any background worker.
- Backups use AES-256-GCM (random 96-bit nonce) with tamper detection and an
  encrypted SHA-256 digest of the SQLite snapshot. Encryption is streaming,
  so it does not require loading the entire database into memory. Archive
  file and temporary files are mode 0600; temporary working directories 0700.
- SQLite's native backup mechanism captures committed WAL records. Before
  backup, source and snapshot must pass integrity/foreign-key checks and
  match schema/row-count inventories.
- Test restores check authenticated encryption, SHA-256 digest, SQLite full
  integrity, foreign keys, table counts and schema hash before a new file is
  published. Existing outputs are NEVER overwritten.
- Sanitized JSON reports contain only table names/counts, schema/checksums,
  and booleans — **not** Public credentials, encrypted blobs, Public account
  IDs, user labels, financial values or session tokens.

## Preconditions before *any* real-system rehearsal (not done yet)

1. Obtain explicit approval and schedule a maintenance window. Coordinate a
   bounded pause of the legacy worker and freeze all DB writers before
   comparison or migration. Preserve current Observe settings and plan a
   supervised restart. A consistent online backup alone does NOT prove that
   account settings were frozen throughout the rehearsal.
2. Prepare an isolated, trusted machine with encrypted storage and enough
   free space for a temporary unencrypted SQLite snapshot, encrypted archive
   and decrypted test restore. Temporary file removal is **not secure erase**;
   use whole-volume encryption or appropriately managed encrypted scratch.
3. Securely generate a NEW independent random 32-byte key, base64-encode it,
   store it in an external trusted secret manager and inject only via
   `EDGE_BACKUP_KEY_B64`. The key is not a Public API key. Do not use a
   personal password or paste the key into chat, GitHub, shell arguments,
   screenshots, changelogs, or logs.
4. **Separately escrow** all necessary production secret-management recovery
   information, including Render's `EDGE_CREDENTIAL_KEY` encryption key and
   any legacy Public credential source, using approved secure procedures.
   The encrypted database archive does not contain these environment
   variables. Never put them into the archive or repository.
5. Copy/prepare an approved SQLite snapshot on the isolated environment.
   Do not point the script at the production `/data/edgepilot.db` unless a
   separately approved operational procedure explicitly authorizes it.

## Examples for a future isolated test only

Set `EDGE_MIGRATION_TOOLS_ENABLED=true` and
`EDGE_BACKUP_KEY_B64` in the local, secure process environment.

    python backend/tools/migration_rehearsal.py inspect --database /secure/test/edgepilot.db

    python backend/tools/migration_rehearsal.py rehearse \
        --database /secure/test/edgepilot.db \
        --approve "REHEARSE OFFLINE ONLY"

To create a persistent encrypted archive in a separately approved storage
location (never inside GitHub or a shared downloads folder):

    python backend/tools/migration_rehearsal.py backup \
        --database /secure/test/edgepilot.db \
        --output /secure/offsite/owner-backup.epbk \
        --approve "REHEARSE OFFLINE ONLY"

Test-restoring to a **new**, disposable path:

    python backend/tools/migration_rehearsal.py restore-test \
        --archive /secure/offsite/owner-backup.epbk \
        --output /secure/test/restore-copy.db \
        --approve "REHEARSE OFFLINE ONLY"

Keep the encrypted archive, decryption key and recovery materials physically
and logically separated. Record an independently stored archive SHA-256 and
a redacted rehearsal result, plus the approved restore operator's identity.

## STOP conditions and separate activation gates

Stop on corruption, checksum mismatch, unexpected row count/schema drift,
missing recovery keys, insufficient scratch storage, worker activity, or
unverified account identity. Do **not** activate tenant feature flags.

This release does not implement or authorize mapping the legacy account and
history to a new tenant ID. The existing single-user credentials, session,
balances, risk controls, worker journals, and Public connection continue
unchanged. Full rollback/migration implementation, multi-user activation,
per-account live provider adapters and app account switching all require
new approvals and separate security tests. Live trading and bank transfers
remain disabled.
