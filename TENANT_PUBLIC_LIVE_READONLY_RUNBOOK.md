# EdgePilot v0.2.27 — Identity-scoped Public read-only integration

**Default OFF.** The new shared-user Public API path makes only two GETs:
an authorized account list, and a verified account's sanitized portfolio.
A POST exchanges the user's own secret for a short-lived Public bearer.
It cannot place orders, transfer money, enable an autonomous worker or
read another EdgePilot user's data.

## Required feature gates

The following all must be explicitly enabled together on a dedicated,
verified rollout:

EDGE_TENANT_SCHEMA_PREPARE=true
EDGE_IDENTITY_AUTH_ENABLED=true
EDGE_TENANT_ACCOUNT_READS_ENABLED=true
EDGE_TENANT_PUBLIC_VAULT_ENABLED=true
EDGE_TENANT_PUBLIC_READONLY_ENABLED=true

No gate is enabled by this release. The owner's legacy login/dashboard,
global Public secret and service worker continue to work independently.

## User-owned API contract

- GET /api/identity/public/read/connections/{connection_id}/accounts:
  derive user ID from the identity session cookie; decrypt only their
  active connection; authenticate with Public; list up to 30 account IDs
  returned by the provider. This is not a global connection or cache.
- POST /api/identity/public/read/connections/{connection_id}/accounts:
  requires identity CSRF and a provider account ID that was returned by
  the CURRENT session's real Public account list; binds an internal tenant
  UUID to the verified identity + key in a transaction.
- GET /api/identity/public/read/accounts/{internal_account_id}/portfolio:
  require an owned, active, linked account and unrecalled connection,
  list authorized Public accounts again, and fetch ONLY that account's
  portfolio. Return a sanitized balance + at most 100 positions. No raw
  Public order, personal, banking or transfer payload is returned.

All identities and connections are looked up on the server. No caller can
supply a different user ID. POSTs need same-origin, Secure HttpOnly session
and X-Edge-Identity-CSRF. A cloned or swapped credential is denied by comparing
its saved encrypted revision before/after network traffic; account linking
rechecks within the final SQLite write transaction. Provider tokens are
short-lived, held in memory only for one request and NEVER globally cached.

Strict request allowlist: POST
https://api.public.com/userapiauthservice/personal/access-tokens;
GET https://api.public.com/userapigateway/trading/account;
GET https://api.public.com/userapigateway/trading/{ID}/portfolio/v2.
Only verified, syntax-checked account IDs are interpolated. TLS verification
remains on; no arbitrary URLs/redirect targets/HTTP methods are accepted
from the client. Provider errors are sanitized. Quota: 20 operations/user
and 250 globally per 60 seconds with a persistent transaction-serialized
admission table; this is a safety limit, not an investment-size assumption.

## Limits and roll-out requirements

The adapter uses the existing per-user encrypted credential vault. It has
not yet been enabled in Render, and no actual second Public API key has been
supplied for live end-to-end verification. All automated tests use completely
synthetic Public secrets/tokens and an injected transport with NO network.
Service availability and provider account entitlement must still be checked
when the actual integration is activated.

A moving account balance/history is not yet stored per tenant in production;
no user registration, full Android passkey UX, native Credential Manager
setup, multi-user worker scheduling or complete backup/restore isolation
exists yet. The user-requested two-device/real-two-key acceptance goal
remains OPEN. Enable only after real production HTTP isolation, safe backup,
user onboarding and device testing. Provider permission is an engineering
assumption for development, not a statement about an actual API grant.
