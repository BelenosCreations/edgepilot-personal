# v0.2.80 — First private-family invitation readiness, read-only

The original legacy login remains available. The **approved development architecture** is invitation-only coexistence on the existing paid Render service, not immediate legacy retirement. A separately approved production operator action is still required before allowing a second real EdgePilot account.

## Dormant readiness inspector

`backend/engine/private_family_rollout_preflight.py` is an explicitly operator-only, **read-only**, source-only preflight. It is never invoked automatically by Flask, Android, a worker, a Render deployment or CI against production. It refuses operation without an exact ephemeral `EDGE_FAMILY_ROLLOUT_PREFLIGHT_ALLOWED=true` and all of the following current-safe conditions:

- Existing private, separate `/data/edgepilot.db` and `/data/edgepilot-tenants.db` with matching fixed paths, non-symlink private file modes, one independent Argon2id owner and intact relational/SQLite integrity.
- Current existing tenant owner has at least one verified, active linked Public account whose encrypted saved credential can be recovered by the **existing** Fernet credential key. Only aggregate counts and verification status are returned.
- The current production **discovery-only** Public pilot and storage/identity flags are on, with legacy login retained. Real Public order execution, worker automation, passkeys, monitor previews, watchlist writes, staging and tenant-only retirement remain off.
- **All three invitation activation switches must still be OFF**: `EDGE_FAMILY_INVITE_COEXISTENCE_ENABLED`, `EDGE_TENANT_SIGNUP_ENABLED`, and `EDGE_PERMANENT_OWNER_INVITES_ENABLED`. The inspector also refuses a second registered member or active unused pending invitation; it specifically checks eligibility **before the first real invitation**.

The utility performs no data writes, sessions, API requests, backup exports, user creation, token issuance, authentication bypass or changes to Render configuration. It neither asks for nor prints secrets. Even a passing report deliberately returns `member_registration_authorized=false`, `external_backup_custody_independently_proven=false`, `second_physical_device_verified=false`, `second_independent_public_account_verified=false`, `live_trading_enabled=false` and `bank_transfers_enabled=false`.

## What is proven, and what is not

v0.2.74 has already produced a user-verified off-Render encrypted **first owner** backup; this preflight cannot independently prove offsite custody, restoration of its separately held keys, or recoverability of a future two-member configuration. The dormant v0.2.76 engine can rehearse a multi-member encrypted archive on synthetic data, but live post-enrollment backups would require separate operator acceptance and credential-key custody checks.

The synthetic unit tests use temporary local SQLite and dummy encrypted Public secrets to show the audit is read-only, refuses unsafe feature flag combinations, broken or missing keys, reused or pending invitations, second members, missing active account links, world-readable files and symlinks. **Passing CI is not authorization to activate the new family signup mode.**

## Operator rollout sequence (future; requires separate explicit approval)

1. Independently verify the original owner can authenticate, then reconfirm the existing legacy owner login and Public discovery-only linkage on the live domain. Do not copy any API key or recovery passphrase into GitHub or chat.
2. Recheck the encrypted owner backup off Render, its known checksum and both required recovery keys under separate private custody; confirm sufficient protected storage and a plan to back up the second member after enrollment.
3. Review the **sanitized** read-only readiness report from this tool under a manually controlled operator command. A pass grants no permission and must not automatically change any flag.
4. With separately approved production permission, enable only the three matching private invitation feature flags together, preserving legacy sign-in and all existing no-execution feature values. Retain a reversible rollback note and test owner-only invitation issuance and single-use registration on a second actual phone.
5. Verify second-user sessions cannot access owner/legacy accounts and that their separately supplied Public credential discovers only their own accounts; keep portfolio, monitoring, trading and fund transfers unavailable.
6. Immediately pause new invitation issuance by disabling all three invitation flags, create and independently verify an encrypted **multi-user** backup, and compare the off-service copy. Do not replace the earlier owner archive.
7. Only after explicit acceptance should any further optional passkey, portfolio, worker or execution functionality be considered; those are outside this milestone.

No real member was registered, no new paid service was added, no production flags or data were modified, and no signed APK was created in this development milestone.
