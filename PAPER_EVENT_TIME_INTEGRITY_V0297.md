# Offline paper event-time integrity — v0.2.97

## What is checked

The synthetic-only paper recovery audit already checks tenant/user-account isolation, cash continuity, per-position cost basis, realized synthetic P&L, event replay arithmetic, and schema completeness. It now also checks recorded event source observation and local paper creation times before offline encrypted source sealing or final quarantine-and-no-overwrite restoration.

Both timestamps must be real calendar dates in timezone-aware UTC ISO-8601 form (Z or +00:00). Local-time/naive stamps, non-UTC offsets, impossible dates and claimed observations newer than the recorded assumed-fill event are rejected. This establishes limited internal chronological coherence, not external attestation of the provider or its clock. It cannot prove source accuracy, market-data caching rights, historical-data licenses, execution eligibility or profitability.

## Synthetic negative tests

The offline two-identity, three-account setup mutates one event timestamp at a time without changing cash or foreign keys. The auditor and encrypted archive creation both must refuse: nonsensical timestamps, missing zone, non-UTC offset, invalid calendar date, observation later than creation and a created-at field older than the observation. Repaired legitimate fixtures must continue to seal. All tests are offline on disposable /dev/shm fixtures.

## Production gates still closed

Do not import the dormant paper-ledger or recovery auditor into the HTTP app or run against the real persistent disk. Do not switch on production paper fills, broker orders, autonomous trading or transfers. Production restore still requires a separately approved, operator-controlled plan with tested key rotation, durable storage and crash cleanup, and verified per-account source retention/usage rights. The existing Render service, paid plan, disk, accounts, passkeys, encrypted secrets and original owner acceptance remain untouched.
