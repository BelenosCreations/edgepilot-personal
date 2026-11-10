# EdgePilot v0.2.20 — Public read-only response contract, offline only

**Hard state: INACTIVE. NO REAL PUBLIC AUTHENTICATION.**

This release prepares a narrow credential/token/account-list verification
contract based on Public's official documentation as reviewed Nov 9, 2026:

- POST `https://api.public.com/userapiauthservice/personal/access-tokens`:
  exchange a user-generated secret for a temporary `accessToken`.
- GET `https://api.public.com/userapigateway/trading/account`:
  list accounts accessible to the authenticated token. Uses
  `Authorization: Bearer ACCESS_TOKEN`.

Official sources:
- https://public.com/api/docs/quickstart
- https://public.com/api/docs/resources/list-accounts/get-accounts

**Important:** The Public key can provide access to an account; a matching
`accountId` from this endpoint does not, by itself, establish legal account
ownership or authorize EdgePilot to execute trades. Public's real API is
capable of both read and write actions, and individual keys are sensitive.

## What was implemented

`backend/engine/tenant_public_readonly_preflight.py` defines:
- The two exact documented endpoint **shapes**.
- A recorded-response transport that is **not an HTTP client**, contains
  no sockets/requests/urllib networking, and rejects non-synthetic secrets.
- A verifier that reads only a detached, verified RAM-backed SQLite fixture.
  It checks `user_id + account_id + provider=public + connection` with an
  active user and non-revoked connection before decrypting an encrypted
  **synthetic** credential in process memory using a separate fixture key.
  A real credential fails the explicit `SYNTHETIC-` prefix gate.
- In-memory simulated access-token exchange, then recorded GET accounts.
  Only an exact account reference match succeeds; duplicate, empty,
  malformed, unsupported or mismatched replies fail closed.
- Distinct sanitized codes for 401/403 auth rejection, 429 rate limiting,
  upstream unavailable, invalid response and account not accessible.
  Provider response contents, original secret, access token and account
  references are never returned to the result or logged.
- A returned status that explicitly says `verified_by_real_public=False`,
  `verified_legal_owner=False`, no network calls, no orders, no activation.

`backend/engine/tenant_public_preflight_batch.py` processes a
deterministically bounded list of pre-existing, disabled, account-scoped
test plans. A bad binding or failed recorded response causes only the
affected synthetic account to be paused using v0.2.19's revision-fenced
recovery gate. Other accounts remain available for independent recorded
preflights. A corrected simulated response never automatically resumes
a paused account; manual synthetic review is still required.

**No provider requests of any kind occur** in these tests. There is no
actual URL session, network transport, login, credential exchange, live
account verification, worker scheduling, paper/live order, funds transfer
or production database write. The legacy selected Public account and
single-owner Observe worker remain unchanged.

## Test coverage

- Multiple owners and separate accounts under one owner; wrong-owner
  and revoked-account access refused.
- Mock token exchange + get accounts responses, encrypted fake credentials
  and complete non-disclosure of secrets/tokens in results.
- Auth failures 401/403, rate limit 429, unavailable 5xx/408, bad/empty/
  duplicate accounts and mismatching accountId; malformed tokens refused.
- Wrong encryption key, any non-synthetic credential, unknown transport
  object, and exact-only provider endpoint constraints.
- Independent account failure isolation, no automatic recovery, stale
  manual recovery rejection, and revalidation on account revocation.
- Guard tests ensure new modules never appear in the production Flask app
  or worker; static audit rejects accidental import.

## Remaining blockers before any real account verification

A separately approved real read-only Public transport design is required:
TLS pinning or strong CA/hostname verification, safe network timeouts,
no redirects, DNS/SSRF protections, account-scoped credential retrieval and
rechecks, avoiding all order-capable interfaces, token expiration,
rate-limit handling, logging redaction and request budget monitoring.
A new consent ceremony for real account authorization, provider agreement
and key permission review is also required. No shared API token should
be entered into ChatGPT messages, GitHub files, app screenshots or test
logs. The API account list proves credential **access**, not legal
ownership; explicit broker-side verification is required if that is the
desired legal claim.

Before live multi-account operation: replace legacy global account
reads in *all* HTTP routes/worker, design fully isolated per-user worker
scheduling, Android account enrollment/switching, reversible migrations,
security review and a separately approved activation plan.

## Rollback

All code is dormant; schemas in tests are generated on disposable /dev/shm
SQLite fixtures. No production tables, credentials or worker settings are
altered. Rolling back this release is code-only. CHANGELOG.md, version
metadata and this runbook document the unchanged security posture.
