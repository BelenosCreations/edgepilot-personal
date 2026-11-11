# v0.2.69 — Mobile-friendly one-time owner bootstrap (still default-off)

The separate permanent tenant file was created by the operator on the existing
paid Render service and passed both v0.2.62 read-only legacy/tenant schema
checks and v0.2.65 first-owner readiness inspection at **zero members**.
The first subsequent v0.2.60 owner-bootstrap attempt displayed a generic
refusal after Android Termux SSH requested the password twice and a **hidden**
final approval phrase. The tool did NOT report success.

This release changes **only the private console UX**:

- The new owner password remains hidden in both entry prompts. If either
  entry is empty (such as an Android clipboard/Enter race), if they differ,
  or if length is outside 14–128 characters, the CLI prints a safe reason
  and immediately refuses without attempting a database write.
- The fixed nonsecret phrase `INITIALIZE FIRST EDGEPILOT OWNER` is now
  entered with a **visible** standard prompt, just like the successful
  earlier tenant storage initialization. It is checked exactly. The phrase
  remains required; it is never added to shell arguments or logs.
- The pre-existing engine's fixed nonsecret refusal reason (such as
  unsafe file, existing owner, disabled identity gate) is displayed
  without showing username, password, SQL or API credentials.
- The engine's atomic one-owner transaction and all environmental checks
  remain unchanged. No automatic second attempt, login reset or public
  sign-up feature was added.

**Operator process:** First rerun the read-only owner readiness inspector.
If it still reports zero users, the operator may repeat the existing
trusted interactive bootstrap once with command-local opt-in:
`EDGE_OWNER_BOOTSTRAP_ALLOWED=true EDGE_SHARED_TENANT_DB_PREPARE=true
EDGE_TENANT_SCHEMA_PREPARE=true EDGE_TENANT_DB_PATH=/data/edgepilot-tenants.db
EDGE_IDENTITY_AUTH_ENABLED=true python3 tools/first_owner_bootstrap.py`.
Use a private password entered manually twice (hidden). Only then manually
type the fixed visible phrase and press Enter once. If any failure occurs,
stop and review the sanitized message and read-only owner readiness report.

**Successful owner identity creation is NOT production identity activation.**
It neither migrates the original Public account nor disables token login.
No new paid service, live trading, autonomous orders, worker restart or bank
movement. Independent login and recovery still need a separately gated,
real-device verification before changing production routing.
