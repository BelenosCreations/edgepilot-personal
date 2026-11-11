# EdgePilot v0.2.52 — Verified Free Render staging service

## Status and evidence (2026-11-10 America/New_York)

The owner approved a Render Free **staging** instance, conditional on
reviewing workspace included usage and not creating paid capacity.
The owner supplied a Render Billing screenshot on November 10, 2026
showing Hobby workspace plan, payment method already on file,
approximately 0/750 Free instance hours, 45 MB of workspace outbound
bandwidth, 7 included pipeline minutes, 1 existing custom domain,
1 existing service, and $0.57 current unbilled existing-service
charges. These are a point-in-time bill snapshot, not a cost guarantee.

A separate staging service was created in the confirmed
Belenos's Render workspace:

- Service: `edgepilot-passkey-staging`
- Render service ID: `srv-dbpupj2jnfac73ehv1v0`
- Workspace ID: `tea-dbocidc9v7es73est240`
- Free service URL: `https://edgepilot-passkey-staging.onrender.com`
- Render dashboard: `https://dashboard.render.com/web/srv-dbpupj2jnfac73ehv1v0`
- Deploy ID: `dep-dbpupjajnfac73ehv2og`
- Source: `main` GitHub commit `2a53250924c90d350a58ad84f966e08e521b9185`
- Region: Ohio; runtime: Docker; build context: `backend`;
  Dockerfile: `backend/Dockerfile`
- **Compute plan is Free.** Auto-deploy is **off**, no persistent
  disk, and no paid add-on was created.
- Render service metadata reported `status=live` for the initial
  deployment. Events recorded successful build and deployment,
  and application logs show gunicorn listening on port 10000 and
  Render's live-service message. This verifies backend startup.
  It is **not** yet a verified end-to-end custom-domain HTTPS
  or hardware passkey test.

The production service `edgepilot-private-h9tl`
(`srv-dbocnb3m8hqs7386trvg`) remains separate with its own
Starter compute/disk; it was **not** modified by this staging creation.
No production token, Public secret, OpenAI key, signing private
key, encryption key, database or live worker was copied.

## Confirmed independent public APK certificate

The previously signed `EdgePilot-v0.19.17-private-stable-signed-test`
GitHub Actions artifact from the successful build `42888113943`
was recovered privately. The APK v2 signing block certificate was
independently decoded to verify the public SHA-256 digest:

`B1:D5:C5:60:11:10:D4:B3:BF:5A:22:D4:4A:F5:6E:A7:BA:8C:24:F0:46:FA:DB:27:95:2A:EA:18:E7:EC:D3:3F`

That is **public certificate metadata only**, not a password or
signing key. The new staging Render instance has this actual fingerprint
as its `EDGE_ANDROID_CERT_SHA256`. Its Android association configuration
claims `com.edgepilot.mobile.staging`, not the production package.
The staging-signed APK has **not** been built yet; signed staging APK
verification and Android OS link association remain required.

## Configuration isolation

Startup preflight requires all of the following:

- `EDGE_ISOLATED_STAGING=true`
- `EDGE_DB_PATH=/tmp/edgepilot-staging.db`
- Distinct fixed WebAuthn RP ID
  `staging-edgepilot.belenoscreations.biz`
  and origin `https://staging-edgepilot.belenoscreations.biz`
- `EDGE_ANDROID_ASSOCIATION_PACKAGE=com.edgepilot.mobile.staging`
- Tenant schema, identity, invitation signup and passkey routes enabled
  **only** in this isolated staging process
- Owner login token, production Public and encryption credentials
  **absent**; live order, worker, per-user Public vault/read-only,
  account reads, monitoring, watchlist editing flags **false**

Because the RP ID and origin are pinned to the proposed custom domain,
the Render `onrender.com` URL is a transport/liveness address and
cannot act as a successful browser/WebView passkey origin; a 404
association for that hostname is correct. Startup and successful
Render deploy are not proof of association or biometric login.

## Necessary owner-controlled one-time domain action

The connected Render integration cannot add a service custom domain,
and this project currently has no connected Squarespace DNS control.
The owner manages the `belenoscreations.biz` DNS in Squarespace
(the domain was previously moved from Google Domains).

1. Open the **staging** service's Render dashboard above. Under
   **Settings → Custom Domains → Add Custom Domain**, enter exactly
   `staging-edgepilot.belenoscreations.biz`. Do not add a wildcard
   or attach the existing production `edgepilot.belenoscreations.biz`.
2. Open Squarespace Domains → `belenoscreations.biz` →
   DNS → DNS Settings → Custom Records → Add.
   Add only one CNAME:
   - **Type:** CNAME
   - **Host / Name:** `staging-edgepilot`
   - **Value / Data / Points to:** `edgepilot-passkey-staging.onrender.com`
   - **TTL:** default or provider-supported short TTL.
   Do **not** delete Squarespace defaults, apex records, existing
   `edgepilot` CNAME, `www` records, email MX or other DNS.
   Check for conflicting record only under the exact new hostname.
3. Return to Render staging Settings → Custom Domains and click
   **Verify**. Wait for verified HTTPS and valid managed TLS;
   then load `https://staging-edgepilot.belenoscreations.biz/healthz`
   and `/.well-known/assetlinks.json`. The latter must serve
   only the staging package and independently verified fingerprint.
4. Confirm the existing production URL and association still work.
   Do not send production passwords, personal Public keys or app
   owner tokens to the staging site.

For the Hobby workspace, Render documents **two included custom
domains**; the billing screenshot showed one in use, so this single
staging subdomain is expected to use the other included slot.
Additional domains after that cost extra: verify current usage
in Billing before adding any others.

Sources: https://render.com/docs/custom-domains and
https://render.com/docs/configure-other-dns .

## After domain verification (still not done)

1. Run the *manual-only* staging signed GitHub Actions workflow on
   `main` with the verified staging hostname; verify the resulting
   APK package, signature and embedded host. It should install
   alongside the existing production app.
2. The Free instance has **no shell access or one-off jobs**.
   The existing invitation-only registration mechanism issues
   tokens only through a trusted operator process and has no
   anonymous HTTP issuance route. No staging invitations have
   yet been issued. Implement and independently test a narrowly
   scoped **staging-only operator provisioning path** before
   claiming two-user signup is usable, or migrate to an
   operator-accessible isolated durable staging service under
   separate cost approval. Do not remove invitation checks.
3. Verify two **different real Android phones**, two independent
   EdgePilot member identities, Android Credential Manager passkey
   registrations and logins, CSRF/session revocation and isolation.
4. Any actual Public credential/account work remains behind a
   separate provider-authorization/security and **persistent
   isolated storage** gate. Free SQLite can disappear after
   15 minutes idle, any redeploy or restart. This first service is
   only for disposable synthetic identity ceremonies.
5. Do not enable order placement, hands-off live trades or fund
   transfers as part of staging.

## Costs and next review

No new fixed monthly instance, disk, domain or paid API service was
purchased in this milestone. The existing $0.57 and projected
monthly amount shown in the user's screenshot belonged to the
workspace's existing resources and are not staging charges.
Because the workspace has a payment method, **bandwidth and
build-minute overages can still generate charges**, notwithstanding
the Free compute designation. Monitor workspace usage before
future builds; do not auto-deploy, add keep-alive jobs, attach a
paid disk, enable paid providers, or exceed allowance without
explicit authorization. See
https://render.com/docs/free .

The v0.2.51 proposal remains a historical **non-deployable
pre-creation artifact**; this file records its subsequently
authorized deployment and real public certificate verification.
