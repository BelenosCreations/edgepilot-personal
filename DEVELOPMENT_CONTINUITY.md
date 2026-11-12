## CURRENT checkpoint — v0.2.74 verified owner Public connection; backup code in development, November 12, 2026 UTC

The user independently tested the active v0.2.73 Public discovery-only
pilot at https://edgepilot-private-h9tl.onrender.com/account on Android.
Screenshot showed one "Encrypted Public connection", a discovered
"BROKERAGE" account, and a "Linked accounts" entry stating
"Public BROKERAGE · ownership verified; portfolio, monitor, orders
and transfers disabled". The old legacy Public key was NOT copied.
This is a real external acceptance beyond the prior synthetic tests,
but there is no live two-account / second device acceptance and
no portfolio or trades authorization.

The prior encrypted tenant-owner archive edgepilot-tenant-owner-
20261112.epbk was created/isolated restored and uploaded off Render
before a Public API credential and account link were added, so that
archive DOES NOT contain the now-saved encrypted Public connection.
v0.2.70 backup is explicitly limited to dormant first-owner state
(no sessions, broker features disabled). Do not weaken that tool.
Instead v0.2.74 adds a separate first-linked-owner recovery snapshot:
consistent /data tenant DB copy to tmpfs, decrypted credential
verification under existing EDGE_CREDENTIAL_KEY without revealing
secret, removes tenant_identity_sessions and tenant_auth_failures only
in a temporary snapshot to prevent session resurrection after restore,
AES-256-GCM with the private offline 32-byte phone recovery key,
private no-overwrite archive in /dev/shm, and isolated read-only
restore proof. Both live DB files remain untouched; original legacy
login and Public key remain separate.

This code MUST pass PR and merged-main GitHub CI, be merged, and
be confirmed live on the EXISTING paid Render Starter service before
the owner runs it through LOCAL Termux with the separately held backup
key. After backup succeeds, user must copy encrypted archive off
Render, verify downloaded SHA-256, and upload to their existing private
Google Drive Edgepilot backup folder. Prior backups and GPG recovery
must remain preserved. Do not treat source code deployment as a
confirmed production backup. No new paid resources, portfolio
balances/holdings, monitoring, orders, bank transfers, public
signup, invitation enrollment or second-device account are enabled.

## CURRENT operator checkpoint — v0.2.73 live private Public discovery, November 12, 2026 UTC

GitHub PR #95 for v0.2.73 was green, merged to main commit
b40874ef6ce1ee9d7282bb3b4faa54a669ae4e4e, and the
merged-main GitHub action run 43150624623 concluded SUCCESS.
The existing paid Render Starter service edgepilot-private-h9tl
then deployed this commit live. With the user's explicit approval,
we merged (DID NOT REPLACE) environment flags to activate ONLY:
EDGE_PERMANENT_READONLY_PILOT_ENABLED=true,
EDGE_TENANT_ACCOUNT_READS_ENABLED=true,
EDGE_TENANT_PUBLIC_VAULT_ENABLED=true,
EDGE_TENANT_PUBLIC_READONLY_ENABLED=true,
EDGE_TENANT_PUBLIC_DISCOVERY_ONLY=true,
plus the previously established identity/isolated tenant DB gates.
Render deploy dep-dbqjf4ec6qcc73fhamrg was confirmed LIVE.

Still disabled: EDGE_PERMANENT_TENANTS_ONLY=false, enabling
the original legacy owner token login; EDGE_AUTOMATION_WORKER_ENABLED
and ENABLE_LIVE_ORDERS remain false; signup, invites, passkeys,
monitor preview, watchlist editing, active tenant portfolio,
bank transfers and autonomous orders remain disabled.
The stable existing EDGE_CREDENTIAL_KEY was preserved, not printed,
changed or copied to chat. The original legacy Public credential
remains in /data/edgepilot.db and has NOT been migrated. The tenant
owner uses /data/edgepilot-tenants.db. Both share the same existing
1 GB paid Render persistent disk; NO new service was purchased.

CRITICAL DISTINCTION: Render reporting LIVE does NOT mean the
user has supplied a Public secret or that provider account discovery
has succeeded. User must open the secure /account page, sign in as
Belenos-Owner, generate/copy their own Public PERSONAL API secret
privately from official Public account settings, Save encrypted key,
select the new independent connection, and tap Find my Public accounts.
Only the provider token POST + account list GET are allowed by the
discovery-only pilot; even direct portfolio URLs return 404.
User should not paste keys or account identifiers into chat.
Once account linking is confirmed, prepare an updated encrypted
off-service tenant snapshot because previous backup predates the
newly stored credential. The existing Google Drive encrypted owner
identity backup and original owner credential recovery remain intact.

Next: physical Android end-to-end validation of the new scoped
Public secret storage and account-list/discovery flow. Do not enable
portfolio holdings, real order placement, transfers, workers,
new members, auto-trade or tenant-only cutover without a separately
verified development stage/authorization.

## CURRENT checkpoint — v0.2.73, approved first Public account discovery, November 12, 2026 UTC

The owner approved LIMITED identity-scoped Public API secret encryption,
provider-verified account discovery, and verified account binding on the
existing paid Render instance. The independent Belenos-Owner HTTPS login
and logout and legacy owner login were confirmed on Android; the separate
tenant owner backup is privately saved on Android and uploaded to Drive.
Current GitHub main before development was v0.2.72, all CI passed and
existing paid Render Starter deployment was live.

v0.2.73 adds a feature flag
EDGE_TENANT_PUBLIC_DISCOVERY_ONLY=true to the existing
tenant Public read-only adapter, explicitly disabling portfolio API
and frontend viewing controls. Provider access must remain limited to
POST short-lived access token and GET account list; no holdings, order,
or transfer endpoints may be called. A new synthetic two-user, two-key
integration regression checks owner isolation and no original global
Public key reuse. This development CHANGE DOES NOT ITSELF ACTIVATE
Public features. Required active flags on the existing service:
EDGE_PERMANENT_READONLY_PILOT_ENABLED=true,
EDGE_TENANT_ACCOUNT_READS_ENABLED=true,
EDGE_TENANT_PUBLIC_VAULT_ENABLED=true,
EDGE_TENANT_PUBLIC_READONLY_ENABLED=true,
EDGE_TENANT_PUBLIC_DISCOVERY_ONLY=true; retain identity, storage,
original token login and disabled background worker/trading/signup.
Stable existing EDGE_CREDENTIAL_KEY must be retained unchanged.
No actual user key has been entered by the assistant.

After PR and merged-main CI and Render deployment, merge flags into
existing Render environment (no replacement), verify new deployment
live, and ask the owner to independently input their Public API
personal secret on the real HTTPS account page to test discovery.
NEVER paste keys, passwords, account IDs or JWT in chat. The new
tenant DB will have sensitive encrypted credentials not yet included
in the earlier tenant-owner backup if the operator saves one; plan
a later recovery snapshot that includes connections, without exposing
credentials. No new paid service, member registration, portfolio
balances/holdings, independent second physical device, orders,
bank transfers or automated execution is authorized.

## CURRENT checkpoint — v0.2.72, November 12, 2026 UTC

The independent Belenos-Owner Argon2id identity was already created
and its password verified via read-only trusted SSH. An encrypted,
authenticated-restored owner tenant snapshot was copied with matching
SHA-256 to private Android storage and uploaded to the existing
Google Drive Edgepilot backup folder. Drive redownload comparison
remains unverified.

On the same paid Render service, an auth-only environment rollout
activated EDGE_IDENTITY_AUTH_ENABLED=true with isolated
/data/edgepilot-tenants.db and left the existing
/data/edgepilot.db token login available. The user supplied a
REAL PHYSICAL ANDROID SCREENSHOT showing "Secure EdgePilot account
session active" and "Welcome, Belenos-Owner" at the independent
HTTPS /account UI. In the next message, the user confirmed the
requested sign-out and original legacy login tests "Works properly".
Treat this as operator-confirmed acceptance, not as assistant-side
browser execution. The Observe/Paper worker, tenant signup, Public
vault, tenant read-only account API, passkeys, live orders and all
bank transfers remain disabled. No extra paid services were added.

