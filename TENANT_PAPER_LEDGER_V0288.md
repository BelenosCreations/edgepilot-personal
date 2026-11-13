# v0.2.88 — Dormant tenant-isolated paper accounting

This is a **source/test-only** development checkpoint. The module `backend/engine/tenant_paper_ledger.py` is intentionally **not imported by app.py**, and its `prepare(path)` migration is **not** run in the production tenant database. There is no paper-trading HTTP route, Android control, background job, Public order, bank access, or paid service.

## Explicit internal-only construction

A future trusted service must derive `principal_user_id` from a verified authenticated EdgePilot identity session, look up the current account through the existing tenant schema, and validate provider rights from an authoritative adapter. Do not accept user-supplied UUIDs or a caller's assertion that market rights are verified. This prototype consumes **synthetic provider evidence** in tests only. Before any real-user rollout, require data license review and server-controlled UTC time and a verified fee model.

A separate `open_wallet` operation seeds synthetic paper dollars explicitly. It never uses or mutates real Public funds. Repeated initialization with the same seed is idempotent; a different seed is refused. Reallocation/reset needs a future, separately authorized process that keeps full history.

`record_paper_fill` stores a hypothetical instantaneous BUY at observed ask plus explicit adverse slippage/fees (total rounded **up**) or a long-only SELL at observed bid less those costs (proceeds rounded **down**). These are simulated assumptions, **not actual broker fills or guaranteed fillability**. Persistent paper fills also require explicit verified provider caching rights, since the paper event retains observation and source/quote metadata. It refuses unknown/stale/closed/unlicensed evidence, negative or nonfinite quantities, unavailable cash, exceeding the synthetic initial-cash protected 0–99% budget, exceeding the spend cap/per-trade cap, unsupported prediction-market contracts, and short selling. The synthetic seed and existing committed position cost basis define a conservative fixed baseline budget; it does not pretend to know mark-to-market equity or buying power.

All wallet, position, and request/event rows use composite `(user_id, account_id)` foreign keys. Every operation checks active user, account and unrevoked connection in the private tenant DB; a legacy global-token identity cannot access these functions. SQLite `BEGIN IMMEDIATE` serializes account state changes; request UUIDs and SHA-256 request digests enforce exactly-once local effects on identical retries and reject conflicting retries. No actual Public fill, broker order, credential or finance API data is imported. Synthetic realized P&L is based only on the assumed scenario price and conservatively allocated cost basis; there is no unrealized/portfolio performance claim.

## Acceptance gates before connecting to the owner UI

1. Verify PR CI, merged-main CI and a disposable two-user/two-account test database with idempotency, cash and cross-account failures. No production migration or runtime flag.
2. Validate that the existing encrypted tenant backup and restore process can safely include *new* paper tables once enabled, without modifying or exposing current private data. A tested restore must precede production activation.
3. Design a separately authorized scoped API path behind the identity cookie and CSRF protections, with server-side rate limiting and trusted data-provider provenance, not client-authored rights assertions.
4. Reconcile an owner-selected Public account snapshot separately; never conflate paper portfolio value, actual Public cash, broker orders or investment advice.
5. Only after real-device acceptance may the owner use clearly labelled paper controls. **Real trading, autonomous orders and bank transfers remain OFF** regardless of paper-mode readiness.

## Tests and roll-forward

`python -m unittest backend/tests/test_tenant_paper_ledger_v0288.py` from the project root may require the appropriate backend import path; CI runs `python -m unittest discover -s tests -v` from `backend/`. Tests use local temp SQLite and synthetic identities and do not call external providers. This new schema is additive and dormant, so there is no production rollback/migration until a future explicit activation milestone.
