# v0.2.89 — Offline paper-ledger integrity and encrypted recovery rehearsal

**Scope:** Development-only, synthetic SQLite fixture under Linux /dev/shm. No live service migration, web endpoint, production restore, Public call, order, transfer or new paid product. Existing Render disks, real accounts, encrypted credentials and passkey records are untouched.

## New recovery checks

- The dormant engine/tenant_paper_recovery_audit.py replays every synthetic paper event per (user_id, account_id) in recorded row order. It confirms that BUY cash debits round up; SELL proceeds round down; running cash agrees with each event and wallet; and the final quantity, released cost basis and realized assumed P&L agree with every stored paper position.
- It fails closed on missing members of the three-table schema, malformed event IDs or fingerprints, negative cash, impossible sales, mismatched arithmetic, missing wallet ancestry, or structurally inconsistent rows. A database without any paper tables retains the older backup contract.
- The existing **synthetic-only** encrypted backup/restore rehearsal now performs that audit both before sealing and after opening an archive. SQLite integrity, foreign keys, private tmpfs-only paths, owner-only file modes and revocation/quarantine remain separate mandatory checks.
- Synthetic two-identity/three-account tests verify a sealed round-trip retains all paper records **but** permanently denies direct paper snapshot and wallet operations while restored account connections are revoked and linked accounts disabled. Tampered cash, cost basis and partially missing schema are refused before archive creation.

## Boundaries and unresolved acceptance

This is *structural and arithmetic* verification, **not** cryptographic proof of quote origin, historical rights, trusted market prices, or broker execution. Persisted quote-rights evidence is not independently signed; the prototype never claims otherwise. The current recovery API only supports disposable in-memory test fixtures; do not pass live Render tenant data or claim production backup/restore is complete.

Before real paper-mode activation: implement verified server-side identity and CSRF authorization, provider-licensed quote capture and retention evidence, additional signed audit/backup protection as needed, production-safe encrypted backup/restore with an explicit restore policy and operator acceptance, owner-device acceptance, and independent reconciled brokerage presentation. A restored archive must never resurrect old Public keys or passkey sessions.

**Always disabled:** live trading, autonomous orders and bank transfers. No new hosting or API charges.