v0.2.72 adds an exact-profile Flask regression under temporary
separate owner + tenant DBs to prove that independent identity
sessions cannot inherit the legacy session and vice versa,
different synthetic users cannot see each other's tenant identity,
and CSRF sign-out preserves unrelated logins. Tests also assert
new-user enrollment and broker features remain disabled.
No new runtime feature is activated by this development step.

Next: verify PR and merged-main GitHub tests plus successful Render
deployment of v0.2.72; inspect default-off user/account Public
binding flows and prepare an owner-approved *read-only* independent
broker-connection rollout without copying the original global
Public key. Real second-device/member/second Public account still
requires operator-driven acceptance; do NOT create real members,
enable broker features or retire the original login automatically.

## CURRENT operator checkpoint — Controlled HTTPS identity login enabled, November 12, 2026 UTC

The user explicitly approved enabling a limited, reversible identity-only
HTTPS login test on the same existing paid Render Starter service. The
Render environment variables were merged (NOT replaced) to retain the
original /data/edgepilot.db while selecting the separate existing
/data/edgepilot-tenants.db. EDGE_SHARED_TENANT_DB_PREPARE=true,
EDGE_TENANT_SCHEMA_PREPARE=true and EDGE_IDENTITY_AUTH_ENABLED=true.
EDGE_PERMANENT_TENANTS_ONLY=false, allowing the original legacy
token-based login to coexist. EDGE_PERMANENT_READONLY_PILOT_ENABLED,
tenant Public vault/read, tenant account reads/monitor/watchlist,
signup, invites, passkeys and signed Android passkey origin all remain
false; EDGE_AUTOMATION_WORKER_ENABLED=false and ENABLE_LIVE_ORDERS=false.
The existing paid Render service deployment dep-dbqhl6ajnfac738nlst0
of v0.2.71 main commit 9381b3f was verified LIVE. No new paid
resources or additional database were created.

IMPORTANT: Do NOT claim an end-to-end user login was verified yet.
The first login on a physical Android browser and subsequent session/
logout must be tested by the owner using Belenos-Owner and their
private Argon2id password, without revealing password to ChatGPT.
Assistant-side public web probing failed to access the URL, but Render
reported LIVE. The private owner archive was restored/verified and
copied off-Render with checked SHA-256, then visibly uploaded to Drive;
Google Drive byte-for-byte redownload verification is still pending.
See CONTROLLED_OWNER_HTTPS_LOGIN_V0271.md.

After owner confirms new HTTPS session and logout, independently confirm
original legacy login still works; if failure or unexpected access,
rollback ONLY EDGE_IDENTITY_AUTH_ENABLED=false on the existing service,
without replacing secret environment values or deleting databases.
Do not enable Public account routes, tenant-only cutover, bank transfer,
autonomous orders, signup, passkeys or restart Observe/Paper worker
without further explicit approval and acceptance evidence.

## CURRENT checkpoint — v0.2.71, November 11, 2026

The owner completed v0.2.70 production tenant backup from the existing
paid Render service with reports backup_verified=true,
isolated_restore_verified=true, first_owner_count=1,
archive_private_0600=true. The encrypted
edgepilot-tenant-owner-20261112.epbk (UTC server date) was transferred
to local Termux by protected SSH, with exact SHA-256 comparison, saved
as a private 0600 local archive, and then uploaded to the existing
private Google Drive Edgepilot backup folder. User screenshot visibly
showed the uploaded archive and upload completion. A separate Drive
redownload comparison has not yet been done.

Owner login Belenos-Owner is enrolled with Argon2id hash in
/data/edgepilot-tenants.db; the original owner token and Public
credentials remain in the original /data/edgepilot.db. Observe/Paper
worker remains paused with user approval. No independent HTTPS login,
second Android device, Public account owner verification, tenant-only
cutover, order execution or funds transfer has been activated.

v0.2.71 introduces a separately gated read-only trusted-terminal
Argon2id proof to establish that the operator remembers the new
owner password, without changing DB, creating sessions, or enabling
any public identity API. Its return explicitly reports that real
HTTPS owner login remains unverified. After GitHub PR/main CI and
existing Render deployment pass, request a one-time operator
execution. Do not activate tenant identity public routes until
that result is verified and a separate reversible login rollout
is reviewed with the operator. No new paid resources.

## CURRENT checkpoint — v0.2.70, November 11, 2026

The owner successfully completed first-owner bootstrap using the
v0.2.69 visible final approval prompt. Render printed the expected
success response, and a follow-up v0.2.65 read-only readiness
inspection confirmed inspection=passed, tenant_member_count=1,
tenant_owner_initialized=true, tenant_owner_has_password_identity=true
and next_operator_stage=manual_owner_identity_login_test.
The new private tenant identity login is Belenos-Owner and its
password was never displayed or collected in chat. Original Public
credentials and token-based login are unmigrated and intact.

v0.2.70 adds a dedicated, default-off, single-first-owner tenant
database backup because the legacy .epbk helper requires the old
settings schema and the synthetic-only tenant helper cannot touch
Render /data. This code uses a phone-held 32-byte backup key piped
over SSH, encrypts a RAM-only consistent SQLite snapshot with
AES-256-GCM, verifies an isolated private restore and publishes
a distinct non-overwriting temporary /dev/shm archive. It has NOT
yet been run on real production storage. The next operator action
after verified CI/Render deployment is to exit remote shell,
run the private backup from LOCAL Termux, compare the remote
archive SHA-256 with the downloaded local encrypted file, then
upload the archive to private Drive. The backup passphrase/key
must remain separately recoverable.

The Observe/Paper worker remains disabled as approved. No tenant
login routes, tenant-only policy, Public pilot, live orders,
bank transfers, credentials migration, second physical device
or extra paid service are activated. Preserve existing legacy
database and its validated encrypted offsite backups.

## CURRENT checkpoint — v0.2.69, November 11, 2026

The user, on an existing authorized interactive SSH terminal attached to
the *same* paid Render Starter service, successfully created
/data/edgepilot-tenants.db via the guarded v0.2.63 initializer after
manually typing the visible 34-character approval phrase. The tool
returned prepared=true, private_tenant_database=true,
initial_tenant_members=0, separate_from_legacy=true and
authorized_to_activate=false. The v0.2.62 read-only database cutover
preflight then returned inspection=passed, legacy_schema_intact=true,
separate_database_files=true and tenant_identity_schema_intact=true.
The v0.2.65 first-owner readiness audit also returned inspection=passed,
tenant_member_count=0 and next_operator_stage=manual_first_owner_bootstrap.

The initial manual owner bootstrap then requested Belenos-Owner as both
display label and login identifier, prompted twice for hidden password,
and immediately printed the generic "Owner identity was not created"
failure after a HIDDEN approval prompt. Do not infer an owner account
exists. The engine accepts Belenos-Owner; the failure could be empty
hidden input or another gate. v0.2.69 improves ONLY the operator
console interface: visible **nonsecret** approval input, specific
nonsecret denial reasons, and blank/mismatched/short-password checks
before attempting any write. Still require a fresh READ-ONLY readiness
check to verify zero members before operator retry; do not assume the
earlier attempt committed or not without verifying.

The older owner database, original token-based login, saved Public
credentials and separate GPG recovery/backups remain untouched. The
Observe/Paper background worker was disabled on Render with user
approval; live execution and transfers are disabled. Do not enable
tenant-only mode, identity routes, Public pilot features or order
submission merely because bootstrap source code deployed. Next operator
actions: verify merged-main GitHub CI and paid Render deploy for
v0.2.69, run read-only owner readiness, then (if zero) manual first
owner bootstrap, followed by repeat read-only readiness and a later
separately gated real login/recovery test. No added paid services.

## CURRENT checkpoint — v0.2.68, November 11, 2026

