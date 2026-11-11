# v0.2.64 — Owner Public credential vault-key recovery (inactive)

The encrypted .epbk database backup and the GPG owner access-token recovery
file are NOT enough by themselves to unlock the owner's encrypted Public
credential. That uses a separate stable Fernet EDGE_CREDENTIAL_KEY saved in
the Render environment. This milestone provides a private, read-only,
default-off verification of independently backed-up recovery material.

## Operator-only proof

After independently obtaining the old key from separate secure custody,
an authorized operator on the already paid Render service may temporarily
enable EDGE_OWNER_VAULT_RECOVERY_AUDIT_ALLOWED=true in the interactive
console context and run:

    python tools/verify_owner_vault_recovery.py

The script requires the exact private owner /data/edgepilot.db with
recognized legacy schema, and refuses active workers/orders, tenants-only
routing, staging, signup and tenant Public features. It asks for the exact
approval phrase VERIFY OWNER VAULT RECOVERY, then asks the operator to enter
the saved Fernet recovery key through a hidden terminal prompt. Never put
the key in command arguments, logs, source files or chat messages.

The code compares the entered key to the running server key in constant
time, reads saved owner ciphertext using SQLite mode=ro and query_only,
and authenticates/decrypts privately with Fernet. It prints only boolean
results and cannot change owner records, return secrets or contact Public.
A missing or tombstoned encrypted credential cannot prove decryption;
the result explicitly distinguishes key match from ciphertext verification.

A cryptographic match still does NOT prove the independently entered key
was actually secured offsite, that it remains valid with Public, or that
production tenant features can be activated. Those require separate
operator evidence and later authorized read-only real-account acceptance.
Never rotate or remove the running key to make this test pass.

No extra hosting, database, disk, deployment flag change, new identity,
live order, autonomous trading or transfer is enabled by adding this code.
