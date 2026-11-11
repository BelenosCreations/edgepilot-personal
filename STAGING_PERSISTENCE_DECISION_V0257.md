# EdgePilot v0.2.57 — Real-device passkey evidence and persistent staging decision

**Status:** Documentation-only checkpoint. Do not change deployment,
storage, subscriptions, credentials or trading flags without the owner's
separate and explicit approval of recurring costs and the migration steps.

## Verified on physical Android, November 11, 2026

The user completed the v0.2.56 `EdgePilot Staging` UI exercise
after redeploying the isolated Free Render service:

- Synthetic member `Test1` registered/signed in.
- Before setup, the welcome card accurately displayed
  **"Passkey login is not set up for this EdgePilot account"** and
  **"Set up biometric login"**.
- After using that button, the device showed
  **"Your passkey was registered"** and the same welcome card changed
  to **"✓ Passkey login enabled — 1 passkey registered"**;
  the initial setup button disappeared.
- The user then reported **"Works"** after being asked to sign out,
  select **Use passkey**, and confirm re-entry as `Test1` without
  a password. This is a user-reported successful physical-device
  passkey sign-in, not an independently captured Android OS trace.
- Earlier screenshots also showed synthetic `Test 2` passkey
  registration. They do **not** yet establish that two distinct
  physical Android devices signed in independently at the same time.
  Neither user has connected a real Public brokerage account.
- Actual synthetic test accounts disappeared on an earlier Free Render
  redeploy; this was observed and the test user was re-created.
  This is not an unexpected application behavior on an ephemeral DB,
  but is unsuitable for continued account-level tests.

**Acceptance:** One signed Android staging app, one synthetic member,
credential registration, dynamic passkey state and user-reported
passwordless sign-in. **Not yet accepted:** surviving restart/redeploy,
two physical phones/independent sessions, recovery and backups,
real Public credentials, brokerage isolation, account data persistence,
trade execution or commercial deployment.

## Existing architecture and isolation

The current service `edgepilot-passkey-staging` is Render Free,
with manually controlled deployment, no disk and
`EDGE_DB_PATH=/tmp/edgepilot-staging.db` (ephemeral SQLite).
Its DNS and WebAuthn RP are pinned to
`staging-edgepilot.belenoscreations.biz` and the separate
`com.edgepilot.mobile.staging` signed Android package.
The existing personal production service
`edgepilot-private-h9tl` and its persistent disk **must not be
reused or shared** with staging: that would mix owner and other
members' data and compromise isolation.

The backend already supports choosing its SQLite DB location via
`EDGE_DB_PATH`. Keeping the same database format minimizes code
changes for a private synthetic staging pilot. Longer-term shared
hosting with multiple worker instances and tenant-specific real
brokerage integrations requires a dedicated migration to a managed
transactional database, encryption-key management, backups and
restore drills. A SQLite disk is not a complete multi-tenant
production architecture.

## Persistence options and charges — owner decision required

| Option | Cost basis at November 11, 2026 | Durability | Engineering and fit |
| --- | --- | --- | --- |
| **A. Upgrade only staging to Render paid web compute + separate 1 GB disk** | Render lowest paid web plan **$7/month** plus persistent disk **$0.25/GB/month**, approximately **$7.25/month additional** before taxes, overages and any future upgrades | Disk-backed SQLite survives staging redeploy/restart, assuming correct mount path | **Recommended next private testing step.** Keeps current SQLite routes; no additional hosting account; single staging instance; backups/restore still need work |
| B. Free Render Postgres plus code migration | Free PostgreSQL expires **30 days** after creation and later can be deleted unless upgraded | Not durable long-term | **Not recommended** for solving the owner's recurring lost-account issue; migration adds nontrivial code and testing |
| C. Paid managed Postgres and application migration | Separate recurring compute/storage charges; request a current quote before provisioning | Durable database service with managed backup options | More scalable longer-term multi-user architecture, but out of scope of the present synthetic UI trial |
| D. Continue disposable Free service | No new fixed monthly compute/disk charge; workspace usage overages are still possible | **Not persistent**: restart, spin down, deploy can wipe users | Safe for temporary functional tests only; requires new synthetic invitations and passkeys |

Official pricing and behavior checked:
https://render.com/pricing
https://render.com/docs/free
https://render.com/docs/disks

The Render Hobby workspace has a saved payment method; therefore even
Free services may incur bandwidth or pipeline-minute overages. The
approximate $7.25/month is **additional to** the existing personal
production service, not a replacement for its current bill.

## Proposed option A conversion (NOT AUTHORIZED YET)

1. Confirm owner explicitly authorizes **up to approximately $7.25/month
   additional recurring base charges**, and acknowledges potential
   taxes/overages; capture the current exact Render quote before action.
2. On the **staging service only**, change the compute plan from Free
   to the lowest available paid web plan (Render Starter,
   approximately $7/month). Keep `autoDeploy` **off** and the
   staging hostname, isolated backend branch, one instance and
   broker/worker/trading flags unchanged.
3. Attach **a new 1 GB encrypted persistent disk to the staging service**
   with mount path `/data`, if supported in the current Render UI.
   Do not attach it to or alter `edgepilot-private-h9tl`.
   The Render disk mount path must match the container.
4. Change only staging `EDGE_DB_PATH` from
   `/tmp/edgepilot-staging.db` to
   `/data/edgepilot-staging.db`. This intentionally starts
   a **new** isolated test database on the newly attached disk.
   Do not copy personal production SQLite or credentials, and do not
   expose real Public API keys.
5. After the new service reports Live, create fresh synthetic
   invitations through the key-gated staging operator path and
   re-register two test accounts. The previously issued disposable
   Test1/Test2 data cannot be assumed restorable.
6. Perform a controlled staging-only manual redeploy; verify
   user IDs, tenant isolation, passkey counts, and passwordless
   login **still exist** after the redeploy and a service restart.
   Back up only synthetic records after defining encrypted backup
   and restore permissions. Do not rely only on disk snapshots
   as a recovery plan.
7. Check that owner production service domain, signed app and
   credentials remain unaffected; monitor new Render charges.
   Roll back only the staging environment if validation fails.
8. Continue two physical devices' isolated sessions and account
   ownership tests with **synthetic** records only. Any real
   brokerage integration or fully autonomous trading remains a
   separate security, provider-authorization and durability gate.

### Important service constraint

Render persistent disks attach only to **paid services** and cannot
be shared across instances. Adding a disk triggers a deploy; disk
snapshots and persistence have their own limitations. Choose the
smallest disk size because it may not be reducible later.

## Required decision

The owner must choose whether to authorize a paid durable staging
backend under the estimated pricing above or keep staging Free
and disposable. **No paid instance, new disk, database or
external service is created by this checkpoint.**

The next developer should resume from this explicit gate rather
than assuming that a successful passkey UI means the two-phone,
independently persisted multi-user phase is complete.