v0.2.67 deployed with passed PR and merged-main tests on existing
paid Render service. The owner explicitly approved a temporary pause
to the Observe/Paper worker; EDGE_AUTOMATION_WORKER_ENABLED was changed
to false through the Render connector and a live Render deployment was
confirmed. The owner verified /data/edgepilot.db permissions corrected
from 0644 to 0600 and the worker setting false via trusted SSH. The
separate /data/edgepilot-tenants.db was still absent.

The protected v0.2.63 tenant initializer was attempted twice after
the worker/permissions fix, with the exact approval phrase, but
returned its undifferentiated generic denial. A careful operator
read-only diagnostic found NO blocking runtime flags, valid private
owner DB and SQLite integrity, successful isolated schema and identity
creation on the same paid disk, valid temporary 0600 permissions,
successful fsync and hardlink; no production tenant file was created.
v0.2.68 adds fixed, nonsecret phase identifiers to THIS manual
initializer only, and tests error sanitization. It does not relax
the checks, perform initialization or change live flags.

NEXT: verify PR/main CI and Render deployment for v0.2.68, then
request the operator to execute the original protected interactive
initializer once, recording only the fixed safe stage result. Do not
enable identity, Public reads, live orders, bank transfers or a
second paid service. If the initializer succeeds, run the v0.2.62
read-only cutover preflight then v0.2.65 owner readiness before
any manual independent-owner bootstrap.

## CURRENT checkpoint — v0.2.67, November 11, 2026

v0.2.66 PR #87 passed PR CI and merged, adding a startup guard that
blocks retiring the old owner API unless a valid independently enrolled
tenant owner is present on the paid disk. v0.2.67 follows with a
default-off production account-scoped **read-only pilot permission**,
removing the previous mutually exclusive preparation flag that would
always reject tenant vault and Public read-only features on the paid
backend. The new pilot flag alone enables no tenant API. Per-feature
gates remain independent; without prepared private tenant file,
owner bootstrap, identity sessions, stable Fernet key and disabled
workers/orders, enabling the pilot is rejected.

Actual /data/edgepilot-tenants.db creation and independent first
owner bootstrap have NOT been confirmed by the operator. The legacy
database backup, owner GPG recovery and Fernet-key GPG recovery were
encrypted, verified and backed up off-phone. The existing Render
Public credential decrypts with the running key. These are distinct
from actual two-user acceptance, app/passkey validation and provider
authorization. Continue to keep production pilot, tenant-only and
tenant Public features inactive until operator-led recovery checks,
owner login and a reversible staged acceptance plan. No new cost,
live orders, automated trading or fund transfer.

## CURRENT checkpoint — v0.2.66, November 11, 2026

v0.2.65 PR #86 implemented the dormant read-only owner readiness
inspection, passed PR and merged-main CI, and deployed on paid
Render. The actual v0.2.63 protected storage initialization still
requires trusted operator input and has not been confirmed.
v0.2.66 makes the separately gated tenant-only route retirement
fail closed if no prepared private tenant DB and independently
enrolled active owner Argon2id identity exist. This is source-only
protection; normal v0.2.64/v0.2.65 owner routes remain unchanged
until environment flags are independently activated.

The operator's legacy database backup, new owner access token GPG
file, and Fernet key GPG file were verified and uploaded off-phone.
Render can decrypt the existing Public ciphertext. Neither this
nor owner existence proves login recovery or two-device test.
Next operator tasks: create tenant file, read-only schema check,
readiness audit, manual first-owner bootstrap, and actual login.
Do not enable tenant-only, live Public tenant APIs, workers/orders
or bank transfers solely due to GitHub CI. No new paid service.

## CURRENT checkpoint — v0.2.65, November 11, 2026

v0.2.64 merged with passing GitHub tests and verified live Render
deployment. The operator previously verified the original Render
owner Public credential decrypts successfully; separately encrypted,
verified, and uploaded the Fernet EDGE_CREDENTIAL_KEY recovery file to
their private Drive folder. A separate v0.2.63 protected one-time
initializer is available for the isolated paid-disk tenant DB, which
the operator last reported as NOT CREATED. No subsequent proof that
the tenant file was actually initialized has been provided.

v0.2.65 adds an opt-in read-only inspection for this exact gap:
validate separate paid-disk DB schemas, one valid owner identity or
an empty first-owner staging state, and member/identity completeness.
It will not modify storage or authenticate real users, and its output
does not approve live cutover. The tool is dormant until called
manually from trusted Render console after actual tenant DB
preparation.

After exact PR/main CI and paid Render deployment verification,
request only the missing operator evidence: actual v0.2.63 tenant
file initialization, v0.2.62 read-only cutover preflight, v0.2.65
owner readiness report, independent owner bootstrap/login and then
2 separate Android devices and Public accounts. Preserve legacy
owner login/DB and all encrypted backups; keep public tenant
activation, auto trading, orders and bank transfers disabled.

## CURRENT checkpoint — v0.2.64, November 11, 2026

v0.2.63 PR #84 passed CI, merged, and added a dormant console-only
empty tenant DB initializer for the existing paid /data disk. No
production initialization has been witnessed. v0.2.64 adds a
separate, default-off owner Fernet credential-key recovery audit:
an independently entered EDGE_CREDENTIAL_KEY can be checked against
the running service and saved owner Public ciphertext without
printing secrets or altering any database. This feature has not
actually been executed in production; evidence of an independently
held recovery key is still required.

The owner verified the November 11 encrypted database backup and
isolated restore, uploaded it to a private Drive backup folder,
and separately verified and uploaded a new encrypted owner-token
GPG file. These are not substitutes for a separately recoverable
EDGE_CREDENTIAL_KEY. Continue only after exact PR/main GitHub CI,
Render deployment, and independent operator checks. Do not infer
first-owner identity, tenant disk activation, second phone/Public
account, live orders or bank transfers from a source code merge.
No new paid infrastructure.

## CURRENT checkpoint — v0.2.63, November 11, 2026

GitHub v0.2.62 (read-only independent paid-disk cutover preflight) was
merged and passed exact-main CI and paid Render deployment. The owner
subsequently verified the Nov 11 encrypted legacy database backup with
an isolated restore on the paid service, copied it to the phone and
uploaded it to the private Google Drive backup folder. A newly encrypted
owner access-token GPG recovery file was independently decrypted,
byte-compared against the existing owner token, and uploaded to Drive.
The older failed-passphrase GPG artifact was preserved. These steps do
NOT prove stable Render EDGE_CREDENTIAL_KEY recovery, any on-disk
tenant DB activation, or the real two-device acceptance test.

v0.2.63 adds a **dormant, manual** first-time tenant file initializer.
On the existing paid /data disk it can create an empty private
edgepilot-tenants.db only after an independently verified backup,
operator console and a one-use approval; refuses an existing tenant file,
writes no owner DB rows, and publishes no live identity or Public APIs.
The code is NOT invoked by Render deployment or the Flask service.
See PRIVATE_TENANT_STORAGE_INIT_V0263.md. Verify exact PR/main CI and
paid deployment before calling v0.2.63 merged.

Next operator milestone: independently secure and verify credential
encryption key recovery; then, with explicit trusted console inputs,
run the new empty storage initializer (only if target absent) and the
v0.2.62 read-only database preflight. Independently bootstrap the first
owner (v0.2.60), verify real identity login and staged account isolation,
and ONLY THEN consider flags for eventual tenant-only routing.
Orders, transfers and live automation remain disabled. No new paid
services. Do not claim production initialization or migrations occurred.

## CURRENT checkpoint — v0.2.62, November 11, 2026

v0.2.61 (private owner invitations, at most 10 members) was developed as
PR #81 with passing PR tests and merged before this follow-on. v0.2.62
adds an explicitly opt-in, console-only, read-only production cutover
inspection for the existing paid Render Starter instance and attached
/data disk. It inspects the isolated owner and tenant databases, checks
paths/permissions/schema integrity and reports only nonsecret flags.
No database data, credentials, live trading or transfers are touched.
PR/main GitHub tests and Render deploy require independent verification.
See PERMANENT_CUTOVER_PREFLIGHT_V0262.md.

