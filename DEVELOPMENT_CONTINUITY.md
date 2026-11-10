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

The repository includes account identity sessions, one-use invitation signup,
a user-owned encrypted Public credential vault, gated Public read-only
account discovery/linking and portfolio retrieval, WebAuthn passkey server
verification, a mobile-ready separate /account interface, an Android WebView
Web Authentication capability check, a fail-closed Digital Asset Links
endpoint, and synthetic monitor/worker fencing and emergency-stop tests.

The legacy owner app and Observe/Paper worker still use global single-owner
state, and cannot be called by tenant sessions. Account-specific monitoring
is being added in small, independently gated read-only increments, not by
silently enabling the existing global worker.

Major outstanding work includes stable Android release signing, verified
Digital Asset Links, physical biometric WebAuthn enrollment/sign-in on two
devices, account recovery, controlled tenant activation and data migration,
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
