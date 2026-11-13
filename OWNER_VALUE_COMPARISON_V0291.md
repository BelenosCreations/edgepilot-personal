# v0.2.91 — Manual owner account-value display comparison

## Scope
After an independent EdgePilot owner signs in on `/account` and opens `/owner`, they choose their **verified linked Public account** and manually click **Retrieve read-only snapshot**. Only then does **Compare displayed values** activate. The owner may open the official Public app on the same account, inspect its account total and enter that value into the owner dashboard.

The browser computes a signed difference from exact integer cents using BigInt, with no floating-point conversions. If equal, the UI states only that the two displayed numbers are equal to the cent, **not** that the accounts or valuation methods are independently reconciled. Differences are clearly signed and indicate which value is higher. Without a loaded snapshot, or after a selected-account change, comparison is refused. Entered values are for display only and are never sent to any EdgePilot endpoint, Public, storage, logging, or other account.

## Data and safety boundaries
- A new snapshot, account change, refresh of linked accounts, signout or page exit clears the owner-entered amount, comparison and internal snapshot reference.
- Input accepts nonnegative USD with up to 12 integer digits and at most two decimal places, no thousands separators or exponent notation. Display strings and differences are handled without IEEE-754 monetary rounding.
- Snapshot still comes from the existing owner identity-cookie, account-verified, sole-owner-gated Public read-only endpoint. No new backend or brokerage route exists.
- The comparison does not establish live Public quote access, marketdata authorization, vendor history/retention rights, quote recency, paper execution eligibility or realized performance. The owner must explicitly compare the same brokerage account at approximately the same time; the app cannot independently check the user-entered balance.
- All dormant tenant paper-ledger and synthetic encrypted recovery modules are untouched; no production paper fill, live trade, autonomous order, bank transfer, new hosted service or credential mutation.

## Acceptance
1. On the owner's Android phone, sign into `https://edgepilot-private-h9tl.onrender.com/account`, navigate to `/owner` and retrieve the linked Public account snapshot.
2. Open that same account in the official Public app, enter its displayed USD account value and select **Compare displayed values**. Report whether the numbers are equal or differ; **do not send financial balances, account identifiers, API tokens or passwords to the repository**.
3. Change selected account and verify the previous amount/difference disappears. Fetch a new snapshot; confirm the comparison stays disabled until then.
4. Independently request a single symbol quote and record success vs safe unavailable, the shown Public source and timestamp/freshness, with no reproduction of sensitive account identifiers.
5. CI synthetic Node exact-cent tests and static identity/scope tests establish only code behavior, not the real provider's marketdata entitlements or device acceptance.

This is a read-only milestone with $0 added service cost. Before considering real paper fills, require authoritative market data rights, history provenance, tenant-scoped durable encrypted recovery, a clean restore rehearsal and explicit activation approval.