This is NOT a completed cutover. A fresh independently verified encrypted
off-service backup, tested restore and stable credential encryption key
must be confirmed before modifying the paid service environment, creating
the first real owner identity or retiring legacy owner APIs. Do not turn on
tenant Public access, passkey or order flags solely because this source
and synthetic tests pass. Separate physical-device and Public-account
acceptance remains required. No additional paid services.

## CURRENT checkpoint — v0.2.61, November 11, 2026

v0.2.58: paid existing Render service reuse and private separate tenant DB
code merged, tests green, deployed live while feature flags stayed off.
v0.2.59: future tenant-only legacy API denial and signed production
passkey-origin policy merged; gated and unchanged in live config.
v0.2.60: one-time offline first-owner role/bootstrap CLI merged after
green PR tests; no real operator bootstrap has executed.

v0.2.61 adds a separate **disabled** first-owner invitation issuance
API for a bounded private ten-user pilot. It does not trust Public or
legacy token for roles. Issuance is tied to owner-only identity and CSRF
inside SQLite BEGIN IMMEDIATE; private registration refuses a race above
ten users. Nine per 24-hour invite issuance and append-only audit. All
brokers, workers, orders and transfers remain inactive by default.
See PERMANENT_PRIVATE_INVITATIONS_V0261.md.

The NEXT real-world required milestone remains verified current
encrypted off-service legacy backup and restore rehearsal; initial
owner enrollment from a trusted Render console; deliberate shared
database flags, independent passwordless login and two-device
isolation, then provider-approved read-only brokerage checks.
No additional paid hosting/storage. Do not claim code CI alone
proves any real user or broker account migrated.

## CURRENT checkpoint — v0.2.60, November 11, 2026

v0.2.58 PR #78 merged and verified on paid Render and GitHub. v0.2.59
PR #79 merged after green PR tests; it adds **inactive** legacy API
retirement and signed-app WebAuthn-origin options for the permanent
isolated user model. The paid existing Render deployment rolled
forward, but no multiuser environment activation has taken place.

v0.2.60 supplies a **console-only, off-by-default, one-time initial
owner identity creation** for the separate paid tenant SQLite DB, with
Argon2id hashed password, atomic audit, zero existing-user requirement
and no legacy data copy. No Flask/HTTP route or alternate token was
added. All tests are synthetic. The first real account provision
remains blocked on an independently verified fresh encrypted and
restorable owner backup, an operator-trusted service terminal, and
proper split DB setup on existing paid /data. See
FIRST_PERMANENT_OWNER_BOOTSTRAP_V0260.md.

Maintain strict operational distinction: GitHub CI/Render green
does NOT prove data migration, backup, actual second physical phone,
real two-owner Public account read access or permanent identity
activation. Keep live orders, autonomous brokerage, bank transfers,
paid service creation and tenant Public features disabled. Never
reuse owner API secrets for tenant identity or print any secrets.
Proceed from last verified commit and preserve logs of tests and
deployment. Next production gate requires operator evidence, not an
assumption or automatic destructive cutover.

## CURRENT checkpoint — v0.2.59 (follows verified v0.2.58), November 11, 2026

v0.2.58 merged via PR #78 with passing PR and post-merge GitHub tests;
the same commit auto-deployed **live** on the existing paid Render Starter
service. The separate `edgepilot-tenants.db` remains configuration-gated;
default Render environment must not be described as an activated migration.
Neither legacy owner data nor keys were moved.

v0.2.59 is a distinct new development milestone. It adds a default-off
`EDGE_PERMANENT_TENANTS_ONLY` routing option that can retire legacy
owner HTTP APIs after safe migration and recovery, without allowing
identity cookies to become owner cookies. The optional production
signed-app WebAuthn origin is independently gated to the pinned real
production Android certificate, exact owned RP, tenant-only identity
and separate DB. There are new negative tests and a standalone runbook.
Default production behavior, owner APK, credentials and paid resources
are unchanged. Verify exact PR and merged-main CI before any merge.

The next operational gate remains a fresh encrypted backup/restore
checkpoint, owner identity recovery and controlled shared-disk split
preparation. Do not enable tenant-only mode until the owner can sign
into the migrated identity; do not accept legacy tokens as tenant IDs,
enable any live order/transfer, claim a second physical device, or buy
additional hosting.

## CURRENT checkpoint — v0.2.58, November 11, 2026

**New explicit architecture approval:** Use the existing paid Starter Render
service `edgepilot-private-h9tl` (service ID `srv-dbocnb3m8hqs7386trvg`)
and existing /data persistent disk as the future permanent single-instance,
multi-user backend. Do **not** upgrade the Free staging service or purchase
additional paid database/storage/hosting. The v0.2.57 additional-cost staging
plan was superseded. Keep staging disposable.

The initial `feature/v0.2.58-shared-paid-tenant-db-isolation` branch contained
only a 61-line unwired database-path selector; review identified it was not
safe to merge as finished. v0.2.58 has now added guarded shared-disk tenant
file selection, private-file creation and permissions checks, explicit
integration into every tenant Flask store, and local cross-database tests.
`/data/edgepilot.db` remains the owner file, `/data/edgepilot-tenants.db`
is the independent tenant DB. Tenant login, real Public access, migration,
live orders and transfers must remain disabled in production until separate
authorization, recovery and isolation testing.

**Release discipline:** Verify the exact branch PR CI, merge only on green,
inspect merged-main CI and paid-service Render status, and only then
proceed with recovery/activation. `main` auto-deploys to the paid service:
a source merge must not silently switch environment settings. Never print
stored tokens, passphrases, key bytes, provider secrets or encrypted rows.
Do not claim permanent two-user acceptance from the one-phone staging
passkey test. See SHARED_PAID_BACKEND_CUTOVER_V0258.md.

# EdgePilot — Development continuity checkpoint

This file is the canonical handoff for a new ChatGPT conversation when a
long development chat becomes read-only, slow, or difficult to navigate.
It complements README.md (product overview), CHANGELOG.md (release record),
VERSION (latest backend milestone), MULTIUSER_PLATFORM_ACCEPTANCE.md
(success criteria), and TENANCY_MIGRATION_PLAN.md (technical blockers).

## Approved product objective

Build **one shared, future-ready EdgePilot backend and Android application**.
Users create their own EdgePilot login, use secure passkeys/Android biometric
credential verification, and connect their own independently encrypted Public
API key. Their brokerage accounts, settings, watchlists, portfolios, history,
worker tasks, strategies, caches, sessions and backups must be isolated. The
project is currently private/noncommercial; broad commercial distribution is
not a present requirement, but should not necessitate redesign later.

The user defined the current phase as complete **only when two different
Android devices with independent users and independently owned Public
accounts actually work and isolation is verified end-to-end**. Mock/CI tests
alone do not satisfy this acceptance criterion.

## Standing authorization boundaries

- Continue routine development, corrections, pull requests, CI, merges and
  normal Render deployments without asking for each step.
- Discussion of a *new* capability is not automatically authorization to
  implement that capability. Seek confirmation for major out-of-scope work.
- Build and test the multi-user Public architecture under the engineering
  assumption that multi-user API access will be permitted. Do NOT claim
  legal approval has been verified or silently activate unrelated real
  users' credentials until separately verified as appropriate.
- Real brokerage order submission, live autonomous trading, bank deposits
  and transfers remain disabled until separately authorized.
- Never expose credentials in repository files, logs, ChatGPT messages,
  APK artifacts or screenshots. Never copy the legacy owner credential
  into another user's tenant record.
- Tenant identity endpoints and passkeys/vault/readonly are independently
  gated by environment variables and default off. No blanket enabling of
  production feature flags before readiness review and a safe migration.
- Existing personal owner app, Render backend and encrypted backups must
  remain compatible through staged migration.

## Implemented code areas and still-incomplete items

