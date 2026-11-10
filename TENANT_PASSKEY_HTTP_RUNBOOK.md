# EdgePilot v0.2.29: Gated WebAuthn HTTP ceremonies

## Not live on deployment

This release adds server-side WebAuthn endpoints, disabled by default.
No EdgePilot production configuration is changed automatically. Existing
Android WebView does not yet expose biometric/passkey login controls.
Real Public account use, trades, transfers and global worker activation
remain separate and disabled.

Enablement requires EDGE_TENANT_SCHEMA_PREPARE=true,
EDGE_IDENTITY_AUTH_ENABLED=true, EDGE_TENANT_PASSKEYS_ENABLED=true and
fixed EDGE_WEBAUTHN_RP_ID and EDGE_WEBAUTHN_ORIGIN values. The RP ID
must be the exact public HTTPS hostname (not request.host or a client
parameter); origin must exactly match https:// plus that same host.
Any missing/invalid configuration fails startup closed.

## Identity-only endpoints

- POST /api/identity/passkeys/register/options and .../register/finish
  require a verified identity cookie, same-origin request and identity CSRF.
- POST /api/identity/passkeys/authenticate/options and .../authenticate/finish
  are unauthenticated only for obtaining/verifying a short-lived WebAuthn
  challenge. They require same-origin HTTPS. The finish operation verifies
  origin/RP/challenge/public-key signature and user verification before a
  secure HttpOnly SameSite=Strict identity cookie is issued.
- GET /api/identity/passkeys requires identity cookie and identity CSRF and
  returns only the count of registered passkeys.
- DELETE /api/identity/passkeys/<credential_id> requires identity cookie and
  identity CSRF; revokes only the current owner's credential and invalidates
  that owner's identity sessions, not other users.

All cookies are identity-only and cannot access existing legacy owner routes.
A passkey proves the EdgePilot identity, not ownership of a brokerage account.
The existing individually encrypted Public vault still requires a separately
enabled feature gate and user-scoped provider ownership validation.

## Biometric data

The Android operating system / credential provider performs biometric or
device-PIN user verification. EdgePilot receives signed WebAuthn assertions
and stores credential public keys and counters, NOT fingerprint or facial
templates. This release does not attempt to fake biometric login with a
client-side PIN prompt or Android local-only BiometricPrompt.

## Threat boundaries and remaining work

The Android WebView shell must integrate WebKit WebAuthentication support,
native Credential Manager, verified Digital Asset Links, and functional
sign-in/register UI. Real-device testing on two Android installations is
required; a successful stubbed unit test does not prove native passkeys.
Credential recovery / lost-device workflow and provider-scoped account
monitoring are still pending. Challenge quotas, one-time use, expiry and
replay protection are covered by existing tenant_passkeys unit tests.

The live Public API terms/authorization assumption is for engineering
development only, not a verified right to connect unrelated real accounts.
The milestone completes only the gated HTTPS server ceremony boundary.
