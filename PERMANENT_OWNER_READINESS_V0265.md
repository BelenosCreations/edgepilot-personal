# v0.2.65 — Independent owner readiness inspection (inactive)

This milestone adds a manual-only, read-only inspection for the interval
between a deliberately prepared separate tenant database and an eventual
independent EdgePilot owner login. The existing paid Render Starter
instance and 1 GB /data disk remain the sole permanent backend.

The operator first completes and independently verifies the owner
encrypted offsite DB backup and isolated restore, owner-token recovery,
and separate credential key backup, then prepares the tenant DB using
v0.2.63. The initial owner is only created by the existing separate
v0.2.60 console bootstrap operation, never by this inspection.

## Manual inspection, no mutation

In a **trusted interactive console** on the existing paid service,
temporarily set these command-local variables (not permanent Render
environment toggles):

    EDGE_OWNER_READINESS_AUDIT_ALLOWED=true
    EDGE_SHARED_TENANT_DB_PREPARE=true
    EDGE_TENANT_SCHEMA_PREPARE=true
    EDGE_TENANT_DB_PATH=/data/edgepilot-tenants.db

Then run from /app:

    python3 tools/inspect_permanent_owner_readiness.py

The script requires the fixed legacy and tenant database filenames,
private 0600 regular files, separate inodes, valid legacy/identity
schemas, SQLite integrity, no foreign-key violations and all
dangerous live and tenant-only flags turned off. All SQL reads are
read-only, query-only; it does not log usernames, account numbers,
password hashes, ciphertext or API keys.

With zero tenants, it reports that the next human-operated task is
manual first-owner bootstrap. With exactly one valid non-disabled
owner and corresponding independent password identity, it reports
the next step as an independent login test, **not** that login has
actually happened. Unexpected duplicate owners, missing identities,
inconsistent member records and unsafe files are denied.

A successful report always states that real owner login, Public
ownership, second physical device, and historical owner migration
have not been verified. Passing is NOT approval to turn on
EDGE_PERMANENT_TENANTS_ONLY, passkeys, Public API connections, live
orders, automated trading or bank transfers. No production settings
are changed merely by merging or deploying this tool.
