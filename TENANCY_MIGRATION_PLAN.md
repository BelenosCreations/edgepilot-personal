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
