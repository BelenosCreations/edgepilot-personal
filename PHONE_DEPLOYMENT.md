# EdgePilot: setup from an Android phone (v0.19.10)

## Before you start
- Revoke the Public API secret exposed in any screenshot. Create a replacement; never share it in chat or commit it to Git.
- Install Chrome. Create your own GitHub and Render accounts. Choose a strong, unique EdgePilot app token of at least 32 random characters and save it in a password manager.
- The ZIP is source code, **not an APK**. Hosting costs can apply; check Render's displayed cost before accepting. Persistent disk is intentional for SQLite.

## Publish private source (no credentials)
1. Extract the ZIP on your phone. Its root is the `edgepilot_personal_v01910` folder.
2. Create a **private** GitHub repository. Commit the contents of the folder into the repository **root**, preserving `backend/`, `render.yaml`, `README.md`, etc. You may need a mobile Git client or terminal to upload folders recursively; the standard GitHub browser may not accept a ZIP as a ready-to-deploy repository.
3. Confirm `.env`, API tokens, `*.db`, and other secrets are not present. The included `.env.example` contains placeholders only.

## Deploy the backend and PWA with Render
4. Sign in to Render in your phone browser. Connect your GitHub repository, then select the repository's Blueprint (`render.yaml`). Review the proposed paid plan and persistent disk.
5. Supply these **private environment variables** through Render's secure configuration, not GitHub:
   - `PUBLIC_API_SECRET`: your newly rotated Public personal API secret.
   - `EDGE_APP_TOKEN`: your unique random 32+ character app access token (different from the Public key).
   - `EDGE_DB_PATH`: `/data/edgepilot.db` (already set by Blueprint).
   - `ENABLE_LIVE_ORDERS`: `false` (already set; real orders disabled in code regardless).
   - `OPENAI_API_KEY`: optional; leave unset for initial read-only testing.
6. Deploy. Confirm `/healthz` responds `{"ok":true}` and the HTTPS page loads. This health response contains no account data.
7. In Chrome open your Render HTTPS address. The Backend URL field should already contain the origin. Enter **only the EdgePilot app access token** in the app's Connect screen. Never enter the Public API secret in a browser field.
8. On the Overview screen, choose **Test Public connection**. If accounts were found but none selected, go to **Settings → Risk settings → Fetch my accounts → choose your brokerage account → Save settings** and repeat the test. Do not select the wrong account if you have several Public account types.
9. Once the account and portfolio show verified, compare balances, buying power, and holdings against Public directly. If anything differs, keep trading disabled and diagnose the mismatch.
10. Chrome menu → **Add to Home screen** / **Install app**. Keep your hosting and credentials private.

## Acceptance criteria for this release
- `GET /healthz` works without secrets and leaks no financial data.
- An invalid EdgePilot app token receives 401 from protected `/api` endpoints.
- Missing Public API secret gives `not_configured`; a valid secret lists accounts; selected valid account confirms portfolio access.
- Public key is never sent to the browser, committed, or displayed by the diagnostic.
- Attempts to place a real buy/sell order fail closed, even if preferences say autonomous.

## Cautions
The Public API secret itself can carry trading permissions; the *app* is read-only at this stage. Current authentication uses a single shared token and requires a trusted HTTPS/private access gateway for serious financial usage. Render's persistent disk supports one service instance; scale-out and automatic trading infrastructure are future tasks. Do not use this release for real-money execution. The source has not been authenticated with your brokerage account during development.
