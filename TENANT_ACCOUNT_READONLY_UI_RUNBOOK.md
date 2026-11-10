# EdgePilot v0.2.31 — User-scoped Public account discovery and portfolio UI

## Goal

A separately authenticated EdgePilot user can select only their own encrypted
Public connection, discover that connection's broker-reported account list,
request verified read-only linking, and view sanitized portfolio balances and
holdings. Nothing in this UI submits an order or requests a funds transfer.

The /account web page uses existing tenant Public read-only APIs. The browser
never receives a Public secret after creation; the backend resolves and
decrypts it only for the verified identity session. Server-side account
binding independently verifies the account ID is reported by the owner's
own Public credential. Arbitrary account ID changes cannot authorize access.

## Feature gates and safety

The server is configured default-off for:
- EDGE_TENANT_SCHEMA_PREPARE
- EDGE_IDENTITY_AUTH_ENABLED
- EDGE_TENANT_ACCOUNT_READS_ENABLED
- EDGE_TENANT_PUBLIC_VAULT_ENABLED
- EDGE_TENANT_PUBLIC_READONLY_ENABLED

The /account page renders a clear unavailable message when backend gates are
off. It never routes identity credentials into the legacy owner app and does
not use the existing legacy global selected account. User and connection IDs
come from authenticated server-side reads and are encoded as URL path
components; provider-discovered account IDs are accepted for linking only
after a server-side ownership verification.

Portfolio rendering refuses responses unless readOnly=true, ordersEnabled=false
and transfersEnabled=false, and the returned internal account ID matches the
selected linked account. Displayed text is assigned using textContent and
document.createTextNode, not raw HTML. A sign-out or different identity session
clears all previously displayed connections, accounts, holdings and balances.

## Current boundaries

This is a user-facing read-only connection selection interface, not
production multi-tenant activation. User-scoped Public reads are separately
gated and may use actual provider network calls only in an explicitly
enabled environment. CI uses fake provider responses. No real Public
keys, transactions, account balances or execution payloads are tested in CI.

No conversion of the legacy owner dashboard, worker strategy execution,
historical imports, individual watchlists or platform-wide backups has
occurred. Biometric login still requires trusted APK signing, Digital Asset
Links and independent device tests. Source installation and account UI
checks cannot prove two real devices have isolated Public accounts.

## Validation

Backend Python and Flask tests, JavaScript syntax and GitHub CI must pass,
including static client checks that reject order/transfer routes and unsafe
HTML insertion. Existing v0.2.27 synthetic HTTP integration tests verify
two users cannot discover or link the other user's provider account. The new
UI's verified account labels and portfolio views should receive manual
Android/browsing testing after controlled authentication enablement.

No production feature flags are changed by this code-only milestone.
