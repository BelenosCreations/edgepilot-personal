## Phase 5 (v0.2.11): Isolated owner shadow mapping rehearsal (NOT a live migration)

An offline-only owner-to-tenant staging rehearsal now exists:
`backend/engine/owner_shadow_migration.py` and
`backend/tools/owner_shadow_rehearsal.py`, with the procedure and blockers
in `OWNER_MIGRATION_SHADOW_RUNBOOK.md`. The tool reads only an already
restored, isolated database copy, uses SQLite backup to create a second
throwaway working copy, verifies the legacy encrypted Public credential using
an externally supplied vault key, and creates a *dormant* user, account,
credential connection, quarantined settings and fully traceable history
mapping in the temporary copy. All source records are left unchanged.

It will refuse the live `/data` mount, a wrong key, conflicting account
references, existing tenants, missing selection or invalid history. It
reports pending legacy history/automation tables as blockers. **There is
no live migration operation, new login provisioning or tenant activation,
and no changes to Render feature flags.** Production migration will require
new explicit approval, a fresh encrypted backup and a maintenance window.


## Phase 4 (v0.2.10): Offline migration backup and restore rehearsal (NOT executed)

Source-only tools have been added under `backend/engine/migration_preflight.py`
and `backend/tools/migration_rehearsal.py`, with instructions in
`MIGRATION_REHEARSAL_RUNBOOK.md`. They do not connect to Flask or start in Render.
They support sanitized read-only database inspection, streaming AES-256-GCM
SQLite backups, authenticated restore to a brand-new destination, and a
full temporary restore rehearsal. Opt-in requires
`EDGE_MIGRATION_TOOLS_ENABLED=true` and an explicit operator approval phrase.
The original database and all existing owner data are untouched.

**No live backup, production validation, account migration or switch-over
has occurred.** A future explicitly approved maintenance window must freeze
writers, preserve both the independent backup key and separate Render Public
credential vault key, verify recoverability on encrypted scratch, document
row counts and checksums, and confirm the owner’s account details before
any migration script is built or used. Avoid uploading backup files or keys
to GitHub or chat. A successful dry run does not enable other users.


## Phase 3 (v0.2.9): Dormant account-scoped authorization and journals

The new `account_scope` module prepares isolated tables for portfolio snapshots,
observation cycles, account-level worker leases, and a fail-closed per-account
runtime status: Observe selected, worker/paper/live enabled flags all ZERO.
The scoped store requires the session principal from `IdentityStore.principal`
and checks ownership/active status against both `tenant_accounts` and the
owning Public connection. Cross-user or revoked account access fails closed.

The additional independent activation gate is
`EDGE_TENANT_ACCOUNT_READS_ENABLED=true` alongside the previous
`EDGE_TENANT_SCHEMA_PREPARE=true` and
`EDGE_IDENTITY_AUTH_ENABLED=true`. All remain **false by default**.
These gates are NOT being enabled in Render. Even when they are enabled in
an isolated test environment, only read-only identity endpoints can list
authorized accounts and show stored summaries:
`GET /api/identity/accounts` and
`GET /api/identity/accounts/<id>/summary`.
These routes do not call Public or scan markets, and cannot place orders.
Each uses only the verified cookie identity, not an HTTP user_id parameter.

The *future* per-account worker storage has separate transactional leases,
with one active worker per account and no cross-account status mutation. It is
not wired to the existing single-account observation worker, broker adapter,
or an Android control. There are no tenant worker threads, live quote calls,
or records initialized from the existing account. New portfolio balances
in tests are synthetic test fixtures, not actual account values.

**Remaining required gates before migration or shared use:**
- External review of Public Individual API terms for each deployment model.
- Verified full backup + restoration rehearsal of current SQLite and encryption
  material; require owner approval before initiating any live migration.
- Build a provider-authenticated per-account brokerage adapter, credential
  rotation and least-privilege account selection; bind account IDs to their
  exact owning connection and fail closed on token mismatches.
- Refactor and test **every** existing route, worker, cache, accounting,
  history and risk allocation path to use authenticated tenant/account context
  (not just the new read-only routes). Provide an isolation test matrix.
- Integrate worker scheduling, per-account quotas and alerts; preserve existing
  saved Observe state and avoid silent service interruptions during cutover.
- Develop owner self-account switching, admin invitations, MFA/passkeys,
  recovery, revocation and an audited staged rollout. No user sign-up is
  currently permitted.


## Phase 2 (v0.2.8): independent identity authentication (still inactive)

The separate Argon2id identity module now supports backend-internal identity
provisioning and user-bound four-hour web sessions. It introduces no self-service
registration endpoint and **does not** share credentials or permissions with
the existing single-user EdgePilot login.

