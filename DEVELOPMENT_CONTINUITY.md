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

