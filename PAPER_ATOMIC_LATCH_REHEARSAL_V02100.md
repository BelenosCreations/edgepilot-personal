# v0.2.100 — Offline atomic synthetic paper loss-stop latch rehearsal

This is **not** active paper trading, production risk enforcement, market-data
licensing, an authenticated HTTP API, or a production backup/restore facility.

The isolated module `backend/engine/tenant_paper_latch_rehearsal.py` exercises
an SQLite transaction design in a freshly created private 0600 file on
verified Linux `/dev/shm`. It cannot open an existing file for initialization,
write to Render's existing production database, import into the Flask app or
connect to the dormant paper-fill writer.

The operator/test supplies fresh **synthetic** UUID identities, a separate
random 32-byte-or-longer HMAC key, and an explicit integer-cent loss threshold.
Neither the key nor source market quotes are stored in the fixture. Each
separate user/account scope has a fixed, authenticated threshold, signed event
chain, reconstructed realized P&L floor, sticky loss-stop latch, and
replay-protected request identifiers.

A transaction uses `BEGIN IMMEDIATE` to replay and authenticate the journal
before recording a simulated `OPEN` admission decision or an assumed
`REALIZE` event. A loss reaching the threshold latches the account; later
synthetic gains and new connections do not clear it. Later `REALIZE` updates
can be recorded as assumed closing/reconciliation outcomes, but post-latch
`OPEN` admissions are denied. Duplicate identical UUID requests return
their original decision, even if the latch changed subsequently; a changed
payload under the same UUID is refused. The state update and journal insert
share a transaction; injected failure before commit rolls back both.

Both `OPEN` and `REALIZE` events are **fictional decision inputs**. An
accepted `OPEN` is not a broker order, paper fill, reserved position, trading
signal or authorization to invoke the dormant fill writer. This rehearsal
does not mark open positions, verify market data, calculate live equity, prove
identity from a server session, guarantee durable storage across tmpfs reboot,
or connect its locking transaction to any fill operation. HMAC prevents
undetected changes to the synthetic journal only while the caller-held key is
kept outside the database; key compromise, deletion of the entire fixture,
replay of an old complete fixture, disk-level crash recovery, multi-process
migration, and operator-level resets are **not** solved.

Verification includes independent simulated family/account scopes,
threshold equality, persistent synthetic latch after gains, replay conflicts,
injected atomic rollback, wrong-key/HMAC alteration, journal deletion,
invalid money, non-tmpfs rejection and refusal to overwrite fixtures.
Read-only owner acceptance results from v0.2.94 remain complete and unchanged.

**Remaining activation gates:** authorization for Public market-data
retention/usage, trusted session/account binding and request protection,
production durable backup and anti-rollback with key rotation, recovery of a
tamper-evident policy/latch, formal lock ordering in a licensed paper-fill
transaction, independent review and explicit operator approval. Until then,
production paper fills, live orders, autonomous trades and bank transfers
remain disabled. No Render service, disk, credentials, provider, paid plan
or existing account is modified by this module.