The repository includes account identity sessions, independently gated current-password
changes that revoke the member's device sessions, one-use invitation signup,
official Public signup and API-key instructions from the /account screen,
a user-owned encrypted Public credential vault, gated Public read-only
account discovery/linking and portfolio retrieval, WebAuthn passkey server
verification, a mobile-ready separate /account interface, an Android WebView
Web Authentication capability check, a fail-closed Digital Asset Links
endpoint, and synthetic monitor/worker fencing and emergency-stop tests.

The Android debug wrapper can open two exact Public-owned signup/key-help
URLs only on a deliberate user click, outside the EdgePilot authenticated
WebView. Android build 0.19.17 compiles this code but external navigation and
device passkeys still require physical-device verification.

The legacy owner app and Observe/Paper worker still use global single-owner
state, and cannot be called by tenant sessions. Account-specific monitoring
is being added in small, independently gated read-only increments, not by
silently enabling the existing global worker.

Major outstanding work includes stable Android release signing, verified
Digital Asset Links, physical biometric WebAuthn enrollment/sign-in on two
devices, forgotten-password recovery and proof of ownership, controlled
tenant activation and data migration,
strict per-account worker/strategy/history isolation, durable encrypted
backup/restore verification, incident monitoring and real two-account
read-only validation. No real orders/transfers are part of current acceptance.

## How to resume safely in a NEW chat

1. Read this file and the repository's current VERSION, README.md,
   CHANGELOG.md, MULTIUSER_PLATFORM_ACCEPTANCE.md and recent runbooks.
2. Inspect GitHub open pull requests, main's head commit and the **latest
   passing** tests for that exact head; do not rely on an older chat's
   claim that a version is complete.
3. Continue from the highest verified merged milestone. If a PR is open,
   review its current diff and CI first, fix failures, then merge safely.
4. Use a focused GitHub feature branch for each new development milestone,
   with tests, documentation and a changelog entry. Verify PR CI and
   post-merge CI. Check Android APK CI whenever Android files change.
5. Explain major completed steps in concise progress updates and provide
   the PR URL and test status. Never claim an APK, Render runtime or device
   behavior was verified without inspecting that exact evidence.
6. A ChatGPT conversation branch/new chat is a UI action by the user, not a
   GitHub branch. This file preserves continuity independently of that UI.

**Suggested first message in a new conversation:**
"Continue EdgePilot from the GitHub repository
BelenosCreations/edgepilot-personal. Read DEVELOPMENT_CONTINUITY.md, VERSION,
CHANGELOG.md, MULTIUSER_PLATFORM_ACCEPTANCE.md and the latest merged PR and
open branches. Continue approved multi-user development with periodic
updates, preserving all brokerage/trading safety restrictions."

## Current milestone checkpoint (v0.2.35)

Public key rotation and disconnection are now controlled from a member's own
/account interface. Credentials stay encrypted on the server; previously
verified account bindings are disabled and must be verified again after
rotation or disconnect. Revocation/rotation revalidates session and CSRF
within the same database transaction, preventing stale authorization after
logout. The feature remains default-off with the existing identity/vault
gate. Refer to TENANT_PUBLIC_CONNECTION_MANAGEMENT_RUNBOOK.md for acceptance
and limitations. Physical two-device biometric login and actual two-account
Public validation remain uncompleted. Always verify current GitHub VERSION,
PR status and exact-head CI before announcing release completion.


## v0.2.35.1 maintenance checkpoint

v0.2.35 merged with passing PR CI, but post-merge CI exposed an intermittent
STATE_UNAVAILABLE denial in the disconnected multi-process SQLite rehearsal.
The patch retains exactly two durable admissions and checks fail-closed
denial types. Verify v0.2.35.1 PR and post-merge CI before continuing.
No production broker or Android behavior changed.

## v0.2.37 session-management checkpoint

Verified tenant identity sessions can now be listed by the logged-in member
and other sessions can be revoked through a separately default-off,
CSRF-protected identity API. The account page displays timestamps only;
no physical-device fingerprints, IPs or biometric data are collected.
Changes are serialized with identity revocation and a secret-free immutable
audit records other-session logouts. The main app/worker, Public account
authorization, real trading and transfers are unchanged. See
TENANT_SESSION_CONTROLS_RUNBOOK.md. The two-physical-phone acceptance target
remains open.


## v0.2.38 — Stable Android signing preparation

A standalone manual-only GitHub Actions workflow now builds a private signed
Android test APK using a trusted operator-owned keystore and an independently
pinned certificate SHA-256. It cannot run automatically or on a PR, and
rejects missing or mismatched secrets/certificates. The normal debug APK
workflow is untouched. The project does NOT yet have a provisioned stable
signer, verified signed build, Android Digital Asset Links association, or
physical two-device biometric acceptance.

Next: complete isolated signing-key provisioning and website association
using an authorized owner action, then verify Credential Manager on real
devices; do not flip tenant or Public/trading flags automatically. Continue
account-specific worker/backup isolation development without broad activation.
Review ANDROID_PRIVATE_SIGNING_RUNBOOK.md and latest CI before acting.


## v0.2.39 — Test-only encrypted tenant backup/restore validation

A synthetic two-member fixture can now be snapshotted into an authenticated
Fernet archive and restored to a new private SQLite database only on verified
/dev/shm tmpfs. Archived identity sessions, pending WebAuthn challenges,
unredeemed invitations and worker leases are invalidated on restore;
all stored provider connections/accounts and passkey credentials are
quarantined pending explicit fresh verification/re-enrollment, preventing
resurrection of formerly revoked broker keys or authenticators;
cross-member account and encrypted credential isolation must remain intact.
Production Render DB paths and non-tmpfs destinations are explicitly rejected.
This is NOT production offsite backup or key-management readiness. No live
brokerage request, transfer or trading was enabled. Review
TENANT_BACKUP_REHEARSAL_RUNBOOK.md and latest CI for the exact commit.


## v0.2.40 — Shared-backend two-user HTTP acceptance rehearsal

Synthetic end-to-end tests now simulate Alice and Bob on independent Flask
cookie jars against the SAME backend with separately gated identity,
invitation signup, WebAuthn option preparation, encrypted fake Public keys,
read-only fake broker accounts/portfolios, per-account watchlists and
inactive monitoring previews, and selective other-device session logout.
No real HTTP brokerage requests, Android biometric assertions, live workers,
orders or transfers occur. Passing tests are NOT proof of two real phones,
real provider permission, authenticated production Public accounts or
production-grade recovery. See TWO_DEVICE_SYNTHETIC_ACCEPTANCE_RUNBOOK.md
before declaring this stage complete.


## November 10, 2026 — First owner-controlled stable signed APK verified

The operator created a 4096-bit RSA JKS signing identity in private Termux
storage, verified the signing certificate, GPG AES-256-encrypted a backup,
successfully checked decryption against the original, and stored the sealed
backup in their own Google Drive. Five required GitHub Actions signing
secrets were configured privately, and the signing password was verified
against the unchanged keystore before both password secrets were updated.

Manual signing workflow #42888113943 ran on main at
45ecaf82d0f1c3d648c2e6ab0a17d18817823e73. Attempt 1 failed the
certificate-pin check and produced NO artifact. The expected public
certificate fingerprint was recalculated from the actual JKS and corrected.
Attempt 2 PASSED compile, apksigner signature + fingerprint checks and
private artifact upload. Artifact:
EdgePilot-v0.19.17-private-stable-signed-test
(expires 2026-11-17; no binary in the source repository).

This satisfies the signed-artifact CI precondition but NOT Android
installation, authenticated Digital Asset Links, passkey/biometric
enrollment or sign-in, verified two-physical-device tenant isolation,
provider-permitted real accounts, production database recovery or active
tenant monitor workers. The existing debug-signed APK may not update in
place to the stable signature; DO NOT advise uninstalling without
checking local session/recovery state. Continue from the real-device
signer/Digital Asset Links verification stage. No production trading
or transfers have been enabled.

See ANDROID_PRIVATE_SIGNING_RUNBOOK.md and APK_TESTING.md for the exact
GitHub run and safe installation limitations.

## November 10, 2026 — Owner-reported physical Android installation and legacy login

