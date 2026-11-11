# EdgePilot v0.2.50 — Conservative over-preflight AI reconciliation

This milestone closes an accounting safety gap in the **dormant** per-member
AI BYOK ledger. A provider's measured token cost may exceed an application's
preflight estimate/reservation. That is a spending-risk event, **not a normal
completed cheap request**.

The independent tenant ledger now compares any synthetic measured
reconciliation against its own stored reservation. If measured usage
exceeds the held microUSD amount:

- The reservation becomes `uncertain`, not an ordinary completed cheap
  request. The measured overage is retained as an attributed cost.
- Subsequent monthly-budget admission counts the greater of the held
  reservation and measured usage. This can legitimately exceed the
  local member budget and leaves no available balance for further
  synthetic reservations in that month.
- An unknown provider cost still holds its full reservation without
  inventing a measured cost.
- The response explicitly records `overageDetected`; a different
  member cannot settle or hide that overage, and a second settlement
  attempt is refused. Disconnecting or rotating the key does not erase
  the prior month's attributed cost.

This is still **not** a guaranteed provider-side spending ceiling.
An actual provider could charge above the app's intended limit. Real
execution must separately validate provider token/price reports,
enforce supported request bounds and rate limits, receive opt-in,
handle timeouts, reconcile invoices and monitor actual provider spend.
No billable provider execution is enabled in this milestone.

Test from `backend/`:

    python -m unittest tests.test_tenant_ai_budget_overage_v0250 -v

All fixtures use temporary fake credentials and synthetic token counts.
Tests cover measured overage, budget lockout, unknown usage, ordinary
low-cost completion, key disconnection history, cross-member denial and
double-settlement refusal. No HTTP provider call, Android APK,
subscription, bank transfer or live brokerage order is activated.

The separate two-physical-Android-device/two-independent-Public-account
acceptance gate and real security/operational validation remain open.
