# v0.2.60 — First permanent EdgePilot owner identity (OFFLINE, unactivated)

## Why the next gate exists

The existing paid Render Starter service and 1 GB disk will become the
permanent single-instance EdgePilot backend. The current owner's original
credentials and records in `/data/edgepilot.db` must **not** be silently
adopted as another user's account or destroyed. The newly prepared
`/data/edgepilot-tenants.db` holds independently authenticated members.
A first-owner identity is needed before considering the tenant-only
routing switch from v0.2.59. This release adds a private operator-console
one-time bootstrap, **not an HTTP self-registration, password reset,
Public brokerage connection or production migration**.

## Strict prerequisites before any real operator runs it

1. Independently verify a *fresh, encrypted, off-service* backup and
   **tested restore** of the original production owner database and
   custody of the stable Public Fernet key and owner app login token.
   The November 9 backup history alone does not prove today's DB
   content is recoverable. Do not display or export secrets in chat.
2. Confirm the existing paid Render service is still
   `edgepilot-private-h9tl`, with the existing disk mounted at `/data`
   and one application instance. Do not provision a new paid resource.
3. Verify the v0.2.58/59 code has passed PR and merged-main CI and
   deployed healthy. Pause the legacy global Observe/Paper worker
   safely and preserve its state. Ensure `ENABLE_LIVE_ORDERS=false`.
4. Prepare the split DB schema on **the existing paid service only**:
   `EDGE_DB_PATH=/data/edgepilot.db`,
   `EDGE_SHARED_TENANT_DB_PREPARE=true`,
   `EDGE_TENANT_SCHEMA_PREPARE=true`,
   `EDGE_TENANT_DB_PATH=/data/edgepilot-tenants.db`,
   `EDGE_IDENTITY_AUTH_ENABLED=true`,
   and `EDGE_AUTOMATION_WORKER_ENABLED=false`.
   Keep `EDGE_PERMANENT_TENANTS_ONLY=false`, tenant Public
   credential/read/account gates false, and live/bank permissions off.
   A private, pre-existing tenant file and its schema are required.
5. The operator must have a trusted **interactive terminal on the
   existing service**, not a public endpoint or APK secret input.
   Run in the existing backend working directory with a temporary
   one-command environment flag:
   `EDGE_OWNER_BOOTSTRAP_ALLOWED=true python tools/first_owner_bootstrap.py`.
   Do not put passwords, approval phrases or keys in command arguments.
6. Enter a unique login identifier, display label and new 14–128
   character password twice through interactive prompts. The approval
   phrase is prompted without shell history. The tool creates **only
   one** owner-role tenant identity atomically. It never reads plaintext
   Public secrets or copies owner settings, brokerage records or sessions.
   Once any tenant user exists it refuses permanently; no second owner
   is implicitly created.
7. Validate the owner can log into `/account` using the isolated
   tenant identity, test session revocation and passkey registration
   under deliberate separate feature gates, then confirm original
   owner access remains recoverable. The owner is not brokerage-linked
   until a separately approved migration/verification process.
8. Do not enable tenant-only legacy API retirement until the
   owner login, recovery, passkeys, two-user isolation, and historical
   account migration/quarantine have been verified. Keep production
   brokerage and funds transfers disabled.

## Source-code safety boundaries

The console tool is in `backend/tools/first_owner_bootstrap.py`;
the atomic transaction lives in
`backend/engine/permanent_owner_bootstrap.py`.
No Flask import, route, scheduling, or persistent bootstrap secret is
added. The code refuses missing operator opt-in or approval, unsafe
paths, staging, missing schema, loose file permissions, running global
workers, live orders, enabled Public tenant features, enabled invitation
signup, existing members or duplicate login. The plaintext password is
not printed, returned, logged, or put on GitHub. Argon2id is used for
the account's password hash. Concurrent calls serialize in SQLite.

Automated tests use synthetic temporary databases and no Render shell,
real credentials, third-party API, trades, transfers or paid service.
This feature is **not** activated by merging the branch. The current
ChatGPT connectors cannot read the actual Render SQLite contents, verify
a fresh backup or run the trusted interactive Render shell, so the real
production step requires separate operator action and evidence.
