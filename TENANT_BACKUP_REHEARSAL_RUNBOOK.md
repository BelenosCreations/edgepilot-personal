# EdgePilot v0.2.39 — Encrypted backup/restore rehearsal (synthetic only)

## Scope and guarantee

This stage validates backup-restore consistency for two independent EdgePilot
identities in an **isolated Linux tmpfs fixture**. It is deliberately NOT a
production backup or recovery mechanism, and it cannot be pointed at the
actual Render database or the owner's Public credentials.

The new module `backend/engine/tenant_backup_rehearsal.py` provides:
- `sealed_snapshot(path, archive_key)`: take a consistent SQLite backup
  exclusively into verified `/dev/shm` tmpfs, validate required tenant
  tables, SQLite integrity, foreign keys and inactive runtime; encrypt the
  entire image with a caller-held Fernet backup key distinct from the
  credential-vault key; return only sealed bytes in process memory.
- `restore_sealed_fixture(token, archive_key, new_path)`: authenticate
  the sealed image before creating any plaintext file, reject incorrect
  keys or tampering, write exclusively to a NEW mode-0600 file in verified
  `/dev/shm`, verify SQLite and cross-table integrity, and invalidate
  ALL archived sessions, pending passkey challenges, unredeemed invitation
  codes and stale worker leases; quarantine every restored broker connection
  and account to prevent older snapshots from resurrecting revoked keys.
- A 16-MiB maximum fixture size; no production data, online broker
  requests, worker activation, trades, transfers or HTTP integration.

Only read this code as a test contract. It should never be invoked by the
legacy worker, Flask app, Render deployment or a production backup script.
A production backup strategy needs durable encryption, authenticated key
rotation/recovery, offsite retention, owner deletion and restoration policy,
incremental/backfill consistency, WAL handling, disaster testing, and
platform-wide operational signoff — none are supplied here.

## Isolation requirements

The source must already be a valid, detached SQLite regular file on the
real Linux `/dev/shm` tmpfs mount, without an active WAL sidecar. Source
and restore locations outside verified tmpfs are rejected. The restore
location must not exist, even as a symlink. Wrong keys, malformed or
tampered archive bytes, corrupted SQLite, missing expected tenant tables,
invalid foreign keys and active persisted runtime configuration all fail
closed. A failed restore must remove the newly created plaintext file.

A backup key is never recorded in the repository. Test cases use newly
generated synthetic encryption keys and fake provider account references.
No real Public credential is ever read, logged or exported.

Two distinct keys are used:
1. The archive key authenticates/decrypts the complete SQLite snapshot.
2. The existing Public credential-vault key decrypts individually encrypted
   fake credentials *within* the restored SQLite fixture.

A correct archive key alone must NOT be understood as proof that the
credential-vault encryption key is available after a disaster. Real
restoration requires independently protected and recoverable vault keys.

## Tested acceptance

Unit tests construct two synthetic users, two account bindings, encrypted
fake Public keys and distinct watchlists. They validate that restoration
preserves both accounts/settings and encrypted keys, while forcing both
users to authenticate again. Each user may access only their own restored
account. Old session cookies, pending sign-in challenges, invitations and
worker leases cannot be reused.

Negative tests cover archive tampering, missing/wrong archive key, existing
destination, path outside `/dev/shm`, forged SQLite payloads, active worker
leases and forbidden runtime state. GitHub CI executes these tests on Linux
with tmpfs support. Passing tests are **not** evidence that a real production
database or a two-device Public connection was restored.

## Further milestones

- Durable production-grade encrypted backups with explicit operator
  ownership, key custody, retention, offsite storage and recovery runbooks
- Per-tenant restore/deletion protocol and explicit disaster authorization
- Stable signed Android app and Digital Asset Links verification on two phones
- Per-tenant active worker, portfolio history and cache isolation
- Separate authentication recovery with verified proof of account ownership
- Real account read-only acceptance only after permitted provider access;
  live orders, autonomous trading, and bank transfers remain disabled

See DEVELOPMENT_CONTINUITY.md and MULTIUSER_PLATFORM_ACCEPTANCE.md.
