# Offline fractional paper-ledger recovery

EdgePilot v0.2.108 rehearses recovery of the v0.2.106 synthetic Decimal fixture.
All SQLite and plaintext operations use marked, private 0600 files in verified
Linux tmpfs. The existing v0.2.107 session- and CSRF-authenticated preflight
remains read-only. Synthetic ledger UUIDs identify test scopes. Server account
authorization still belongs to the independent identity/session boundary.

## Independent operator evidence

- Keep separate synthetic journal, checkpoint-anchor, operator and archive
  keys. The operator owns the latest record and tip outside the fixture.
  Every proposal increments the sequence and names the previous record MAC.
  Each new checkpoint advances the epoch by one.
- Publish the prepared record and tip as one compare-and-swap against the
  previous tip, using the same independently controlled lineage ID throughout.
  This is the external custodian's contract. This version implements proposal
  and verification only. Establish genesis once for a new lineage.
- Prepare advancement from the pinned original and a private candidate.
  Every existing account's immutable policy and exact journal prefix must
  match. A larger event count alone cannot establish continuity.
- Prepare journal rotation by predicting the replacement MACs in a rolled-back
  SQLite transaction. Execute only against the independently published pending
  tip and only when the before and after checkpoints match inside the write
  transaction. Retired keys cannot be reused for that lineage.
- A pending tip and matching old database produce `AMBIGUOUS_OLD_STATE`.
  Freeze operations after an uncertain publication or commit. A matching
  prepared target requires explicit operator promotion and separate tip
  publication. Recover the latest tip from the custodian after an interruption.
  The external workflow must serialize execution of a published plan and must
  never replay the write automatically after an uncertain result.
- Compromise, indeterminate evidence or an integrity failure can produce
  terminal quarantine. Compromise retires both journal key IDs when a rotation
  is pending. Quarantine blocks this lineage's promotion, sealing and restore.

## Encrypted backup and restore

Seal a consistent SQLite backup against the active tip, then encrypt it with an
independent Fernet key. The archive contains the synthetic SQLite image. Its
authority comes from the separate operator record and anchor checkpoint.

Restoration requires operator approval bound to the ciphertext digest, current
tip and exact new destination. Decrypt privately, check the expected SQLite
schema, integrity, foreign keys and complete account inventory, then replay the
fractional accounting journal and compare the active checkpoint. Publish using
an atomic no-replace hardlink. An existing destination, sidecar, stale archive,
pending tip, or extra link after interrupted cleanup blocks recovery. Use a
private 0700 directory for the destination.

The tests use synthetic keys and mock independent custody, including interrupted
publication, stale evidence, divergent journals, competing restore attempts and
ambiguous pre- and post-commit rotation states. Rotation and restore preserve
immutable policy, fractional cost basis, exact cents, historical loss stops
after later gains, and scoped request replay and conflict behavior.

## Remaining production gates

Durable external custody, atomic cross-resource publication, trusted operator
authentication and production restore validation require separate verification.
An old authenticated record and database can appear current if the custodian's
tip is rolled back too. Tmpfs cannot demonstrate durability across host loss.
The offline operator and archive modules have no Flask callers and use no
production credentials. Production paper fills, live trading, autonomous
orders and transfers remain disabled.
