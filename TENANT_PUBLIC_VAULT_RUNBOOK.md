# EdgePilot v0.2.26 — Identity-scoped encrypted Public connections

**State: OPT-IN STAGING. Not activated in the owner deployment.**

## Why

EdgePilot's current production Public credential is a single global encrypted
record. That cannot be reused safely for independently signed-in users.
v0.2.26 adds a separate, user-scoped store and HTTP lifecycle API for the
shared multi-user architecture. It does not make live Public requests yet.

## Security requirements

The feature requires ALL server flags:
- EDGE_TENANT_SCHEMA_PREPARE=true
- EDGE_IDENTITY_AUTH_ENABLED=true
- EDGE_TENANT_PUBLIC_VAULT_ENABLED=true

The latter remains false by default. Encrypted storage requires the existing
private EDGE_CREDENTIAL_KEY environment secret; the public key is entered
into the HTTPS browser UI and must never be pasted into a chat or source file.

A session-authenticated identity can call these endpoints:
- GET /api/identity/public/connections — list only its own connections; never
  return a secret, ciphertext, token or provider account reference.
- POST /api/identity/public/connections — accept a secret only, encrypt it
  server-side into a row owned by the verified identity, mark unverified.
- POST /api/identity/public/connections/{id}/rotate — re-encrypt replacement
  secret and invalidate every previously linked account on that connection.
- DELETE /api/identity/public/connections/{id} — one-way disconnect and
  invalidate linked accounts, without affecting another identity.

These HTTP mutations require a Secure HttpOnly identity session, matching
Origin and X-Edge-Identity-CSRF, as enforced in the existing middleware.
Unknown, revoked, disabled, cross-owner or malformed IDs fail closed.
No user_id from the HTTP body is permitted; users cannot choose identity.
All audit rows are append-only and event-only; secret fields are omitted.
Encryption verification and sensitive secret decryption remain backend-only.

## What remains disabled

This milestone never performs a Public network request, account discovery,
broker portfolio read, trading order, bank transfer or worker action. It
also does not enable public sign-up, attach real provider accounts, or expose
a new user-facing form yet. Saved keys are explicitly **stored_unverified**.

The sole internal method that can decrypt a user's own credential is
not called by Flask and is statically prohibited from being called from
the legacy HTTP app. Future read-only adapter must verify an account's
Public ownership, use the correct credential, and enforce per-owner budgets,
request cancellation and revoked account checks.

## Tests and acceptance

Unit and Flask tests exercise two separate identity cookie jars, distinct
synthetic keys, encrypted database bytes, cross-user rotation/disable denial,
password/CSRF/origin protection, missing key fail-closed behavior, append-only
audit, account binding invalidation, and unchanged legacy broker table.
CI must pass on PR and on main after merge.

A user working on a different device with an actual independent Public
account is NOT yet proven; see TENANT_PASSKEY_SHARED_PLATFORM_RUNBOOK.md.
Development may assume Public multi-user integration permission for code and
tests, but that assumption is not a claim of actual authorization.