Two explicit flags are required to enable the identity-only routes:
`EDGE_TENANT_SCHEMA_PREPARE=true` and
`EDGE_IDENTITY_AUTH_ENABLED=true`. Both currently default to false. **Do not
enable either flag on the production service** until after the supervised
migration and end-to-end route scoping review. No such flags are being modified
in Render by this release.

When eventually enabled in an isolated environment, only these scoped routes
are permitted: POST `/api/identity/login`, GET `/api/identity/session`, and
POST `/api/identity/logout`. They use a separate Secure/HttpOnly
`__Host-edgepilot_identity` cookie and `X-Edge-Identity-CSRF` request header,
and have **no authorization to the legacy /api dashboard, Public connections,
accounts, settings, automation, historical records, trading or transfers**.
Provisioning is internal-only: no public user-creation, recovery or invite API.

Operator-controlled first-user enrollment, password resets, second factors,
permission boundaries, backups, account migration and controlled deprecation
of legacy tokens are **separate future tasks**. Never tell another person to
reuse your existing EdgePilot token. A login API being present in source code
does not make EdgePilot suitable for shared deployment.


# EdgePilot multi-user / multi-account foundation — Phase 1 (v0.2.7)

**Status: source-code foundation only. Disabled by default.**

This phase adds isolated, foreign-key-constrained SQLite tables and internal
tenant repository helpers. It **does not** register users, allow a second
login, expose HTTP endpoints, change the Android APK, switch Public accounts,
move any owner data, or alter the experimental Observe/Paper worker.

## Architecture boundaries

- The existing `settings`, `broker_credentials`, `edge_sessions`,
  `automation_*`, `paper_positions`, `activity`, historical account
  snapshots, and reconciliation tables remain single-user legacy records.
  No existing record is modified or copied by this release.
- New tenant tables: `tenant_users`, `tenant_connections`,
  `tenant_accounts`, `tenant_user_preferences`,
  `tenant_account_settings`, `tenant_audit_events`,
  `tenant_schema_meta`.
- New tenant users and their Public accounts have randomly generated internal
  IDs. An individual may have multiple independently selected broker accounts.
- Broker credentials are encrypted with the backend-held Fernet key, never
  stored in Android, an HTTP response, or cleartext database rows. Old broker
  credentials remain in the existing encrypted legacy vault.
- User-to-connection and user-to-account ownership is checked on all internal
  repository reads and writes. Database composite foreign keys prevent
  linking a second user's account to the first user's connection.
- Each provider account reference is exclusive to one user at this stage.
  Cross-user account sharing and delegated authority are **not supported**.
- There is no authenticated multi-user session principal yet. Production code
  must derive it from a trusted session after login, **never from request JSON
  or an arbitrary URL account ID**. Do not connect these internal provisioning
  methods to publicly accessible routes until that exists.

## Production safety

`EDGE_TENANT_SCHEMA_PREPARE` defaults to `false`. The existing hosted
application continues behaving exactly as before. Setting this environment
variable to `true` would only create empty tenant tables on startup.
**Do not enable it yet** without the separately approved migration and
rollback procedure. This phase intentionally does not set or modify any Render
environment variables or create new live database records.

## Required migration process (future, not authorized by Phase 1)

1. Identify a maintenance window. Pause the experiment workers and block
   settings changes while migrating. Capture a full encrypted SQLite backup
   and any encrypted broker key material required for recovery, in a secure
   destination. Never put the backup or its key in GitHub/chat.
2. Rehearse restore onto an isolated temporary database and verify table
   counts, critical per-account settings, reference integrity, and decryption
   capabilities. Record backup checksum and restore outcome.
3. Create the actual owner identity only through verified admin provisioning.
   Bind the existing owner data and credentials to the correct tenant with a
   tested, reversible mapping. Migration must occur in an atomic transaction,
   preserve row IDs/provenance and never silently reassign historical records.
4. Add independently authenticated user sessions with user-bound CSRF and
   least-privilege identity enforcement; then account-specific settings and
   broker connections. Every route and worker query must be scoped to the
   authenticated user AND authorized account.
5. Run cross-user/cross-account authorization tests including forged account
   IDs, cross-user credential references, racing worker leases, API failures,
   invite revocation and historical data retrieval. Require no cross-tenant
   reads, writes, or trading actions.
6. Roll out through a deliberate, reversible feature flag and verify live
   owner account values/monitoring against the backup. Abort and restore on
   mismatch; do not silently fall back to another person's credentials.

## Additional independent approvals needed

- Multi-user authentication and account switching UI.
- Live owner-data migration and first tenant account activation.
- Other-person account enrollment and Public individual API license/terms
  review before distribution.
- Per-account worker scheduling, notification preferences and platform-level
  quotas/rate controls.

Real-money order execution and all bank transfers remain disabled. The
existing single-user login is **not safe for additional people** until the
above authorization work is complete.
