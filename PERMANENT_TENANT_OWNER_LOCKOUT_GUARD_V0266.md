# v0.2.66 — Deny tenant-only startup until first real owner identity exists

The default-off EDGE_PERMANENT_TENANTS_ONLY switch retires the legacy
owner API and dashboard. Enabling it before an independent owner's
identity exists could lock the original owner out of the only working
login. This milestone closes that source-code authorization gap.

Every tenant-only startup now checks a pre-existing PRIVATE 0600
regular tenant SQLite database (not an automatically created empty
file), SQLite integrity and schema separation, exactly one active
owner role with an Argon2id password identity, and fully paired
member identities. It reads no owner passwords, API secrets,
ciphertexts or balances. If anything is missing, startup fails
closed rather than silently retiring the original dashboard.

This is a *technical* safeguard only. Owner account existence is
not proof the human owner can successfully log in, recover forgotten
passwords, enroll a real Android passkey, access the broker or
operate on two independent physical devices.

## Operator cutover order

1. Independently preserve and rehearse encrypted owner DB recovery,
   owner-token recovery, and stable Fernet credential-key recovery.
2. Using the v0.2.63 console initializer, prepare the private tenant
   file on the existing paid /data volume, if none exists.
3. Inspect private schemas with v0.2.62, then inspect empty
   owner-readiness with v0.2.65.
4. Only with an operator-controlled v0.2.60 console bootstrap,
   create the first separate owner login; then use v0.2.65 again
   to verify the database's owner/identity pairing.
5. Independently test real owner login/recovery on the target
   host and physical device. Record a rollback plan before
   eventually enabling tenant-only routing.
6. Independently authorize and test Public read-only tenant keys;
   keep all orders, live automation and bank transfers disabled.

Never change permanent Render flags merely because CI or this
read-only readiness check passes. The actual production tenant file
and independent owner may still not exist. No new paid resources.
