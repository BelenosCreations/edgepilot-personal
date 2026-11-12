# v0.2.71 — Controlled HTTPS owner login on existing paid Render

**Approval and scope.** The owner approved activating an independent
HTTPS identity-login pathway *only* after secure first-owner enrollment,
Argon2id password proof and an off-service authenticated encrypted
tenant backup. On the existing paid Render Starter instance,
environment variables were merged rather than replaced.

**Verified deployment:** `dep-dbqhl6ajnfac738nlst0` — live on source
commit `9381b3fec91ef6d8c467ffaf4daeb7b033d8d05b`. This confirms
Render deployed the authentication-enabled service; it does NOT
independently establish a real-device login.

**Live configuration:**
- Original legacy DB remains `/data/edgepilot.db`; separate existing
  owner tenant identity DB is `/data/edgepilot-tenants.db`.
- `EDGE_SHARED_TENANT_DB_PREPARE=true`,
  `EDGE_TENANT_SCHEMA_PREPARE=true`, `EDGE_IDENTITY_AUTH_ENABLED=true`.
- `EDGE_PERMANENT_TENANTS_ONLY=false` preserves existing
  `/api/login` and its separate legacy session.
- `EDGE_PERMANENT_READONLY_PILOT_ENABLED=false` and all tenant Public
  connection/read, account, monitor, registration, invitations and
  passkey gates remain off.
- `EDGE_AUTOMATION_WORKER_ENABLED=false` and
  `ENABLE_LIVE_ORDERS=false`, with no transfers or bank authority.

**User acceptance test — physical Android browser, no credentials shared:**
1. Open the **Render-owned** HTTPS account page:
   `https://edgepilot-private-h9tl.onrender.com/account`.
   Confirm the domain and lock icon before entering credentials.
2. Choose **Sign in**, not **Create account**, and enter the privately
   selected login `Belenos-Owner` and unique owner password. Never
   paste/send the password to ChatGPT, an issue, screenshot or log.
3. Confirm the page displays a secure session status and
   `Welcome, Belenos-Owner`. Disabled options (e.g., passkeys,
   invitations, brokerage reads) are expected to be unavailable.
4. Sign out using the account page. Reload, confirm the session is
   no longer authenticated. Do not use the same cookie as a
   substitute for an actual separate-device test.
5. Independently test the *existing legacy login* on the personal
   dashboard remains usable, without disclosing the token.
6. On any unexpected denial or cross-account data, STOP. Do not
   repeatedly guess passwords; Argon2id authentication is rate
   limited. Report only sanitized error message/screenshot.

**Rollback** (requires an actual issue or the owner's decision):
Set only `EDGE_IDENTITY_AUTH_ENABLED=false` in the *existing*
Render service, using merge/upsert environment update, and verify
the subsequent deployment is live. Keep separate tenant DB and
recovery material untouched. Never rollback by deleting or
replacing the full Render environment, legacy DB, token or vault key.

**Not approved:** Public credential migration, new member enrollment,
real-money orders, automated trades, bank transfers, permanent
tenant-only retirement, production passkeys or new paid services.
