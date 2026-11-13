# Independent witness recovery receipt

The offline Decimal rehearsal can retain a witness receipt under a separate
key in a separate private directory. The operator provisions it at an
explicitly reviewed tip that matches the local receipt and witness. To advance
it, supply both the expected retained receipt and the exact reviewed successor.
The witness must authenticate the previous receipt in its ancestry and the
reviewed receipt at its current tip. Retrying an already completed update with
the former expected receipt is refused.

When supplied to witness recovery, the independent receipt must match the
local receipt and the snapshot. The existing ledger audit still applies to
active and prepared records. A terminal quarantine record can be recovered
without the ledger. In the synthetic test, the promotion checkpoint was
lost and both local resources were rolled back to an earlier active receipt.
The independent terminal receipt rejected the rollback. Recovery succeeded
after supplying the matching terminal local receipt and terminal witness
snapshot. The earlier active checkpoint export could no longer be recovered.

The operator must retain the independent receipt and matching witness
snapshot before loss. The rehearsal uses separate directories and keys.
Independent durable storage, atomic cross-resource publication and recovery
after simultaneous rollback of every trusted copy remain open. Existing
witness recovery callers can continue to use the local receipt path.

The second tenant restore exits after linking its destination. Inspection and
cleanup refuse older archive evidence, even when paired with its valid old
pin. Cleanup with the exact second-generation pin removes the orphan link
and preserves the published inode and bytes, scoped request digests,
historical stops and quarantined account bindings.

Synthetic Public history tests discard a response when the selected account
is disabled during the request. Real history still needs
[targeted owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
Earlier snapshot and MSFT quote acceptance still apply. Production paper
fills, live orders, autonomous brokerage orders and bank transfers remain
disabled.
