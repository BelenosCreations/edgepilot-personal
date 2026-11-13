# Independent Decimal receipt handoff and pinned tenant restore

## Separate receipt storage

The offline Decimal rehearsal now supports a separate SQLite receipt store
with its own signing key and private directory. It tracks the verified witness
receipt and a signed reservation for an unresolved write. A new store can be
provisioned only at an exact verified witness genesis. The older low-level
custody interfaces remain available for their existing synthetic rehearsals.

1. Record publication and rotation reserve the next write in the receipt store
   before the witness changes. The reservation survives process exit.
2. Record publication retains the exact verified next witness record. A
   rotation claim is acknowledged only after the independent store commits
   that receipt as its next tip.
3. Rotation reopens the independent store and holds its receipt lock while
   the witness and ledger verify the exact claim and prepared target. It
   applies the ledger update only after those checks. A matching target still
   requires explicit promotion.
4. An unresolved reservation freezes the receipt interface. If the receipt
   commit succeeded but its acknowledgment was lost, the newer claim stays
   pinned and the original operation stops. An older ledger remains ambiguous.
   The independently pinned witness recovery path refuses to publish a witness
   against that older ledger. It can rebuild an exact claimed witness against a
   verified prepared target, which still requires explicit promotion.

The receipt, witness and ledger use separate files and keys in the rehearsal.
Treat the receipt location as independently trusted. A valid signature detects
altered evidence but cannot prove freshness if the receipt store itself is
rolled back. The local test processes share an OS identity. Independent
operational custody, recovery from loss of the receipt store, manual resolution
of a frozen reservation, combined rollback protection and cross-resource
power-loss consistency remain open.

## Pinned tenant publication

Concurrent restores of the same pinned archive can publish one new tmpfs
destination. The tests compare the complete scoped paper data against the
pinned source after publication and verify disabled accounts and revoked
connections. Existing coverage checks request UUIDs and digests, fractional
basis, immutable policy and the sticky historical loss stop after a gain.

A failure before linking leaves the destination absent. If linking succeeds
and the reply fails, the completed quarantined fixture can already be at that
path. Inspect it before taking another recovery action. The restore never
overwrites the destination, and refuses an existing SQLite sidecar for a
pinned destination. The test models cooperating processes on isolated tmpfs.

## Owner history

The manual history panel identifies Public and the selected period, and clears
the table when the period changes. A current failure shows a sanitized status
and leaves the table empty. The shipped browser script was exercised with
synthetic replies only. See [Public Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2).

For real owner-device acceptance, use the linked Public account on the owner
dashboard. Retrieve MSFT for one week, switch to one month, and confirm that
the earlier rows clear before loading the new period. Verify the Public label,
UTC timestamps, OHLC and volume, and the provider's expected bar count if
supplied. Report the symbol, period and pass or sanitized status only. Prior
owner acceptance of the same-account snapshot and MSFT quote still applies.
