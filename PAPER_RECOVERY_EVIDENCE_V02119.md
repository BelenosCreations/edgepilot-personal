# Recovery evidence across generations

A synthetic second promotion exited after the witness and independent
checkpoint committed, leaving the local receipt reservation frozen. The
advanced witness rejected the first signed export even when the earlier local
receipt and ledger agreed with it. Rebuilding the checkpoint required the
latest independently retained export and the exact prepared ledger. The
rebuild preserved the frozen reservation until explicit promotion readback
retained the exact receipt. Both ledger files kept their original bytes.
Signed terminal quarantine remains covered by the existing regression tests.

The second pinned tenant restore rejected the earlier encrypted archive against
the latest independently retained pin. Three paper accounts used the same
request ID with distinct request digests. The restored history preserved all
three digests under their original user and account. The owner paper accounts
retained the historical loss stop after later gains. A second owner account and
both member accounts had independent loss histories. The restored provider
bindings were quarantined and prior session and passkey revocations were
preserved.

Browser tests verify that an account change or page exit clears Public history
and prevents a delayed response from repopulating the table. Real Public
history still needs [targeted owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
Earlier snapshot and MSFT quote acceptance still apply.

Combined rollback of all trusted evidence and cross-resource power loss remain
open. Production paper fills, live orders, autonomous brokerage orders and
transfers remain disabled.
