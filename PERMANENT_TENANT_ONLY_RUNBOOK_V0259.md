# v0.2.59 — Permanent tenant-only routing and pinned Android origin (dormant)

**Purpose:** Prepare retirement of the old single-owner HTTP API after
the operator has fully recovered/migrated the owner's identity and data.
This is opt-in safety plumbing, not automatic migration or activation.

## Behavior with no new environment flags

Nothing changes. Production continues to use the existing owner dashboard
and API. The earlier v0.2.58 tenant split is also independently opt-in.
No account, password, passkey, credential or bank/trading setting is moved.

## Optional, jointly gated permanent identity mode

Set `EDGE_PERMANENT_TENANTS_ONLY=true` only **after** separately verifying:

- Existing paid service, owner file, private tenant file and recovery.
- Tenant schema and identity were explicitly prepared on the same paid disk.
- The owner has independently enrolled in EdgePilot and can access their
  own new identity with a tested recovery method.
- Other users cannot reach owner data; no data from old owner rows was
  ambiguously assigned to a tenant.
- `EDGE_AUTOMATION_WORKER_ENABLED=false` and
  `ENABLE_LIVE_ORDERS=false`; no other live trading/bank transfers.
- The old owner API token is preserved in secure custody until final
  recovery, but no longer accepted by any legacy HTTP endpoint.
- Root landing redirects to `/account`; all non-identity
  `/api/*` endpoints return 404, including owner login, session,
  global strategy/settings, broker and worker/order APIs. `/healthz`
  stays unauthenticated and deliberately returns only simple liveness.
- Default-off identity gates remain independent; this switch never
  creates members, invites, grants Public access or starts monitoring.

## Optional permanent signed-app WebAuthn origin

`EDGE_PERMANENT_ANDROID_PASSKEY_ORIGIN_ENABLED=true` requires the above
tenant-only mode **and** independently enabled tenant passkeys, fixed
`EDGE_WEBAUTHN_RP_ID=edgepilot.belenoscreations.biz`,
`EDGE_WEBAUTHN_ORIGIN=https://edgepilot.belenoscreations.biz`,
no staging package override, and the exact verified *public* signing
certificate SHA-256 in `EDGE_ANDROID_CERT_SHA256`.
The server then accepts only the exact pinned HTTPS origin or derived
Android signed-app origin. This does not add arbitrary origins, permit
client-selected trust, or relax cryptographic challenge/signature checks.
It never activates itself merely because a public Digital Asset Links
file exists.

Tests prove policy denies mismatched RP, cert, host, data path or disabled
identity, plus real Flask startup rejects owner routes while preserving
the synthetic original owner credential. Existing v0.2.55 cryptographic
WebAuthn tests remain the verifier foundation. Physical production APK
passkeys, two independent devices and recovery remain unverified.

## Deployment / rollback

Keep both switches **false/unset** until a separately reviewed cutover.
A safe rollback first restores the former environment and compatible
app revision; it must never overwrite a tenant DB with old owner data.
No additional Render resource or payment, live orders or transfers.
