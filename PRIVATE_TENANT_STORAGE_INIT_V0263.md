# v0.2.63 — Independent empty tenant storage initializer (dormant)

This version supplies the **missing manual, fail-closed preparation step**
between the verified encrypted owner backup and the v0.2.62 read-only
cutover preflight. It operates exclusively on the **existing paid Render
Starter service** and its already attached /data disk. No second service,
database plan, storage volume or paid subscription is required.

## What code is available

- A private interactive console script: backend/tools/prepare_private_tenant_storage.py
- A guarded engine function: backend/engine/permanent_storage_init.py
- Synthetic negative tests: backend/tests/test_permanent_storage_init_v0263.py

The operator must first independently verify a fresh off-service encrypted
owner backup, a successful isolated restore, and the separate owner-token and
credential-encryption-key recovery material. The operator approval phrase
is a safety gate, **not proof that those prerequisites passed**.

The script requires an existing private 0600 owner file and its recognized
legacy tables at /data/edgepilot.db, exact destination
/data/edgepilot-tenants.db, explicit local opt-in
EDGE_PERMANENT_STORAGE_INIT_ALLOWED=true, and the v0.2.58 separate-storage
preparation gates EDGE_SHARED_TENANT_DB_PREPARE=true and
EDGE_TENANT_SCHEMA_PREPARE=true. It refuses all live worker/order switches,
staging, identity/member signup, Public credentials, account reads, monitoring,
passkeys and tenant-only API retirement.

From the trusted interactive console on the paid service (never an
unauthenticated HTTP request), and **only after independently verifying the
backup and recovery evidence**, temporarily supply these flags and run
python tools/prepare_private_tenant_storage.py from the backend directory.
Do not change persistent production environment flags to accomplish the
console-only preparation. The script then prompts for the literal approval:

PREPARE ISOLATED EDGEPILOT STORAGE

The initializer reads the legacy DB in read-only/query-only mode, builds an
empty tenant foundation and Argon2id identity schema in a uniquely named
0600 same-disk staging file with restrictive process umask, verifies
schema/integrity and zero memberships, and atomically publishes via a
no-replace hard link. It removes only its own staging file. It will NOT
overwrite or import any existing tenant DB. If the destination already
exists, stop and use the read-only preflight rather than rerunning this
one-time initializer.

## After preparation

Inspect using v0.2.62 read-only preflight in another explicitly gated,
interactive console operation. A passing database inspection cannot attest
to the off-service backup, encryption keys, an independent owner login, or
real two-device account isolation. First-owner bootstrap (v0.2.60) remains
a distinct manual step that needs independent approval and correct runtime
isolation. Legacy owner login stays accessible until deliberate successful
owner enrollment and tenant-only retirement.

Do not publish secrets in GitHub, ChatGPT, Android screenshots, build logs,
or environment dumps. No live brokerage orders, autonomous trades or bank
transfers are enabled or authorized. No code or Render deployment from this
milestone actually initializes production storage; this only prepares a
safely callable operator tool.
