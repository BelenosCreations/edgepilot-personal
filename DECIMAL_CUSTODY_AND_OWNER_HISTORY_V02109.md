# Synthetic recovery custody and owner price history

## Operator custody

The offline Decimal custody prototype stores a single synthetic lineage in a
separate 0600 SQLite file under a private operator directory. It authenticates
each event with a custody key and checks the embedded operator signature. The
journal checks sequence, prior MAC, lineage, pending epochs, retired keys and
terminal quarantine. It requires an independently retained receipt for reads
and the exact latest receipt for compare-and-swap publication.

A prepared rotation claims its intent in a committed custody transaction before
touching the ledger. The claim stays consumed after interruption. A second
custody transaction holds the write lock across the SQLite ledger rotation and
checks that quarantine or another publication has not superseded the claim.
Review then compares the observed ledger with the pinned and prepared states.
An older state under a pending receipt is ambiguous. An exact prepared target
still needs explicit operator promotion.

After a lost publication response, read back from the witness using the last
independently retained receipt and compare the returned signed record with the
proposal. Do not retry an uncertain rotation. Retain receipts from successful
publication outside the witness database. Test coverage includes a real process
exit after claiming the operation, failures around both commits, concurrent
publication, invalid transitions and stale witness rollback.

This is a local synthetic prototype. The witness can use disk-backed SQLite
with EXTRA synchronous mode. Independent deployment, custody of receipts and
keys, operational backup, power-loss verification and protection from rollback
of both witness and receipt are still open. SQLite locks serialize cooperating
processes. They do not make witness and ledger commits atomic across resources.
No runtime caller uses the witness and no real data enters this rehearsal.

## Owner price history

Under the owner's instruction to proceed assuming provider permission, the
existing sole-owner dashboard supports one-week and one-month Public histories
for stock, ETF and crypto symbols. A same-origin manual request uses the
existing identity session, CSRF protection, linked account verification, quota
and recheck after provider I/O. History uses the selected account's Public
credential and checks the account link even though Public's history URL is
token-scoped. It reads the documented regular-market series, requests regular
hours explicitly for weekly equities, rejects redirects and bounds the response
size before parsing.

The dashboard displays exact source OHLC values, volume and UTC timestamps.
Crypto volume can retain fractional precision. Any documented chart lead-in
interval is excluded. The feature displays only the validated source series.
Bars and derived results are kept out of persistent storage. They clear on
account or input changes and page exit. The response sends Cache-Control
no-store. Provider-side entitlement remains enforced by the API.

Implementation treated provider permission as an assumption. The history
endpoint was tested with synthetic provider replies and real application
authorization. Real stock, ETF and crypto bar retrieval from the owner's device
is still unverified. The [Public history contract](https://public.com/api/docs/resources/market-data/get-bars-v2)
documents the source endpoint and response.

Production paper fills, autonomous and live brokerage orders, and transfers
remain disabled.
