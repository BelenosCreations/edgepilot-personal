# v0.2.67 — Dormant permanent account-scoped read-only pilot gate

The permanent existing-paid-disk tenant selector previously denied ALL
account-scoped Public/portfolio gates even after an independent owner
was enrolled. This would have prevented validating two separate real
users' read-only Public accounts during a controlled production pilot.

## New fail-closed pilot policy

A separate default-off EDGE_PERMANENT_READONLY_PILOT_ENABLED flag may
permit individually gated account scope, encrypted user-owned Public
credential vault, allowlisted Public HTTPS read-only adapter, dormant
monitor preview and owner-scoped watchlist editing on the independently
prepared /data/edgepilot-tenants.db database. This flag **alone does not
enable any feature or provider network access**.

When the pilot flag is on, startup requires the already-paid service's
exact paths, private existing tenant database with one enrolled active
owner Argon2id password identity, separately enabled identity sessions,
stable Fernet EDGE_CREDENTIAL_KEY if the vault is requested, disabled
global worker/order execution, and no staging mode. Public READONLY
requires both vault and account-read gates. Watchlist editing requires
dormant monitor preview, which itself requires account-read isolation.
Signup/invitations cannot activate while legacy owner APIs coexist.

## Operator control and future acceptance

Do not enable the pilot on Render until:
- The v0.2.63 tenant DB initializer has actually been executed, followed
  by v0.2.62/v0.2.65 read-only integrity and identity readiness checks.
- The original owner has independently enrolled using v0.2.60, signed
  in and proved account recovery on a physical device.
- The private offsite encrypted backup, vault Fernet recovery and legacy
  owner-token recovery have been independently tested.
- Each user's Public key has explicit authorization and is entered by
  that user; two actual separate Android devices and Public owners are
  available for the acceptance test.

The initial pilot can retain the legacy owner's existing API for
reversible transition while independent tenant identity, credential
and read-only account routes remain separately session-scoped.
After successful two-device verified acceptance, tenant-only mode may
be independently considered, but v0.2.66 first-owner guard is mandatory.
Public broker order submission, autonomous live trading, global workers,
bank deposits/withdrawals and transfers remain disabled.

Synthetic tests with two independent identity sessions verify no key
cross-read, ciphertext-at-rest, unchanged legacy owner credential and
zero provider network requests. They DO NOT prove live Public auth,
real Android passkeys or real two-device ownership.

No new paid service, Render environment flag or storage volume is
created by this code merge. Manual production activation remains a
separate operator decision.
