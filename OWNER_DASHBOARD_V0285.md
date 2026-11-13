# v0.2.85 — One-user identity-backed dashboard (read-only, no new broker permission)

The owner explicitly wanted EdgePilot development to continue through the next useful milestone instead of stopping automatically at each green GitHub run. The approved near-term goal remains **one fully functioning user**. The earlier multi-user identity model, private invitation controls, separate encrypted Public connections and backup/recovery design remain intact for later real-world testing; no second member has been enrolled.

## Why a separate owner home

The preexisting root (`/`) is the legacy, independently authenticated global-token dashboard. The newer (`/account`) identity login and read-only Public linkage are already functioning for one real owner. Combining the two by sharing the legacy global token or credentials with tenant identity sessions would undermine account isolation. This milestone therefore introduces **`/owner` as a new read-only independent owner home** without changing or removing the old root dashboard or its login.

The new route is an unprivileged HTML shell. All data continues to require the existing same-origin HttpOnly EdgePilot identity cookie. JavaScript verifies the authenticated identity is an **owner**, calls the account-scoped `GET /api/identity/accounts`, and only offers access if the server returns `soloOwnerPortfolioAvailable=true` and a linked account UUID. The existing server-side solo-owner database check runs before and after every provider request, failing closed when another member is enrolled. The page cannot see another member's Public credentials or use the legacy global selection.

## Owner workflow

1. Open `/owner`, or tap **My read-only dashboard** from `/account` or the legacy root's introductory sign-in section.
2. The owner dashboard checks the independent identity session and lists verified Public accounts. If the login is absent, expired or is a member account, it shows a nonprivileged sign-in link to `/account`. It cannot initiate registration or a broker trade.
3. Only a deliberate **Retrieve read-only snapshot** tap invokes the already active `/api/identity/public/read/accounts/{scoped_uuid}/portfolio` endpoint. Sign-in and account refresh never fetch balances.
4. The backend validates the current user, account ownership, encrypted broker credentials, provider account ID matching and the sole-owner pilot both before and after Public's request. The browser also validates the full returned snapshot before showing total account value, position count and per-symbol quantities and current value.
5. This displays one **selected brokerage account** only; it is not an all-accounts total, account performance, profit/loss, guaranteed real-time quote or trading decision. Its retrieval time is the device's local time, not a broker market timestamp.
6. A changed account selection, sign-out, browser-page exit, failed/invalid request or replacement of saved linked accounts clears prior financial values from the page. The browser does not persist the snapshot, owner tokens or API secrets in storage, never runs timers or scheduled polling, and makes no orders/transfers.

## Existing production environment remains unchanged

Public-reported account value and zero reported positions were demonstrated by the owner in the previous single-owner `/account` experience. The screenshot does **not** by itself establish that the value reconciles against the user's Public app. There is no new paid service and no new environment setting for `/owner`; it relies entirely on the previously authorized read-only pilot. The family invitation configuration remains as previously approved, but issuance and two-device testing are deferred.

No automatic chart/portfolio history, crypto/prediction-market price feed, profit/loss, AI recommendations, scanning worker, broker order, bank transfer, or paper execution is implied by this milestone. Those require separate reliable sources and explicit gates. Continue toward researched market-data provenance and fully simulated paper/risk features only after this owner dashboard is tested.

## Test and roll-forward boundary

Synthetic/static regressions verify server route separation, owner-only identity/account checks, absence of legacy API token fallback, manual-only provider calls, account ID matching, safe rendering and no persistent financial state, timer or execution endpoints. Existing unit and Flask route tests independently guard the tenant account isolation and read-only provider adapter. Use GitHub PR and merged-main CI; do not merge on a failed suite. The paid Render service already auto-deploys verified merges to `main`, with no new host or disk migration.

Owner acceptance: sign in through `/account`, visit `/owner`, deliberately retrieve your own Public snapshot, verify the account selector and safe empty-position display, and compare the total value against the official Public app without publishing any account identifier, credential, screenshot with private data, or backup secret. Continue programming in the same branch until that milestone is verified before issuing a new family invitation.
