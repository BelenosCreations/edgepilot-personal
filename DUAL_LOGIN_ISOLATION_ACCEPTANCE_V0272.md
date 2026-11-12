# v0.2.72 — Accepted HTTPS owner-login and dual-auth isolation regression

The user completed real Android HTTPS sign-in to the new private
`Belenos-Owner` login, confirmed the secure identity session banner,
then confirmed sign-out and original legacy login work. This is
**operator-reported real-device acceptance**, not a claim that the
assistant independently controlled the Android browser.

An encrypted tenant-owner database archive, including Argon2id identity
hash, had already been authenticated through a temporary restore,
SHA-256 compared after copying to Android, and uploaded to the user's
private Google Drive backup folder. Drive-side redownload checksum
remains unverified.

**Integration regression:** Added a disposable two-database Flask
integration test reproducing the approved live auth-only feature gate
combination. It creates two synthetic identity users on an isolated
private tenant database and a separate synthetic legacy owner token
on the old database. Each can authenticate without the other's
cookie; a tenant cookie cannot access legacy dashboard/broker/
automation APIs, and a legacy cookie cannot access tenant identity
sessions. Identity registrations, passkeys and Public connection/
read-only/account routes must remain disabled. CSRF-bound sign-out of
either login must leave the other user's session unaffected; the
original broker ciphertext and legacy schema must remain unchanged.
**No real Public API requests or real accounts are used.**

Deployment after merged CI adds regression tests/documentation only;
it does NOT enable signup, invitations, Public accounts, tenant
watchlists, passkeys, 15-minute trades, orders, bank transfers or
new hosting resources. The `EDGE_PERMANENT_TENANTS_ONLY` switch
stays false to preserve original owner login. Worker stays disabled.

The user-approved stage ends with a verified independent owner login,
not yet separate Public accounts on two real physical devices.
A subsequent separate decision is required before turning on real
tenant Public connection storage/read-only features, adding a new
real member, or permanently retiring the old token login.
