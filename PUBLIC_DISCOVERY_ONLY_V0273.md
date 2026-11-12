# v0.2.73 — Private read-only Public account discovery, no portfolio/trades

**Approval:** The owner explicitly approved enabling limited read-only
Public connection and account discovery after the independent
`Belenos-Owner` password login, logout and original legacy login were
verified on physical Android.

**Scope and staged safety:** On the SAME EXISTING paid Render service,
the approved rollout enables per-identity encrypted Public secret
storage, provider-authorized account discovery and verified account
linkage. It deliberately does **not** enable account balances,
portfolio holdings, monitors, watchlists, registration, passkeys,
orders, automation workers, bank transfers, or legacy key migration.

The new `EDGE_TENANT_PUBLIC_DISCOVERY_ONLY=true` flag, used with the
older `EDGE_TENANT_PUBLIC_READONLY_ENABLED=true` adapter, explicitly
blocks every HTTP portfolio response even after linking and hides the
corresponding frontend button. The account-list API declares
`discoveryOnlyPilot=true`. The user may later approve portfolio
reads separately; do not quietly remove this flag.

**Verified active deployment — November 12, 2026 UTC.**
GitHub PR #95 and merged-main run 43150624623 both passed.
On the EXISTING paid Render Starter service, the owner-approved
merge-only flags below were deployed as
`dep-dbqjf4ec6qcc73fhamrg`, confirmed LIVE.
No new account key has been entered or tested in this turn.
Actual Public provider account discovery remains a user-driven
acceptance step.

**Required deployment flags (merge existing Render variables,
never replace):**

```text
EDGE_DB_PATH=/data/edgepilot.db
EDGE_TENANT_DB_PATH=/data/edgepilot-tenants.db
EDGE_SHARED_TENANT_DB_PREPARE=true
EDGE_TENANT_SCHEMA_PREPARE=true
EDGE_IDENTITY_AUTH_ENABLED=true
EDGE_PERMANENT_READONLY_PILOT_ENABLED=true
EDGE_TENANT_ACCOUNT_READS_ENABLED=true
EDGE_TENANT_PUBLIC_VAULT_ENABLED=true
EDGE_TENANT_PUBLIC_READONLY_ENABLED=true
EDGE_TENANT_PUBLIC_DISCOVERY_ONLY=true
EDGE_PERMANENT_TENANTS_ONLY=false
EDGE_AUTOMATION_WORKER_ENABLED=false
ENABLE_LIVE_ORDERS=false
EDGE_TENANT_SIGNUP_ENABLED=false
EDGE_PERMANENT_OWNER_INVITES_ENABLED=false
EDGE_TENANT_PASSKEYS_ENABLED=false
EDGE_TENANT_MONITOR_PREVIEW_ENABLED=false
EDGE_TENANT_WATCHLIST_EDIT_ENABLED=false
```

The existing stable `EDGE_CREDENTIAL_KEY` is mandatory for
per-identity Fernet encryption. It had previously been independently
verified as able to decrypt the original owner's saved Public
credential. **Never print, replace or paste the key into GitHub,
chat or logs.** Users supply their OWN provider-issued Public secret
directly through the verified EdgePilot HTTPS `/account` page.
The secret is never migrated from the old single-user credential
database, printed, or returned to the user. The owner must not submit
a Public login password or short-lived JWT in this field.

**Expected Android acceptance:**

1. Open `https://edgepilot-private-h9tl.onrender.com/account`
   after checking HTTPS and domain. Sign in as `Belenos-Owner`.
2. Find **Your Public connection**; enter your *own* Public API
   secret from Public's settings. Press **Save encrypted key**.
   Success only means safely stored, not verified yet.
3. Choose that encrypted connection and tap **Find my Public
   accounts**. EdgePilot sends a five-minute token exchange and
   a GET to the official Public account-list endpoint; it
   refuses every other provider endpoint during this stage.
4. A returned brokerage account is only authorized under the
   current owner's provider key. Selecting it links an internal
   account UUID to that authenticated EdgePilot identity.
5. Reopen `/account`; verify the linked account is visible
   and no portfolio/monitor/trading buttons are available.
   Sign out; original token-based dashboard should still work.
6. If Public rejects the secret or returns unavailable, report
   only the sanitized message or a screenshot **without**
   keys, account IDs or balances. Do not guess credentials
   repeatedly.

**Isolation evidence:** New integration tests use TWO synthetic
EdgePilot identities, two synthetic keys and a fake Public network
client with *only* account-auth and list URLs. An owner cannot
access another owner's connection, and encrypted ciphertext never
appears in the legacy DB. The old login cannot use tenant account
routes. Any portfolio URL is 404 while discovery-only is true.

**Rollback:** Merge (do not replace) these five vars on the same
Render service:
```text
EDGE_TENANT_PUBLIC_DISCOVERY_ONLY=false
EDGE_TENANT_PUBLIC_READONLY_ENABLED=false
EDGE_TENANT_PUBLIC_VAULT_ENABLED=false
EDGE_TENANT_ACCOUNT_READS_ENABLED=false
EDGE_PERMANENT_READONLY_PILOT_ENABLED=false
```
This disables independent Public features while preserving
`EDGE_IDENTITY_AUTH_ENABLED=true` and the old owner login.
Preserve tenant DB and encrypted keys as-is. No secret rotation,
deletion, new paid resources or worker activation.
