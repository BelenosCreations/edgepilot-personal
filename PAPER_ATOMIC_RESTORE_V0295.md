# v0.2.95 — Atomic publication and rollback of synthetic encrypted paper recovery

**Scope:** Offline test fixtures under a verified Linux `/dev/shm` tmpfs only. This is not a production backup/restore implementation, a migration or paper-trading activation. No real account, Render disk, user credential, Public quote, order, banking operation or hosted service is accessed or changed.

## Previous limitation

The v0.2.89 encrypted synthetic restore created the *requested final destination* before validating SQLite integrity, replaying paper cash/basis, revoking recovered broker links, purging identity sessions and rechecking the restored schema. On normal exceptions it removed that file, but a crash or a concurrent reader could potentially observe an unverified, partially written database at the final path. `O_EXCL` protected existing files; it did not provide atomic publication after validation.

## New fail-closed sequence

1. Decrypt the Fernet-authenticated archive with a separately supplied key, validate its magic and SQLite header and refuse an existing requested destination.
2. Create a private `0600` random staging file under the **same verified tmpfs parent**, not the caller's requested destination. Write and fsync the staged bytes, then verify source location and SQLite integrity, foreign keys, schema and dormant paper event/cash/cost-basis replay.
3. Inside that staged DB, transactionally erase sessions, pending WebAuthn challenges, unredeemed invites and worker leases; quarantine every restored Public connection and linked account; revoke restored passkey credentials. Recheck integrity and commit; fsync the staged file again.
4. Publish to the requested previously nonexistent path only after all checks, through `os.link(stage, destination)`. A hard link is atomic, never replaces existing data, and fails if another actor created that destination during validation. Clean only the private stage and its sidecars; never delete a preexisting or concurrently created destination on failure.

This is a synthetic **atomic visibility** safeguard, not a guarantee of production power-loss durability, independently signed backup contents, trust in old market-data rights, or a proven live disaster-recovery procedure. Leftover private staged files after a process crash still require a future operator cleanup policy.

## Synthetic fault-injection acceptance

- A valid encrypted paper archive is restored with the same three wallets and synthetic assumed-fill history while every user-account link remains quarantined.
- A preexisting destination is left byte-for-byte untouched and no private stage remains after a rejected restore.
- Wrong-key decryption, authenticated malformed SQLite, injected staging fsync failure, and a simulated no-replace publication collision leave **no final destination** and no staged files.
- A failure during post-quarantine validation rolls back unpublished staged data; none of the assumed fills become available for an authenticated recovered account.
- Existing cross-identity and cross-account snapshot/open-wallet denials remain in force; tests never invoke the broker, live app or paid Render resources.

## Remaining production gates

Before real backup/restore or **production paper fills**, implement an authenticated and operator-approved production archive/restore policy with durable encrypted storage, independent integrity/signature controls, at-rest key rotation and loss scenarios, transaction/version compatibility, key/identity/session anti-resurrection, deterministic rollback and account-scope acceptance. Provider permission to *retain* quote evidence must be established independently; a successful manual MSFT quote and same-account comparison do not grant it. All live orders, autonomous orders, bank transfers and paper fills remain OFF. The dormant modules are **not imported** by the runtime web app.