The owner installed the previously verified permanent-certificate Android
v0.19.17 test APK on their *existing* phone after locating the legacy
EDGE_APP_TOKEN on Render and confirming that the original token still
worked in Chrome separately. The user subsequently reported a successful
login in the installed app. No token, passphrase, backup ciphertext or
other credential should appear in README, CHANGELOG or GitHub issues.
No key rotation was required.

Important: do not conflate this one-phone **owner-reported legacy dashboard**
smoke test with proof of app-to-website Digital Asset Links, Android
Credential Manager passkey registration/authentication, or the approved
two-distinct-devices/two-independent-EdgePilot-users target. The default-off
identity/passkey/Public-tenant feature gates remain unchanged. The next
technical work is website association validation and safe isolated-test
passkey verification; real orders, transfers and production multiuser
cutover remain disabled.

## November 10, 2026 — Android Digital Asset Links Render configuration staged

The owner opened the website's /.well-known/assetlinks.json on their
current phone and captured a JSON 404 from EdgePilot. This was the
expected fail-closed response while EDGE_ANDROID_CERT_SHA256 was absent
or invalid. A copy of the independently CI-verified signed APK
(GitHub run #42888113943, attempt 2) was read and its Android v2/v3
signature blocks independently parsed; both contain the same X.509
certificate and SHA-256 fingerprint. The public certificate fingerprint,
not a signing secret, was merged into the existing Render service's
EDGE_ANDROID_CERT_SHA256 variable. Render deployment
`dep-dbppig56e07s73b34d1g` was verified status=live.

This is the server configuration milestone only. At this checkpoint a
subsequent external fetch of the public HTTPS JSON response had NOT
been independently confirmed. The owner should reopen the same URL
and confirm it now returns a JSON array containing the correct Android
package and certificate. An installed app's Android Credential Manager
association and tenant biometric authentication remain completely
unverified. Do not turn on dormant multiuser/tenant/passkey/Public flags
or enable orders or transfers as an implied consequence of this deploy.

## November 10, 2026 — Public Digital Asset Links JSON confirmed on Android

After Render deployment `dep-dbppig56e07s73b34d1g` was live, the owner
reloaded https://edgepilot.belenoscreations.biz/.well-known/assetlinks.json
on their current Android phone. The supplied screenshot displayed a
JSON array containing relation
`delegate_permission/common.get_login_creds`, target namespace
`android_app`, package `com.edgepilot.mobile`, and the configured
SHA-256 certificate fingerprint matching the verified permanent-signed APK.
This resolves the prior 404 and validates **public HTTPS association
response content** from the owner's phone. It is not OS-level Digital
Asset Links verification and does not demonstrate credential sharing,
Android Credential Manager availability, or a functioning passkey.

Next: determine a controlled isolated test deployment and user enrollment
method before turning on currently default-off identity, signup, or
passkey flags. Do not activate those on the personal live service simply
because the public association file is available. Test account recovery,
passkey registration and login on an actual Android device, then use a
second independent user/device. Live orders/transfers stay disabled.

## v0.2.41 — Fully offline, real-crypto two-user WebAuthn verification

A new test-only software-authenticator harness generates actual ES256
P-256 signing keys and CBOR WebAuthn attestation/assertion data and exercises
the production py_webauthn verification routines behind the Flask tenant
identity routes without mocks. Two separate synthetic users enroll and log
in on separate in-process browser cookie jars. The test verifies exact RP
origin, signed challenges, required UV, distinct identity-only sessions,
no legacy account inheritance, and fail-closed behavior for wrong origin,
missing UV, forged signatures, foreign handles, reused challenges, counter
rollback and credential revocation. External requests are denied during
the fixture; no Public credential, real account, trade or transfer is used.

This validates actual *cryptographic protocol processing*, not Android
Credential Manager, OS-level Digital Asset Links, physical biometrics,
real website session operation or two independent physical phones.
The existing owner APK and Render feature flags remain unchanged; do not
misrepresent synthetic credentials as a real user's passkey. Follow
WEBAUTHN_REAL_CRYPTO_ACCEPTANCE_RUNBOOK.md for scope and next steps.

## v0.2.42 — Separate Android staging package and guarded website association

After the owner reported a successful login in the permanently signed
production-host Android app, development added a distinct Android staging
build type with package com.edgepilot.mobile.staging and app label
EdgePilot Staging. Production app ID, stable-signed workflow, HTTPS host,
installed app and login credentials remain unchanged. Staging host is a
compile-time, owner-controlled distinct belenoscreations.biz subdomain;
missing configuration compiles only a nonfunctional .invalid host.
A new manual-only workflow can sign the staging package with the same
operator-owned certificate after a separate staging HTTPS service exists.
PR Android CI compiles the unsigned staging build without exposing a
signed staging artifact. A process-startup staging guard refuses unsafe configuration **before**
opening the database or initializing legacy owner credentials, while the
optional backend staging association responds only when explicitly
isolated with exact RP/host and all live credentials, workers, orders
and provider paths absent.

No separate paid Render service or DNS has been provisioned in this
milestone; neither staging signed build, physical Android biometrics nor
two-user/two-device acceptance has been validated. Do not overwrite the
owner's existing APK. Review ANDROID_ISOLATED_STAGING_RUNBOOK.md and
request operator input for new hosting/domain provisioning and costs
before actual staging rollout. Never enable real brokerage trading or
transfers as part of this test.

## v0.2.43 — Approved research strategy and no-cost data boundary

Read AI_ANALYSIS_COST_STRATEGY.md (approved 2026-11-10). It extends
rather than supersedes the two-device, two-independent-Public-account
acceptance objective. The standalone research_intelligence.py module
requires verified coverage, source rights, UTC timestamps, fresh books
and explicit fees/depth/settlement for prediction event research.
No market provider, background polling, brokerage account, user identity
or LLM call is made by the new pure-Python functions. A user who elects
$0 in AI fees must retain a useful non-AI intelligence product when
permitted data exists. No free market-data license is assumed.

Next: precise model-aware AI budget accounting and reservation
reconciliation, default-off tenant BYOK and per-user caps, followed by
consent/licensing-conscious shared signals and deferred commercial
entitlements. Do NOT enable trades, transfers, public distribution or
actual billing. Physical Android passkeys and independent Public accounts
still need real-device acceptance. See FREE_FIRST_RESEARCH_RUNBOOK.md.

## v0.2.44 — Owner AI pricing and local budget accounting

Legacy ai_analysis.py now uses public Standard short-context text
price snapshots (checked 2026-11-10) for the allowlisted
gpt-6-luna and gpt-6-sol models, conservative byte-bound input
cost and 500-token output ceiling, microUSD integer ledger
with SQLite BEGIN IMMEDIATE reservations. Successful replies need
provider input/output token counts to finalize usage-cost estimates;
unknown charges/timeouts/HTTP errors retain their reservation.
Historic $0.20 rows are preserved, including original budget
consumption. This adds no automated AI calls. The current optional
owner AI setting remains disabled by default; the $2 default budget
is unchanged; the local limit is not guaranteed third-party billing.
Pricing expires review 2026-12-10 and fails closed on expired rates.

Read AI_COST_ACCOUNTING_RUNBOOK.md before any model/cost work.
Next: independently owner-funded vs per-user BYOK/allowance encrypted
credentials and tenant budgets; never silently use the owner's
OpenAI credential for other EdgePilot members. Two physical devices,
independent Public accounts and Android passkeys remain open.

## v0.2.45 — Dormant member-owned AI funding/vault groundwork

The owner-approved up-to-ten-friends AI strategy now includes a fully
offline encrypted per-member BYOK preference/budget module. All authority
derives from independent server-side tenant session and CSRF,
revalidated inside the SQLite BEGIN IMMEDIATE transaction. Each member's
mode, analysis depth, own provider key and monthly microUSD cap are
separate. The module does not import or fall back to legacy owner
OPENAI_API_KEY or EDGE_APP_TOKEN. It stores encrypted owner-bound provider
key material under a separate AI encryption key, returns only a configured
boolean, and enforces a fail-closed per-member cost reserve for simulated
requests; no payment, OpenAI HTTP call or schedule is activated.
Managed-credit mode is deliberately refused. Ten-member concurrency
and owner isolation tests reside in test_tenant_ai_byok_v0245.py.

No Flask routes or production flags have been added to expose this store
to real users. Future secure key management, rotation and recovery,
ten-user load, provider billing opt-in, real hardware passkeys and
real independent Public accounts remain outstanding.
See TENANT_AI_BYOK_BUDGET_RUNBOOK.md.


## v0.2.46 — Licensed shared, account-neutral research sample cache

A separate dormant module now validates strictly public provider-neutral
observations, requires affirmative verified analysis/cache/redistribution
rights, rejects personal keys/holdings/account identifiers, records only a
short-lived spread feature, and fences all stock/ETF watchlist previews by
independent identity, CSRF, account linkage and watchlist owner in one
SQLite transaction. Ten independent synthetic users reuse one feature with
zero AI/provider calls. Crypto/prediction account entitlement is NOT
implied, and no provider terms have been accepted by this code.
No real shared market data, external provider requests, HTTP UI, worker,
orders, bank transfers or production gates activated. Follow
SHARED_RESEARCH_CACHE_RUNBOOK.md and the main AI_ANALYSIS_COST_STRATEGY.md.
Before continuing verify PR/CI and resume from highest verified main commit.
The two-physical-device/two-independent-Public-account acceptance goal
and physical biometric checks remain open.


## v0.2.47 — Offline, provider-quota-aware sampling proposal

Another independent, dormant research module proposes source-aware
market sampling under explicit, recently verified quotas, coverage and
license/redistribution permissions. It never schedules or makes a real
request. Ten synthetic members can share one *proposed* licensed central
data call or receive separate individually authorized, fair,
per-member-quota-limited proposals. Stale data, closed/unknown sessions,
prediction-expiry uncertainty, current backoffs and missing
entitlements fail closed. All member identifiers remain internal.
README, CHANGELOG and ADAPTIVE_RESEARCH_PLANNER_RUNBOOK.md updated.

No market data contract, physical multi-device activation, tenant
worker, crypto/prediction broker integration, AI payment, or live
trade is permitted by the synthetic planner. The main project success
gate is still two physical Android devices, independent EdgePilot
identities and independently verified Public accounts.


## v0.2.48 — Matched forward-quality audit without AI execution

The approved AI value/cost strategy now includes an independent offline
paired Brier-score audit for pre-settlement binary forecasts, externally
verified realized outcomes, chronological held-out calibration evidence,
unique matched event provenance, and attributable measured microUSD AI
costs. Claims of causal AI uplift, profits, after-cost alpha or trading
eligibility always remain false; all real outcomes are still unverified.
Negative tests reject private fields, timestamp leakage, unconfirmed
costs, mixed event meanings and repeated IDs. See
PAIRED_RESEARCH_AUDIT_RUNBOOK.md. README, changelog and VERSION
updated. No new provider HTTP, order, money flow, subscription,
production tenant flag or worker was activated. Physical Android
passkeys and independent two-device/two-Public-account acceptance
remain incomplete.


## v0.2.49 — Requested tier is not a commercial entitlement

New standalone dormant tenant_tier_intent module stores authenticated
member-specific requested Free/Plus/Pro/Custom concepts but never
grants a paid plan, overrides data rights, funds AI from the owner,
changes a Public account or enables trading. Ten synthetic members'
preferences, CSRF, disabled/revoked session enforcement and hard paid
grant refusal have negative tests. Real subscriptions/payment providers
and any Play distribution have NOT been approved or activated; see
TENANT_TIER_INTENT_RUNBOOK.md. README/CHANGELOG/VERSION updated.
Physical two-device independent Public accounts remain outstanding.


## v0.2.50 — Fail-closed tenant AI measured overage ledger

If simulated measured token cost exceeds a BYOK member's preflight
hold, settlement now records the higher cost with uncertain status,
and future budget admission counts max(held, actual). Unknown cost
still keeps a full hold. The ledger refuses double settlement and
cross-tenant manipulation, retains prior usage after key disconnect,
and never guarantees provider-side billing limits. Tests in
test_tenant_ai_budget_overage_v0250.py, runbook
TENANT_AI_OVERAGE_RECONCILIATION_RUNBOOK.md. No actual paid model
requests, provider keys, bank action, real orders, subscription
or production activation. Independent two-device Public-account
acceptance and actual physical passkeys remain open.


## v0.2.51 — Approved staging preparation, not a deployment

The user approved preparing a separate EdgePilot staging service in
Belenos's Render workspace, with explicit approval before incurring
additional charges. Current production Render service
edgepilot-private-h9tl is untouched, including its /data disk and
owner Android package. The proposal in
deploy/staging/render-service.proposal.json is intentionally
non-deployable: its signing certificate is an unverified placeholder,
host staging-edgepilot.belenoscreations.biz is only a candidate,
auto-deploy is off, plan is Free and only ephemeral /tmp SQLite is
allowed. backend/engine/staging_release_readiness.py performs a
strict static audit of the proposed settings and the existing server
staging-isolation guard; negative tests prevent copied production
secrets, trading/broker flags, unsafe host/DB/package and unapproved
paid plan changes. README, changelog and
STAGING_RENDER_COST_APPROVAL_RUNBOOK.md updated.

Do NOT create Render services yet without reviewing shared
workspace bandwidth/build-minute usage and potential overages,
confirming approval of extra cost, actual DNS/TLS and genuine public
signed-APK certificate. No new service, DNS or signed staging app
was created. Physical biometric/two-device independent Public
account acceptance remains incomplete. Resume from latest verified
merge/CI, not conversation claims.


## v0.2.52 — Separate Free staging instance created, not yet hardware-ready

With explicit user approval following a Render Billing screenshot,
created `edgepilot-passkey-staging` (`srv-dbpupj2jnfac73ehv1v0`)
under the confirmed workspace, `plan=free`, auto-deploy off, no disk,
Ohio, Docker context `backend`, Dockerfile `backend/Dockerfile`,
main commit `2a53250924c90d350a58ad84f966e08e521b9185`.
Initial deploy `dep-dbpupjajnfac73ehv2og` reported `live`;
Render logs show Gunicorn running and build/deploy events succeeded.
Original owner service `edgepilot-private-h9tl` is unchanged.

Independently extracted **public** SHA-256 signer certificate from the
archived signed v0.19.17 GitHub APK, correcting an old configuration
typo in the preliminary fingerprint: the correct value contains
`...4A:F5:6E:A7...`, not `...4A:F5:6F:A7...`. The current staging
Render environment uses the correct verified signer for
`com.edgepilot.mobile.staging`. The private signing keystore or
password was never accessed, copied or committed. Runtime has its
own /tmp DB, no Public/owner credentials, no trading/broker workers.

**Blockers to finish this stage:** Owner must add the distinct custom
hostname to this staging service in Render, and a separate CNAME
`staging-edgepilot` -> `edgepilot-passkey-staging.onrender.com`
in Squarespace; verify TLS and staging-only Digital Asset Links.
No Render connector action for custom domain or Squarespace DNS
was available. Do not change production DNS. Free instances have no
shell/one-off jobs, so trusted staging-only invitation provisioning
must be designed before the two independent real-device ceremonies.
Then run manual staging-signed Android workflow, verify package/
cert/host, two physical devices and eventually independently allowed
read-only Public accounts on durable storage under separate approval.
No new paid plan, disk, live brokerage or bank transfers approved.
For precise evidence and steps read STAGING_RENDER_LIVE_CHECKPOINT.md.


## v0.2.53 — Disposable operator invite bootstrap prepared

After the owner reported the new staging custom domain **Verified**,
prepared staging-only home redirect to /account, a distinct
/staging-operator page and POST /api/staging/invitations. This
test-only path requires a 256-bit token, only its SHA-256 hash in
EDGE_STAGING_OPERATOR_SHA256, exact configured staging origin and
host, atomic quota of two one-use invites, attempt throttling.
Production / remains the owner dashboard; the operator path
cannot work outside EDGE_ISOLATED_STAGING. No change to the
actual signed production APK or brokerage configuration.

The user reported Render domain verified; HTTP response and Android
OS association are **not independently confirmed** by that statement
alone. No staging signed APK or physical passkey validation yet.
Follow STAGING_OPERATOR_INVITATIONS_RUNBOOK.md to activate the
digest in staging only, deploy the verified GitHub commit
manually because staging auto-deploy is off, and have the user
run the manual signed Android workflow on main with the
exact staging host. Do not claim a GitHub/Render action succeeded
unless the corresponding logs or resulting artifact prove it.
Any Render Free instance spin-down can erase ephemeral invites,
accounts and passkeys; only synthetic trial data allowed.


## v0.2.54 — GitHub signed Android staging run failed safely (phone trailing space)

The owner reported "APK built", but inspection of the actual GitHub
workflow showed run #43011557930 on `main`, event
`workflow_dispatch`, **completed/failure**. The failing step was
"Verify distinct owned staging hostname"; later compile, signing
and artifact steps were skipped. The log showed
`EDGE_STAGING_HOST: staging-edgepilot.belenoscreations.biz `
with one trailing space. Do not claim a signed staging APK exists
from that run.

Fix the manual-only GitHub workflow to normalize *surrounding*
whitespace once, validate the pinned hostname/production exclusion,
write the checked value to GITHUB_ENV, and build with the checked
value rather than the raw workflow form input. Regression tests
execute the real Bash block with trailing spaces, CRLF, malicious
injection, external hosts and production host. No signing key,
provider credential or Render environment change.
After verified PR and main CI, the owner must launch a **fresh**
staging signed workflow on new main; don't rerun the previous
SHA. Only then verify a successful artifact and actual signed APK
package/cert/embedded host before installing alongside the
unchanged production app.


## November 11, 2026 — v0.2.54 signed staging APK verified

The owner dispatched a **new** staging GitHub Actions workflow on
updated main commit `1a3c6a2ba0bfe3390ed8c23d4a9a416d8457fe58`.
Workflow run `43013142566` **completed/success**, including the
strict normalized owned-host check, Android staging assemble,
`apksigner` signing verification and private uploaded artifact
`EdgePilot-v0.19.17-isolated-staging-signed-test`
(artifact ID `13850459385`). The APK was downloaded and independently
inspected. It is `com.edgepilot.mobile.staging`,
`0.19.17-staging`, embeds
`https://staging-edgepilot.belenoscreations.biz/`, and its
v2 signing certificate SHA-256 is
`B1:D5:C5:60:11:10:D4:B3:BF:5A:22:D4:4A:F5:6E:A7:BA:8C:24:F0:46:FA:DB:27:95:2A:EA:18:E7:EC:D3:3F`
matching the verified staging Render association setting. Full APK
SHA-256: `5f1b64ad8c584afb93c72f6c9450567c5dc4a3f853b4aa5651cf47cb05de471a`.
The user received a directly installable APK copy in ChatGPT.

**Open:** On the first Android phone install the second app
**EdgePilot Staging** without removing the owner's production
EdgePilot. Verify staging account login UI and actual custom-domain
HTTPS/Digital Asset Links. Next issue two disposable 60-minute invites
using the separate saved staging operator key, then test both phones'
Android Credential Manager passkeys and session isolation. Free staging
DB remains ephemeral; no live brokerage keys or real trades. Real
Public accounts require durable storage and provider approval.
The earlier workflow run #43011557930 failed before APK compilation
from a trailing hostname space; it is not the successful run.


## v0.2.55 — First physical Android test revealed likely WebAuthn native-origin mismatch

User installed signed `com.edgepilot.mobile.staging` on the real Android
phone, created and signed into the synthetic `Test 1` account,
and tapped "Add biometric passkey". The screen displayed
"Passkey verification failed". **Password/session UI worked**; the
failure was at passkey verification. Do not claim passkeys work.

Code inspection established that `TenantPasskeyStore` used
`expected_origin=self.origin` (the HTTPS website) for both
registration and authentication, while Android Credential Manager
may return `android:apk-key-hash:<base64url(SHA256 app signer)>`.
Google's official passkey guide documents the Android origin.
Prepare a narrowly scoped origin allowlist in v0.2.55 using the
already independently verified **public** staging APK signing
certificate fingerprint. In production, or without strict staging
startup validation, keep only HTTPS. Test with real cryptographic
software WebAuthn fixtures for both origins and reject wrong
native fingerprint, altered challenge and spoofed browser origin.
Do not log clientData/credential material and never accept a
client-selected origin.

**Critical deployment warning:** Render Free staging uses
`/tmp/edgepilot-staging.db`. Any redeploy/spin down can erase Test 1,
passkeys and used invitations. Preserve the owner's original production
service and APK. Recreate Test 1 with newly minted synthetic invitation
only if required; do not use real Public brokerage credentials.
The owner must retest native biometric register/sign-in after the
verified staging fix is deployed. Prior test screenshot confirms
account sign-in only, not successful passkey registration.


## v0.2.56 — User-approved real-time passkey state and self-management

After the owner registered a signed Android staging passkey for
synthetic Test 1 and another for Test 2, screenshots showed the
outdated "Add biometric passkey" button even after successful
enrollment. User explicitly approved updating that UX.

The authenticated account view now loads
`GET /api/identity/passkeys` to get **only its current member's**
active credential IDs, creation timestamps, device type and backup
flags (no device name, biometric data or public/private keys). The
legacy activePasskeys count remains stable; additionally responds
with passkeys array and explicit broker/trading/biometric/identifier
false flags. Client verifies response shape and count, displays
"Set up biometric login" only at zero, otherwise a checkmarked
passkey-enabled state and count. A new Account Security section
lists registered passkeys and adds "Add another passkey" plus
user-confirmed removal. On success, the UI refreshes status; removing
a credential revokes all current member identity sessions and logs
the current UI out, without affecting a second user's sessions.
The UI explains that external credential-manager copies may need
manual deletion. The old APK need not change.

No real Public API credential, order, financial transfer, or live
worker permission was changed. The Render Free staging SQLite is
`/tmp/edgepilot-staging.db`: **backend redeployment can delete
Test 1/Test 2 identities and passkeys**. Confirm account state
after new staging deploy; recreate only synthetic accounts if
necessary. The user's two screenshots demonstrate account
registration and passkey enrollment, but do not by themselves
prove independent physical phones or both passkey sign-ins.
Maintain this distinction in later acceptance claims.


## v0.2.57 — User confirmed Test1 passwordless passkey sign-in; durable staging decision required

In response to a requested sign-out / Use passkey / return to
"Welcome, Test1" test, the owner reported **"Works"**. This supports
one physical Android staging-device synthetic Test1 passkey
authentication roundtrip with previously observed UI transitions
from not configured to "✓ Passkey login enabled — 1 passkey registered".
Do not infer that the separate Test2 image was on another physical
Android device, that it signed in with a passkey after its registration,
or that either member's data survives backend redeploy/restart.

The isolated staging service remains Render Free with a disposable
`/tmp/edgepilot-staging.db`; a deploy demonstrably erased the earlier
test users. Preparing persistent storage is the next blocker.
Current published Render pricing: paid starter web service
approximately $7/month and 1GB disk $0.25/month, for **~$7.25/month
additional base charges**, beyond existing owner production
service and before overages. Free Render Postgres expires after
30 days and cannot be presented as permanent recovery.

The owner must **explicitly authorize incremental recurring costs**
before any paid plan change, disk or database creation. The
`STAGING_PERSISTENCE_DECISION_V0257.md` runbook specifies exact
isolated staging-only `/data` mount and
`EDGE_DB_PATH=/data/edgepilot-staging.db`, no owner credential
reuse, controlled testing across actual Render redeploy and
restart, backup safety and rollback. No deployment, new bill or
change to real brokerage/trading privileges is authorized by this
documentation milestone.
