# EdgePilot v0.2.28: Invitation-only tenant registration (opt-in)

## Scope

This is an additive server-side identity enrollment path for the future shared
backend. It does not activate a brokerage integration, passkeys, an owner
session, real trading, transfers, or any production tenant migration.

Default EDGE_TENANT_SIGNUP_ENABLED=false. Enabling registration requires:
EDGE_TENANT_SCHEMA_PREPARE=true, EDGE_IDENTITY_AUTH_ENABLED=true, and
EDGE_TENANT_SIGNUP_ENABLED=true. The endpoint POST /api/identity/register
accepts exactly invitation, username, password and displayName in same-origin
JSON over HTTPS. No role or user ID is caller-supplied; registration always
creates a member who must log in separately.

## Operator-only invitation issue

A trusted server-side operator may create a one-time 256-bit invitation:

    from engine.tenant_registration import TenantRegistration
    invitation = TenantRegistration("/secure/path/to/edgepilot.db").issue_invitation(
        ttl_seconds=3600
    )["invitation"]

Never store or commit the invitation in source, logs, screenshots, URLs or
GitHub. Only the SHA-256 digest is retained server-side. TTL is 1 minute to
7 days. Invitations are single-use, cap-limited and expire automatically.
There is NO HTTP invitation issuance endpoint.

## Security and recovery

Registration requires same-origin requests and a source-hash attempt budget;
do not accept arbitrary forwarded-client-IP headers as trusted proxy identity.
Argon2id hashes passwords. A tenant user, identity and audit event commit
atomically with invitation redemption, including simultaneous registration
races. Failed duplicate usernames roll back user creation and do not consume
the invite. No login session or Public connection is automatically created.

Legacy owner APIs remain separate. A member identity cookie cannot call the
legacy dashboard, worker, order, transfer or credential paths. Existing Public
vault and read-only adapters remain behind independent feature gates.

A supported production release still requires verified contact ownership,
credential recovery and revocation workflows, password reset abuse controls,
Android WebAuthn/Credential Manager integration, isolated workers and
backup-restore tests, and real two-device acceptance. This feature is
default-off in the merged app and has no signup UI yet. Do not activate the
feature flag until operational provisioning and risk review are complete.

## Validation

Run complete Python/Flask tests, compilation and JS checks, plus post-merge
CI. Regressions cover invitation replay/expiry, duplicate login rollback,
simultaneous one-use redemption, rate limiting, invalid input, cross-origin
rejection, two separate identity cookie jars and isolated synthetic Public
vault contents. No test makes a real brokerage request.
