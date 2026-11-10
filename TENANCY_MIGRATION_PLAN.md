## Phase 22 (v0.2.32): Identity-scoped inactive monitor preview

A new default-off identity endpoint uses the server-verified principal and
linked account ID to return only a validated monitor watchlist and explicit
inactive/safety flags. The legacy Observe worker stays global and unchanged;
no scheduling, Public call or execution is triggered. Fake two-user HTTP
tests exercise revoked/disabled account and cross-owner denial. A separate
/account screen action previews the plan and rejects any claim of active
monitoring or orders. DEVELOPMENT_CONTINUITY.md now provides a durable
handoff for new ChatGPT conversations as the development project grows.
See TENANT_MONITOR_PREVIEW_RUNBOOK.md.

## Phase 21 (v0.2.27): Real read-only Public adapter behind user-scoped gates

A separately flagged HTTPS adapter can authenticate with a per-user encrypted
Public credential and list only that credential's provider accounts. It
transactionally links a user-owned internal account to a verified provider
account and can read sanitized balances/positions after revalidating the
provider's current list. Secret material/access tokens are never returned
or globally shared; revision fencing denies data read or account creation
after key rotation/revocation races. Persistent per-user/global request
budgets and strict allowlisted GET endpoints prevent accidental order traffic.

The identity-only API is disabled by default and the current owner login,
legacy Public key, watchlist, worker, trading and transfer paths are untouched.
Cross-owner simulated two-phone tests exercise a fake network; actual two-user
Public accounts and Android biometric flows remain incomplete. See
TENANT_PUBLIC_LIVE_READONLY_RUNBOOK.md.

## Phase 20 (v0.2.26): Independently encrypted Public secrets per identity, opt-in

Introduced an identity-only server vault and four gated lifecycle HTTP routes.
No public credential is assigned by a client-supplied user ID; the verified
session determines ownership. Encrypted keys are stored in tenant_connections
and are rotated/revoked only for the same identity; rotating or disconnecting
one invalidates its account bindings and writes an event-only append-only audit.
The existing single-owner Public key remains in a completely separate
broker_credentials table. No real Public API traffic, live trading, transfers,
tenant worker activation or automatic owner migration. All new routes 404
unless the tenant schema, identity auth and dedicated Public vault flags are
independently enabled. Two-device fake key tests check access isolation.
See TENANT_PUBLIC_VAULT_RUNBOOK.md.

## Phase 19 (v0.2.25): Shared tenant account architecture and passkey identity (inactive)

Confirmed product objective: a single EdgePilot service, separate sign-in
identity for every user, each user's own encrypted Public key, tenant-scope for
every account/history/worker/cache/recovery action, and Android passkey/biometric
login. Engineering can proceed on an assumed Public multi-user entitlement;
the assumption is not provider permission or permission to enable trading.

A dormant WebAuthn module now supports user-authenticated registration,
single-use short-lived challenges, per-user credential public-key records,
cryptographic signature/origin/ID/user verification, and session issuance only
to the isolated identity system. Existing single-owner HTTP/worker/broker paths
remain unchanged and do not import the passkey store. Native Android
Credential Manager, secure account signup/recovery, read-only Public
multi-user access, full production tenant refactor and two-device tests are
still acceptance blockers. The shared-backend design supersedes a separate
Render service per device; do not deploy a second live user on global single-
owner credentials. See TENANT_PASSKEY_SHARED_PLATFORM_RUNBOOK.md.

## Phase 18 (v0.2.24): Atomic fake work checkpoints vs stop/pause/revocation (inactive)

A disconnected offline-only work-stage recorder shares the v0.2.23
synthetic SQLite fixture and write-transaction safety controls. It records
only strict BEGIN -> CHECK -> FINISH stages, each authorized by a fake
unexpired, owner/account-scoped revisioned lease under the *same transaction*
as simulated emergency-stop state. Stop first means stage denied; stage
first means a historical completed record, not a retroactive cancellation.
Parallel fake processes cannot duplicate a stage. State and event audit
writes are atomic; no arbitrary callback or network adapter is invoked.
Read-only secret-free incident counts remain available after a stop.

