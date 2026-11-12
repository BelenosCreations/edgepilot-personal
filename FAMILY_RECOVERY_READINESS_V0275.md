# v0.2.75 — Independent private-family recovery readiness (dormant)

This development-only milestone prepares EdgePilot for the previously approved objective of up to ten independent private family accounts on the **same existing paid Render service**. It does not enroll a second user or enable trading, Public balances, monitoring, bank transfers, autonomous execution, a new service or a migration.

## Why this is needed

The current verified v0.2.74 linked-owner backup is intentionally limited to **exactly one** independently enrolled owner. It cannot be treated as a complete recovery strategy after other members have separate credentials, account links, sessions and data. The secure next step is to make any future family-level recovery capability prove tenant-account separation first, while the actual multiple-member backup writer remains unimplemented.

## Safety boundary

`backend/engine/family_recovery_readiness.py` is an **unwired, operator-only, read-only** diagnostic. It has no HTTP routes, startup hooks, cron tasks, workers, scheduled jobs, cloud provider calls or archive writes. It requires an exact opt-in environment flag `EDGE_FAMILY_RECOVERY_INSPECT_ALLOWED=true` supplied only to an explicit caller, a verified paired private legacy and tenant SQLite database, and the same discovery-only, no-orders, no-transfers feature profile as the current owner Public pilot. Nothing sets this flag automatically.

The audit reads only aggregate member/session/account counts while validating the underlying private records: exactly one active enrolled owner, no unpaired identity, private separate databases, SQLite integrity and foreign keys, a maximum of ten members, decryptable Fernet-encrypted Public connections, valid owner/connection/account associations, and **no shared identical Public API secret across two different users**. The secret comparison remains internal; only one-way digests are retained for comparison and neither digest nor plaintext is returned. All refusal reasons are fixed, non-secret strings. Revoked ciphertext must also remain decryptable for full future recovery.

## Acceptance limits

Synthetic tests create two distinct independent user identities and distinct encrypted dummy Public keys, then verify that the audit reports only nonsecret counts, never mutates either SQLite file, never produces an encrypted archive, rejects shared keys, unpaired member identities, tampered ciphertext, world-readable tenant storage, invalid vault key, and any signup, invitation, worker or order flag. One existing owner can still pass inspection, but the report explicitly says two independently linked users have **not** yet been proven in storage.

**Not yet delivered:** an encrypted multi-member restore archive, recovery under a lost credential vault key, password recovery for a second user, invite or registration activation, real second Public connection, second physical Android device, a paid Render deployment of this audit, or any live brokerage action.

The owner-verified v0.2.74 off-service linked-account archive and all older backups remain intact. Do not replace it with a preflight report. The next development milestone should implement an encrypted **multi-member** archive and synthetic restore proof, then require separately reviewed operator acceptance before any real second user is enrolled.
