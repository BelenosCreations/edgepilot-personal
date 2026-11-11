# EdgePilot v0.2.49 — Requested tiers versus real entitlements

## Product boundary

EdgePilot's approved architecture anticipates three use cases: one
private owner, up to ten private friends, and possible future Google
Play/commercial distribution. The exploratory Free/Plus/Pro/Custom
names describe future concepts only. **Prices, payment terms,
features, grants, billing providers and commercial launch are not
approved or operational.**

A small, independent tenant-scoped module now stores only each
member's *requested tier concept*. The **effective tier stays Free**
regardless of whether a member asks to review Plus, Pro or Custom.
Even a Free preference does not imply that production tenant
registration or market data access is enabled.

No payment information, subscription identifier, AI credential,
model allowance, Public account credential, API token or trading
permission is accepted or persisted. Paid-tier grant calls are
explicitly rejected. Default free research, provider-specific data
licenses, BYOK spending, managed AI allowances, broker transaction
fees and hosting costs are **independent** product concerns; a
requested subscription label cannot turn on any of them.

The owner-approved future architecture may eventually define paid
features only after actual unit economics, platform policies, data
licensing and required legal/regulatory reviews are complete.
In particular, 15-minute YES/NO markets need separate Google Play
binary-options policy review before any proposed listing.

## Technical scope and security

The inactive `backend/engine/tenant_tier_intent.py` module has
additive, explicitly called schema setup and does not alter the
legacy owner database. Requested tiers are keyed to a server-derived
independent identity; the session, CSRF, credential version, account
disablement and expiry are rechecked inside one SQLite transaction.
There is no HTTP route or public UI, no Render flag change and no
route that can activate an upgrade.

From `backend/`:

    python -m unittest tests.test_tenant_tier_intent_v0249 -v

Tests cover ten independent concurrent users, zero default paid
privileges, cross-user CSRF and revoked-session denial, invalid tier
names, direct paid-grant denial and non-initialization of legacy
databases. No payment provider calls, provider network or active
subscription result is produced.

A future real grant system needs a separately reviewed,
non-forgeable billing/entitlement source, receipt/renewal/refund
and cancellation logic, audit trail, plan-limit protections,
per-user privacy, recovery, data licensing, tax/legal/regulatory
reviews and Play compliance. This module supplies none of these.

The separately mandated two-physical-device/two-separate-Public-account
acceptance remains unresolved. Live trading, cash movement, real
paid AI consumption and distribution stay disabled.
