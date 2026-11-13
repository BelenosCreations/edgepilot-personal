# v0.2.94 — Owner acceptance and receipt-scoped research

## Owner-reported live acceptance (2026-11-12, America/New_York)

After GitHub main `1cedfd760eecb67be305afa8462e20dc09200650`, GitHub Actions `43357095572` passed, and existing Render service `edgepilot-private-h9tl` deployed `dep-dbr7v0p42hec73ba42p0` live, the owner reported two successful tests from the independent authenticated `/owner` dashboard:

1. A manually retrieved, selected-account, read-only Public portfolio value matched the official Public app to the cent as compared directly by the owner.
2. A manually requested Public API `MSFT` (`EQUITY`) quote displayed provider-reported last/bid/ask. The UI marked the last observation stale and distinguished the more recent, timestamp-qualified two-sided book within its freshness window.

**Acceptance completed.** Do not ask for the identical manual test again absent a later targeted regression requirement. The observation is the owner's report, not an independent inspection or storage of private values, provider credentials, symbol quote numbers, provider account identifiers, passkeys or raw HTTP responses. No account balances or actual quote prices are committed to GitHub.

### Rights and confidence boundary

A successful live quote response demonstrates the existing authorized owner could retrieve real Public quote data in that session, NOT that Public grants historical quote retention, retransmission, market-data licensing, executable prices, durable paper-fill evidence or permission to serve other users. Do not equate a successful owner quote with all `marketdata` entitlements or a signed origin attestation. Public-reported quote freshness depends on timestamp and server-receipt time, not the age of an open browser view. The account comparison concerns one snapshot and one manually transcribed app value at approximately the same time, not broker reconciliation or verified investment returns.

## v0.2.94 UI safeguard

The owner dashboard computes a strictly local and ephemeral **bid–ask price-unit difference** from validated Public-reported bid and ask only when both independent quote timestamps were fresh at EdgePilot server receipt. It uses 12-place exact-decimal integer arithmetic, not floating-point, and displays **Unavailable** if either side is untimed, absent or stale. The page explicitly says that freshness holds at receipt only, not indefinitely; this is neither the broker's published spread nor an executable order price, profit, performance or fee forecast. No extra provider calls, market-data storage, worker, client timer, automated trading or paper fill.

## Remaining blocked gates

- Confirm data rights and scoped source provenance independently before caching, durable market-history storage or paper fills.
- Complete production-safe, authenticated/encrypted paper-ledger backup and restore with separate tenant/account isolation, rollback and restore quarantine checks; existing v0.2.89 coverage is **synthetic-only**.
- Create identity/CSRF/rate-limited paper-only API/UI only after the above controls and an explicit production activation decision. The existing paper-preview and paper-ledger modules are dormant.
- Live orders, autonomous brokerage activity, production paper fills and bank transfers stay disabled. Preserve all existing linked accounts, credentials, multi-user structures, encrypted recovery and the same paid Render service/disk.

## Tests

`backend/tests/test_owner_quote_browser_v0293.py` executes the shipped JavaScript quote parser using synthetic MSFT quote shapes, including stale/untimed book rejection, exact 12-digit spread arithmetic and crossed quote refusal. The wider CI still checks account isolation and the dormant paper recovery. This release does not rerun real brokerage calls or request private acceptance data.
