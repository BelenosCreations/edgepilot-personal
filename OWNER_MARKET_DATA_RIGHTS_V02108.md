# Public market-data rights for EdgePilot

Reviewed November 13, 2026. The Public Individual API documents personal,
noncommercial use. Its agreement limits use to authorized purposes, allows
additional market-data terms, restricts third-party applications under the
individual program, and requires written approval for dissemination to third
parties. The API scope establishes technical access for eligible accounts.
Applicable feed-specific terms and account entitlements still govern use.

| Source and purpose | Evidence | EdgePilot treatment |
| --- | --- | --- |
| Stock quotes for personal display | Public documents manual `EQUITY` quotes under `marketdata`. Its Market Data Addendum includes source-specific exchange terms. | Existing owner-only, source-attributed manual view with provider timestamps. |
| ETF quotes for personal display | The quote endpoint uses `EQUITY` for eligible ETF symbols. ETF coverage and applicable feed terms depend on the instrument. | Same owner view. Missing provider data stays unavailable. |
| Crypto quotes for personal display | Public documents `CRYPTO`. Its crypto supplemental agreement says digital-asset market information may come from third parties. | Same owner view for supported symbols. Individual source rights need confirmation for any expansion. |
| Source-derived owner quote spread | Existing view computes the spread in memory from timestamped, fresh bid and ask. Public's terms can apply to derived data as well. | Existing owner-only session display. Keep each quote's source and observation timestamps. |
| Stock, ETF or crypto historical bars and personal backtesting | Public documents bars for `EQUITY` and `CRYPTO`, including a backtesting example. The API documents historical chart lead-in metadata. | Keep historical research dormant. Verify entitlement, bar coverage, corporate-action treatment and use-specific rights before an owner history feature. Exclude chart lead-in values from observed prices. |
| Short-lived cache, logs, saved charts, exports, backups and durable history | The reviewed sources establish no EdgePilot-specific retention permission or permitted period for these uses. | Keep provider observations and derived values out of these stores pending source- and purpose-specific verification. |
| Persistent paper fills, replays, derived datasets or model inputs | Access to the quote or bar endpoint does not establish permission for these uses. | Keep real-data persistence and paper fills disabled. |
| Family sharing, redistribution or a service for third parties | The individual program restricts third-party use and dissemination. | Keep the owner market-data route owner-only. Obtain written authorization covering the intended program, recipients and feeds before expanding access. |

## Official sources

- [Public Individual Trader API Agreement](https://public.com/disclosures/individual-api-program)
- [Public Market Data Addendum](https://public.com/disclosures/public-market-data-addendum)
- [Public crypto supplemental agreement](https://public.com/disclosures/platform-supplemental-agreement-crypto)
- [Public Get quotes](https://public.com/api/docs/resources/market-data/get-quotes)
- [Public Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2)

The owner-verified account comparison and MSFT observation are recorded in
[owner acceptance](OWNER_ACCEPTANCE_V0294.md). They establish what worked in
that owner session. Provider-specific retention approval remains pending.
