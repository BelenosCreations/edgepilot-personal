# EdgePilot v0.2.22 — Inactive Public consent, rotation, and safety gates

**Test-only. No real brokerage credential exchange, connection, trade, fund transfer,
new account activation, background job, or production database migration.**

Public's official API documentation describes a personal Secret Token exchanged
for a short-lived Access Token, then GET account listing using that bearer
token. Public's Individual API program is expressly **personal and
non-commercial**; supporting separate real owners beyond personal use may
require a different contractual integration or written approval.

Official documentation reviewed November 9, 2026:
- https://public.com/api/docs/quickstart
- https://public.com/api/docs/resources/authorization/create-personal-access-token
- https://public.com/api/docs/resources/list-accounts/get-accounts
- https://public.com/disclosures/individual-api-program
- https://public.com/disclosures/api-policy

## Two-step, session-bound approval — offline only

`tenant_public_offline_consent.py` creates only disposable
`tenant_test_public_consents` records. Step 1 requests one exact account
for an authenticated identity session and checks the identity CSRF token.
Step 2 requires the same session, matching CSRF token, exact confirmation
phrase, and current revision within a 10-minute expiry.

The only recorded scope is `SYNTHETIC_PUBLIC_ACCOUNT_LIST_ONLY`.
Approval never enables live Public, trading, money movement, worker
scheduling or account enrollment. Any account revocation, session
revocation, stale approval, wrong owner or expired consent denies access.
The module is not imported into live Flask or Android.

## Synthetic credential rotation

`tenant_public_synthetic_rotation.py` models an atomic, encrypted,
optimistic-concurrency-controlled credential rotation for a **fake**
connection only. Every linked account must have its own valid, same-session
offline approval. One SQL write transaction checks current account
membership and expected generation before replacing the encrypted fake
secret. It writes a secret-free audit record, revokes previous offline
approvals for ALL accounts linked to the connection, and pauses all
affected accounts. Reapproval is required before another simulation.

Real secrets are rejected, and the provider is never called to revoke
a real key. The old ciphertext is not stored in audit records. A real
production rotation system would require a provider-revocation lifecycle,
trusted vault, key version management, account owners' legal permissions,
backend incident response, a tested recovery/rollback procedure, and
disconnected-device reauthentication.

## Persisted emergency latch and rate budgets — test database only

`tenant_public_safety_state.py` stores atomic test state in isolated
SQLite under verified **/dev/shm**. It enforces two simulated requests
per account per 60 seconds and ten globally, no auto retries, and a
revision-fenced manual test-only pause clearance.

The global emergency stop is an irreversible latch for that **SQLite
fixture**, and remains stopped when a new controller instance opens the
same test database. It cannot be reenabled through the exposed module.
However, **/dev/shm is volatile**. This does NOT survive host replacement
or restart and is NOT a durable production kill switch. The existing
legacy worker is not connected to it, so it has no effect on live
monitoring. Production would require durable, replicated, audited safety
state and worker-level enforcement with cross-instance consistency.

## Explicit connection readiness report

`tenant_public_connection_readiness.py` requires authenticated
same-account offline consent, an unpaused account and nonstopped test
safety state. A report can affirm that isolated simulation gates passed,
but returns `real_public_connection_ready=False` and
`actual_public_network_authorized=False` in all circumstances.
It also reports that real provider access, legal ownership verification,
production kill switch, production tenant API/worker isolation, and
multi-owner contractual review are outstanding.

The v0.2.21 real Public HTTPS send method **remains hard-disabled**;
no environment flag can enable it. Static `tenant_route_audit.py`
rejects accidental imports of any new v0.2.22 modules into live Flask
or the legacy Observe worker. Existing global selected-account routes
and the single-owner monitoring worker are still cutover blockers.

## Test and rollback rules

Run the full GitHub CI suite and post-merge CI before marking a release
complete. The synthetic regression suite tests per-owner and shared
connection accounts, cross-user authentication, expiry, CSRF, revocation,
out-of-date credential versions, atomic rotation, audit redaction,
cross-controller request limits and irreversible stop, and no live wiring.

No new module is initialized at production startup. No production schema,
broker credential, account access, monitoring strategy, bank setting,
Android APK or protected encrypted recovery backup is changed. Code
rollback needs no data rollback. The owner must separately approve
**any** future real connection, terms review, key use, production schema
migration, or activation.
