# v0.2.86 — Protected-balance policy consistency (dormant risk calculator)

The user's previously approved protected-balance setting is **0–99%**, not 1–100%. A 100% selection would eliminate the allocation and is not offered. The owner previously asked development to continue without routine stops and requested one functioning user before returning to real two-device/multi-user tests.

This milestone corrects the existing **pure, offline** `engine/risk.py` model to that documented range. It does **not** enable an auto-trading worker, ask Public to authorize trades, read an actual brokerage account, change a real member's allocation, or move money. Nothing in `risk.py` is a trading entitlement.

## Fail-closed inputs

A future execution/paper workflow must supply independently verified and **fresh and reconciled** brokerage account equity, the separately confirmed EdgePilot budget if using independent-balance mode, actual broker buying power, all EdgePilot-attributed/other/open/unreconciled exposure, user-approved spending and per-trade caps, and any external sales awaiting a human decision. **Brokerage total portfolio value alone is not broker buying power.** Every unknown, missing, negative, non-finite or overrange required numeric input fails rather than creating a synthetic quantity. A stale or unreconciled snapshot or unresolved manual sale blocks the calculation.

The protected percentage can be any finite value from 0 through 99 inclusive. For internal rounding, spendable risk budget, remaining capacity and individual order caps are **rounded down to the nearest cent**, while protected balance is **rounded up**. This prevents exposing fractional cents of unsupported risk capacity and prevents understating the value the user asked to protect. The calculator remains a planning bound, not a prediction or a guarantee against market loss.

```text
Potential risk budget = min(user spend cap, allocation × (1 - protected percentage / 100))
Outstanding exposure = EdgePilot attributed positions + other positions
                     + open orders + unreconciled orders
Potential available capacity = max(0, min(budget - outstanding, broker buying power))
Potential per-trade limit = min(available capacity, user per-trade cap)
```

The supported isolated risk model still does not claim to calculate true risk of loss from quotes or other financial instruments. It does not bypass the dormant engine configuration or user/account isolation.

## Synthetic acceptance

v0.2.86 tests exercise the 0% and 99% protection boundaries, 100% rejection, independent allocation reconciliation, combined existing exposure, zero broker buying power, shortfall to zero, manual sale blocks, stale/unreconciled reports, finite/non-finite/missing inputs, and fractional-cent rounding. Existing legacy `test_engine.py` is updated to enforce the new range, rather than continuing to expect 100% to be a valid setting.

No real account values, balances, keys, tokens, trade requests or private backups are stored in public GitHub. The model is not wired to the authenticated owner's live portfolio dashboard and cannot submit orders or transfers. Future Observe/Paper mode needs separate source provenance and simulated quotes before these capacity bounds are displayed as a usable plan.

All completed multi-user identity, invitations, independent brokerage connections, protected storage and recovery work are preserved. No new paid infrastructure and no changes to live trading or bank-transfer switches are needed. Merge only after GitHub PR tests and merged-main tests succeed; Render's existing auto-deploy may restart the backend but no new runtime flag is introduced.