The live Flask app, Observe worker, Public adapter, Android APK and
production database remain unchanged except a version/health string; all
real brokerage, trading and funds operations stay disabled. Static audit
prohibits the new gate from being imported into production. Local SQLite
is not a distributed execution fence or an in-flight broker cancellation
protocol. See TENANT_PUBLIC_OFFLINE_WORK_FENCING_RUNBOOK.md.

## Phase 17 (v0.2.23): Disconnected disk-backed multi-process safety rehearsal (inactive)

Introduced a separate synthetic-only private temp-directory SQLite safety fixture.
It demonstrates an emergency latch surviving a distinct Python process restart,
serialized per-account/global quotas across competing processes, revision-fenced
fake leases, stale/revoked-account denial, manual offline pause recovery and a
secret-free audit. Unsafe, missing or corrupt fixture state fails closed. Explicit scratch-root
validation rejects redirected TMPDIR, Render /data and nonstandard mounts;
read-only redacted incident summaries remain available after a fixture stop.
No live app, credential, provider, account, production DB, worker, trader, bank
transfer or Android APK uses this module. Static route audit prohibits live
imports. A single local disk is NOT a replicated production emergency stop;
post-check races, execution-side cancellation and global migration/ownership
gates remain blockers. See TENANT_PUBLIC_DURABLE_SAFETY_REHEARSAL_RUNBOOK.md.

## Phase 16 (v0.2.22): Offline-only consent, fake credential rotation and persisted test safety state

New synthetic modules model two-step verified session consent, encrypted
fake credential rotation across all accounts linked to one connection,
atomic per-account request budgets, account pauses and a global
emergency stop stored in a disposable memory-backed SQLite fixture.
The stop survives new controller instances on that fixture but is NOT
a production-durable control. Connection readiness checks still
explicitly deny real Public connections and trading. No live worker,
legacy route, broker credential or production data is modified. See
TENANT_PUBLIC_AUTHORIZATION_AND_SAFETY_RUNBOOK.md for details.


## Phase 15 (v0.2.21): Real HTTPS request code behind an unconditional network-disabled gate

Prepared a strictly allowlisted, certificate-verified Public HTTPS client
for personal-token exchange and account listings. The only working
request/response test path uses socket-free fake connections and encrypted
synthetic credentials on verified /dev/shm. The actual network entrypoint
unconditionally fails closed; no real Public credentials or accounts
are contacted. Added per-account test budgets, a latched failure guard,
a process-local irreversible emergency stop, and a route-audit ban on
production imports. See TENANT_PUBLIC_HTTPS_ADAPTER_RUNBOOK.md for
documented limits, provider terms, and future approval gates.


## Phase 14 (v0.2.20): Recorded read-only Public API contract and isolated account recovery

Introduced a gated synthetic-only Public token exchange and account-list
response parser modeled on official Public documentation. A test-only
credential handler decrypts encrypted fake secrets after verifying
owner/account/connection scope. Recorded failures pause only that account,
and manual synthetic review is required before another preflight.
**No real Public network requests, access-token exchange or legal ownership
verification occur.** Existing production API, worker and Public account
remain untouched. See TENANT_PUBLIC_READONLY_PREFLIGHT_RUNBOOK.md.


## Phase 13 (v0.2.19): Controlled fake Public binding, isolated recovery and legacy inventory

The verified-memory-only tests now model explicit account-to-connection
binding against a **fake local Public fixture** (not actual provider
ownership proof). A per-account recovery latch requires manual
synthetic-only review before simulated observation restarts; failures in
one account do not resume or affect another owner's account. New static
analysis inventories remaining global selected-account uses in the live
Flask/worker components; production cutover remains blocked. See
TENANT_PUBLIC_BINDING_RECOVERY_RUNBOOK.md for exact limits and safeguards.


## Phase 12 (v0.2.18): Isolated Flask tenant routes and offline account worker orchestration

A new test-gated Flask factory exercises *real HTTP request handling* for
the session-authorized tenant request contract, exclusively with verified
memory-backed synthetic databases. A synchronous, fair per-owner test
orchestrator performs only zero-quote synthetic account observations.
Neither is imported into the live API or Observe worker. Production
account cutover and trading remain prohibited. See
TENANT_ISOLATED_HTTP_ORCHESTRATOR_RUNBOOK.md for test-only limits and blockers.


