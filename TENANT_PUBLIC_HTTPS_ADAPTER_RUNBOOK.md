# EdgePilot v0.2.21 — Hardened Public HTTPS adapter groundwork

**Release status: INACTIVE. No real Public connection is authorized or possible
through the v0.2.21 adapter.** The two allowed Public endpoints are documented
here strictly for future approved account-access verification.

Official Public documentation reviewed November 9, 2026:
- https://public.com/api/docs/quickstart
- https://public.com/api/docs/resources/authorization/create-personal-access-token
- https://public.com/api/docs/resources/list-accounts/get-accounts
- https://public.com/disclosures/individual-api-program

The individual Public API requires a personal Secret Token exchange to obtain
a short-lived Access Token. The fixed token exchange is
POST https://api.public.com/userapiauthservice/personal/access-tokens
with `secret` and `validityInMinutes`. Only after receiving an access token
may the client call
GET https://api.public.com/userapigateway/trading/account
with an Authorization Bearer token. That response may list multiple accounts
with distinct accountId values. **It establishes credential access, not
independent proof of legal account ownership.** Public's Individual API
agreement describes personal, non-commercial API use; any architecture
serving multiple separate owners needs a terms/partnership review before
production, rather than assuming authorization.

## Network and API restrictions

`backend/engine/tenant_public_https_wire.py` includes a concrete stdlib
HTTPSConnection request/response implementation and fixed allowlist of
exactly the two paths above. It verifies TLS using the system CA trust store
and hostname, fixes the host to api.public.com and port 443, uses a 5-second
socket timeout, sends Accept-Encoding identity, and uses no automatic
redirects, proxy environment, cookies, retry, or unapproved endpoint methods.

The client caps JSON at 64 KiB, rejects unexpected status, redirects,
compressed/unknown content types, bad JSON and duplicate JSON keys, and
returns only sanitized error codes for 401/403, 429, timeouts/5xx and
other unsupported responses. It does not log access tokens, secret bodies,
account identifiers or raw responses. The auth token exchange uses
5-minute validity, but there is **no real token cache** in v0.2.21.

**The entire real network send method unconditionally fails with
NETWORK_DISABLED.** There is no environment variable, settings toggle,
API route or worker that can make it send to Public. A private fake-connection
test path exercises the *same* request formatting and response parsing
without opening a socket. No production adapter imports this module.

## Credential, account and rate safety

`backend/engine/tenant_public_https_account_adapter.py` binds each test
operation to a verified `user_id + account_id`, active connection, and
correct provider account reference in a detached, memory-backed SQLite
fixture. The encrypted credential is decrypted in memory only after scope
validation; any credential lacking the explicit SYNTHETIC prefix fails
closed before any request. Auth-token and account-list responses are parsed
and checked, and the account scope is reverified between steps and before
returning success. Only Boolean synthetic results are exposed. Live
connection, funds and order methods all fail closed.

`backend/engine/tenant_public_access_controller.py` applies strict
per-user/account and global budgets (two simulated operations/account
per minute, ten global simulated operations/minute), no automatic retries,
and a per-account pause latch on provider failures. Manual offline-only
review is needed before retry after a pause. The emergency stop is
irreversible on that controller instance and blocks all subsequent checks.

These **in-memory test guards are not yet a distributed production
rate limiter or persistent emergency-stop service**. Prior to any real
connection, they need durable state, leader coordination, failure testing,
audit logs, cancellation of in-flight requests, incident procedures and
operator approvals.

## Test acceptance

Tests exercise TLS settings, exact methods and paths, request bodies and
headers, no real socket activity, no redirects, certificate/hostname
verification options, JSON size/type/duplicate-key validation, confidential
credential handling, owner/account isolation, revoked connections, 401,
403, 408/5xx, 429, wrong accountId, per-account rate budgets, manual pause
review, emergency stop and a production database location that is rejected.

Static tenant_route_audit.py rejects accidental imports of all new
components in live Flask and the legacy Observe worker. No live API
route, Android account-enrollment UI, new account, quote scan, trade,
transfer, storage migration or bank function is added.

## Remaining approval gates

Before connecting an actual Public credential, review current Public API
permissions and legal/contract terms, provider ownership/access semantics,
TLS and proxy infrastructure, credential secret rotation/expiration, vault
and key provenance, production-safe distributed rate limits, log redaction,
account revoke races, circuit breakers, identity CSRF handling, emergency
shutoff and monitoring. Require separately approved test credentials,
specific account scope, an explicit network activation change, review of
the entire legacy global-account API and worker, and a rehearsed rollback.

The v0.2.21 rollout is code-only. No production schema is changed; reverting
the release would not need a database reversal. The verified Android
Render SSH host settings and the permanent encrypted backup are unchanged.
