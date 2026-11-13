# v0.2.103 — Encrypted, externally pinned synthetic loss-stop recovery

**Offline-only research milestone.** This does not authorize production paper
fills, actual market-data persistence, brokerage orders, automatic trades, bank
transfers, production backup/restore, Render migrations or paid services.

## Scope and trust boundary

`backend/engine/tenant_paper_latch_archive.py` provides a separate,
non-HTTP, non-production encrypted snapshot-and-restore rehearsal for the
v0.2.100–v0.2.102 synthetic per-account loss-stop journals. Neither the Flask
server nor the dormant paper-fill writer imports the module.

Only private `0600`, single-link, verified Linux `/dev/shm` synthetic
SQLite fixtures are eligible. The module requires all three independent
caller-held keys:

- **Journal HMAC key** to authenticate each synthetic user/account policy
  and every event in its full chronological chain.
- **Checkpoint anchor HMAC key** to verify the **latest independently held**
  full-fixture checkpoint and operator epoch, not a freshly generated pin
  from an untrusted restored database.
- **Separate Fernet AES-128-CBC/HMAC authenticated-encryption key** (provided
  through cryptography's Fernet API) to protect a consistent SQLite snapshot
  in an in-memory ciphertext token. This is not AES-256-GCM and makes no
  production-grade key-lifecycle guarantee.

No key is stored in the snapshot or committed to the repository. All
plaintext SQLite bytes, including private backup and restore stages, remain
under verified Linux `/dev/shm`; encrypted output is returned as bytes to
the **operator**, who is responsible for secure independent custody of it.

## Backup research

`seal_synthetic_latch_archive(..., trusted_checkpoint=latest_pin)`:

1. Rejects non-tmpfs or non-private fixtures and over-limit file sizes.
2. Takes a consistent SQLite backup into an exclusive 0600 temporary
   `/dev/shm` snapshot, with no WAL-enabled source.
3. Refuses an unexpected database schema, invalid SQLite integrity or
   foreign-key result, or any user/account chain inconsistent with the
   operator's externally pinned complete inventory.
4. Authenticates and encrypts the SQLite data into an in-memory Fernet
   ciphertext token, discarding the temporary plaintext stage.

A concurrent source mutation that changes snapshot state relative to the
latest pin fails the independent checkpoint audit rather than being
silently accepted. The ciphertext is NOT a production recovery artifact.

## Restore research

`restore_synthetic_latch_archive(ciphertext, destination_path, ...,
trusted_checkpoint=latest_pin)`:

1. Authenticates and decrypts the ciphertext in memory.
2. Demands a new absent destination within verified `/dev/shm`; never
   overwrites an existing file or symlink.
3. Writes and fsyncs a private 0600 staging file in the same directory,
   then verifies its complete synthetic schema, SQLite integrity, every
   HMAC policy and journal chain, and the **latest external checkpoint**.
4. Publishes an already-validated file with an atomic no-replace hardlink;
   cleans up temporary staging and sidecars following normal completion
   or handled failure.

Tampered ciphertext, wrong archive/HMAC keys, a removed entire account,
missing or forged checkpoints, altered losses, stale encrypted snapshots,
schema drift and injected pre-publication failures are refused without
publishing any incomplete requested destination.

**Key limitation:** A holder of a stale pin **and** matching old keys can
approve a stale encrypted archive. This module does not provide an external
monotonic pin authority, automatic key retirement, separate audit log,
physical hardware trust, power-loss-durable storage, or detection when both
the database **and** its operator checkpoint are rolled back. A post-commit
journal-key rotation followed by a restored older archive must be resolved
against an independently trusted latest rotation ticket, key epoch and
operator evidence. Do not issue a fresh pin from an untrusted restore and
call it validated.

The fixture contains no production session state or real brokerage access,
so there are no real credentials to quarantine in this particular archive.
The **separate** tenant paper-ledger backup runbook already handles
different schema/identity quarantine semantics; do not substitute these
fixture functions for that facility.

## Test and activation gates

From `backend`, run:

`python -m unittest discover -s tests -p 'test_tenant_paper_latch_archive_v02103.py' -v`

Eight isolated tests cover independent user/account scope, immutable
historical losses, encrypted roundtrip, wrong keys and modified ciphertext,
older valid snapshot refusal against a newer trusted pin, changed/removed
account data, wrong synthetic schema, external path refusal, atomic no-replace,
fault injection and journal-key-rotation recovery. Full Flask/Python and
browser regression suites must still pass.

Next gates remain: operator-controlled monotonic checkpoint custody,
durable encrypted recovery under power-loss testing, crash/restore key
revocation, actual reliable backup retention, locked consistency with the
dormant paper ledger's position/cash/realized-loss updates, verified quote
usage rights, authenticated server session binding, explicit operator
approval and independent integration review. Do not activate paper fills
until all are met.