## Phase 11 (v0.2.17): Inactive tenant request and worker admission contracts

`backend/engine/tenant_request_boundary.py` now models explicit,
session-authorized read and account-selection operations with canonical
account IDs and denial of unknown or executable routes.
`backend/engine/tenant_worker_boundary.py` models hard-disabled,
fair per-owner account admission and rechecks account eligibility before
RAM-only synthetic replay. Both are excluded from the live Flask API
and worker. Production multi-account cutover remains prohibited.
See TENANT_REQUEST_WORKER_BOUNDARIES_RUNBOOK.md for exact limitations.


## Phase 10 (v0.2.16): Dormant per-device account choice and monitoring isolation

The new backend/engine/tenant_api_gateway.py stores a future account
selection **per verified identity session** rather than changing the
legacy global selected account. The disabled-only
backend/engine/tenant_monitor_blueprint.py produces explicit per-account
watchlist plans and supports RAM-only zero-quote synthetic observation
replays for tests. No HTTP endpoint or live worker imports either module.
The static tenant route audit still blocks multi-account production
cutover. See TENANT_SESSION_MONITOR_RUNBOOK.md for limitations,
diagnostics, security tests and future authorization requirements.


## Phase 9 (v0.2.15): Dormant typed historical summaries and route boundary audit

The offline owner shadow rehearsal can now stage validated, account-scoped
source-only summaries of transaction, broker observation and audit events,
in addition to the v0.2.14 immutable reference ledger. All references
remain, even for invalid/unsupported records, which are counted as pending.
A new static API and worker inventory explicitly **blocks production
multi-account cutover** while the live legacy routes and worker still
depend on one globally selected account. No live changes occur.
See TENANT_HISTORY_SUMMARIES_RUNBOOK.md for audit limits, rollback
procedure and required future approval.


## Phase 8 (v0.2.14): Account-specific dormant historical references

Introduces backend/engine/tenant_history.py, used **only** in the
memory-backed disposable owner migration rehearsal. Explicitly
account-labeled legacy rows get scoped reference records under the verified
owner's inactive tenant account and are reconciled with source-row hashes.
All remaining history stays quarantined. A future-only reader proves
session/account isolation without exposing raw trade payloads. No live
migration or new user activation occurs. Review
TENANT_HISTORY_ISOLATION_RUNBOOK.md before any follow-up work.


## Phase 7 (v0.2.13): Verified memory-backed rehearsal and quarantine review (inactive)

Phase 6 now reports audited evidence-based review groups within historicalReconciliation.quarantineReview, including every quarantined row. Global watchlists/risk configurations, paper simulation, market observations, session tokens and credentials are never silently attributed or activated. Matching timestamps, SPY symbols, or a single selected account do not provide proof of record ownership.

Plaintext safety: The restored source MUST be under a genuine Linux /dev/shm tmpfs. The tool rejects disk-backed inputs, symlinks pointing off tmpfs, and missing/insufficient memory capacity; creates its working copy with TemporaryDirectory(dir="/dev/shm"); verifies every original row's content fingerprint against the staged index; and discards that directory before reporting success. No default system temp directory is used for plaintext in this shadow rehearsal. Standalone migration_preflight backup/restore utilities remain separate and must be run only with the already approved memory-backed procedure.

Detailed runbook: QUARANTINE_REVIEW_RUNBOOK.md. Live migration, new accounts, and trading activation require separate future approval.


## Phase 6 (v0.2.12): Historical reconciliation and provenance (inactive)

The owner shadow rehearsal now calls
`backend/engine/historical_reconciliation.py` to inventory each legacy
history row and create a temporary provenance index. Known explicit broker
account references must match the previously verified Public account;
blank references and unscoped automation, quotes, paper records, risk
configurations and activity are quarantined without owner attribution.
Conflicting explicit account references fail closed, and unrecognized
tables are reported for review. The source DB remains read-only and all
index rows, fingerprints and disposable tenant mappings are destroyed
after the test. Read `HISTORICAL_RECONCILIATION_RUNBOOK.md` for exact
classes, limitations and cutover gates.

**Inventory completeness does not mean migration completion.** No
unscoped paper fills, global observations or activity are assigned to
an owner without independent evidence. No production rollout, new
login, Public connection, worker or trading mode is activated.


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
