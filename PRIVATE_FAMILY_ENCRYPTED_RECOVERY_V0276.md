# v0.2.76 — Encrypted private-family recovery rehearsal (dormant)

EdgePilot's existing paid Render Starter backend and two independently isolated SQLite databases remain unchanged. This milestone prepares a **distinct** future recovery archive for two to ten separate, individually authenticated family members, without replacing the owner-only v0.2.74 archive or enabling additional production users.

## What the code does

The engine-only `backend/engine/permanent_family_archive.py` is **not imported by Flask, Android, a worker or any deployment start script**. It requires a deliberate exact nonsecret operator approval and both opt-in flags `EDGE_FAMILY_RECOVERY_INSPECT_ALLOWED=true` and `EDGE_FAMILY_ARCHIVE_ALLOWED=true`. All v0.2.75 discovery-only, no-orders, no-bank-transfer, no-signup and no-invite safety checks remain mandatory. There is no operator CLI or default activation.

On fake data in tests, the utility checks the existing paired private legacy and tenant SQLite files with the v0.2.75 audit, requires at least two active independent member identities, then copies only the tenant database with the SQLite backup API into private RAM. It clears browser session hashes, login failure/rate-limit state, pending passkey challenges, and **unused invitation token hashes** from the RAM snapshot only. The production source and original legacy owner data remain read-only. Consumed invitation history and registered passkey credentials are preserved.

The new archive format `EDGEPILOT-TENANT-FAMILY-BK1` is distinct from the earlier owner-only and linked-owner archives. AES-256-GCM authenticates the snapshot with the separately held offline backup key. A second, isolated RAM restoration verifies tenant schema, one active owner, identity pairing, decrypted per-member Fernet Public credentials, no API secret shared across members, account/connection isolation and zero restored live sessions, pending invitations or transient challenges. The archive is created as a private, no-overwrite `.epbk` file **only under the trusted RAM directory** and returns a SHA-256 digest and sanitized counts.

## Recovery limits

The encrypted family archive still depends on BOTH the archive recovery key and the original Fernet `EDGE_CREDENTIAL_KEY` to recover broker ciphertext. A verified private RAM test is **not** a disaster-recovery service, off-Render copy, real account recovery, live multiuser acceptance or permission to migrate/restore over production data. `off_service_copy_verified` is deliberately false until an operator independently transfers, downloads and checksum-verifies a specific archive.

At present production has only one independently enrolled owner: this tool **must reject** that environment. It is future-facing only. Full deployment, owner-approved separate member enrollment, two physical phones with their own Public connections, recovery of credentials after lost infrastructure, and operational restore playbook remain future gates. No new paid service, Public portfolio balance request, autonomous trading, real order, transfer or background worker is authorized.

## Regression coverage

Synthetic unit tests use two independently authenticated users with distinct encrypted fake Public keys, linked fake brokerage accounts, active fake sessions, login-failure rows, pending fake passkey challenge, pending and consumed invitations. Tests verify that source DB bytes stay unchanged, archive ciphertext contains no plaintext fake secrets or IDs, archive SHA-256 matches, isolated restore clears only transient credentials, and that wrong AES key, tampered ciphertext, shared Public API key, missing second user, unsafe permissions, pre-existing target archive, orders, invites and worker gates fail closed. GitHub PR and merged-main CI must pass before this code is considered part of the accepted development checkpoint.
