# v0.2.71 — Strictly read-only independent owner password proof

The original Belenos-Owner was already created in the separate paid
Render tenant database and a separate AES-256-GCM encrypted tenant
backup was independently restored into a private temporary database
before its checksum-verified copy was uploaded from Android to the
user's private Google Drive backup folder.

This milestone adds a default-off private console proof that the new
owner's password matches the stored Argon2id hash WITHOUT enabling
the web login routes, issuing a session cookie, changing password,
unlocking Public, creating a member, or resetting account data.

Operator procedure on the EXISTING paid Render interactive console,
once the encrypted offsite backup has been confirmed:

    cd /app && EDGE_OWNER_PASSWORD_PROOF_ALLOWED=true       EDGE_SHARED_TENANT_DB_PREPARE=true       EDGE_TENANT_SCHEMA_PREPARE=true       EDGE_TENANT_DB_PATH=/data/edgepilot-tenants.db       python3 tools/prove_first_owner_password.py

The operator enters the password once privately at a hidden terminal
prompt. The tool verifies exactly one owner and Argon2id credential
from two independently private database files, rejects all worker,
trade, tenant-only, pilot and brokerage feature gates, and returns
only nonsecret booleans. Wrong passwords result in
first_owner_password_verified=false, not a session.

**A successful result is not a real authenticated HTTPS request.**
The first independent HTTPS login must still be separately reviewed
before setting production environment flags. Keep the current owner's
token-based login enabled and all Public tenant APIs disabled.

Real Android device authentication, two members/physical devices,
login recovery, Public ownership and live order/transfer
authorization are still unverified. No new service or fee is added.
