# EdgePilot v0.2.82 — Single-owner first, multi-user retained

## Approved priority change, November 12, 2026

The owner requested focusing the next EdgePilot milestones on **one fully functioning user** before performing a real second-device/family enrollment test. All multi-user foundations, isolated user/account schema, private invitation workflow, credential vault, encrypted recovery rehearsal, and existing production flags are **retained without disabling, removing, deleting, migrating or resetting them**. No invitation is to be issued now. The product should continue to be designed so that separately scoped users can join later without redevelopment.

The user previously verified the independently authenticated owner account and invitation interface, and the temporary operator's read-only first-invitation audit reported one owner and one encrypted verified linked Public account. **This is not proof of portfolio, market-data, trade or AI readiness.** The last merged production code is v0.2.81; existing paid Render service, separate databases and old legacy dashboard remain available.

## Single-owner acceptance milestones

1. **Owner identity, app navigation and brokerage association.** Confirm a real Android owner can sign in to the account page, retain existing legacy dashboard login, see the correct own Public connection/account, and recover a session after normal app restart. No global selected-account fallback. Original brokerage API key is never displayed. The v0.2.74 encrypted off-Render backup remains preserved.
2. **Bounded live read-only portfolio.** A separately approved, explicitly default-off `EDGE_SOLO_OWNER_PORTFOLIO_ENABLED=true` may enable one verified independent owner to request their linked Public portfolio and holdings, sanitized via the existing allowlisted provider HTTP reader. Without this flag, the current discovery-only 404 behavior remains unchanged. No polling, orders or transfers. A member, former member, missing owner identity, wrong account, stale provider response or invalid encryption must fail closed.
3. **Trusted market observations and research.** Stock, ETF, crypto, prediction and fifteen-minute market analysis must distinguish actual provider data from synthetic/backtested results, record freshness and permissions, and refuse signals without verified coverage/pricing/fees. Free-first market-data sources only, no additional paid subscriptions without approval.
4. **Observe/paper workflow with protected balance and stops.** Verify dashboard gains/losses and budget settings, reconciliation, opportunity research and risk enforcement with traceable simulated outcomes before enabling any autonomous live execution. Keep customer-account permissions and separate member data models as the permanent direction.
5. **Only after separate authorization:** Broker live-order and autonomous trading integration, individual risk caps, loss stops and manual bank deposits/withdrawals. Existing broker and bank execution controls stay OFF until separately approved.

A later independent second-user acceptance can reuse the current invitation-only coexistence architecture and the dormant multi-member encrypted backup design. No second member is necessary to complete stages 1–4.

## v0.2.82 development boundary

`backend/engine/solo_owner_portfolio.py` introduces a **narrow pilot** whose independent flag defaults OFF. At startup it accepts only the existing independent encrypted, discovery-only legacy-coexistence setting, with no trading worker, live orders, monitoring, watchlist edit, passkeys, staging or forced tenant-only cutover. It intentionally neither requires nor disables existing owner invitations or signup flags: existing multi-user configuration can remain on.

The GET portfolio endpoint checks the real identity session has owner role, and the private tenant database contains exactly **one** active enrolled owner identity, before contacting Public and **again after** the allowlisted provider response. If another member registers at any point, all subsequent solo portfolio requests (including an in-flight response whose post-check fails) refuse access until a deliberately reviewed multi-user portfolio policy replaces this temporary pilot. This is a temporary read-access restriction, not a deletion or disabling of the multi-user system.

The account screen renders a read-only portfolio action only when its authenticated, owner-scoped API response explicitly says the solo portfolio capability is available. It retains discovery-only status for all other users and hides inactive monitor/watchlist controls in this narrow owner pilot. It refuses to render portfolio results that lack explicit no-orders/no-transfers and matching account identifiers. Never persist API keys or member data in public GitHub, browser URLs or client storage.

**Not yet activated in production:** `EDGE_SOLO_OWNER_PORTFOLIO_ENABLED` is not set on Render, the current protected discover/link feature and invitation config remain unchanged, no real balance/holdings request has been made, and the new feature is being tested using only disposable SQLite and a fake Public HTTP adapter. No new paid service, signed APK, worker, order or bank transfer has been created.

## Rollout considerations

After successful PR and merged-main GitHub tests, independently test an owner login and correct linked Public account in the installed Android client, review provider data permission/response contract, and obtain explicit approval for the first real portfolio read. The solo flag can then be enabled without changing other flags, using merge-only Render environment updates. For rollback, set **only the solo flag** back to false, retaining all existing owner/member invitations, user records, Public credentials, key custody and the v0.2.74 backup. Verify actual backend provider response and account scope before treating portfolio as production-ready.

Do not re-run signed Android builds unless Android source actually changes or a physical APK update is requested. Keep free GitHub CI and commit README, CHANGELOG.md and DEVELOPMENT_CONTINUITY.md at tested milestones.
