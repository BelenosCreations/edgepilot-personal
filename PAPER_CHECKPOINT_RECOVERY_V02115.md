# Recover an independent synthetic promotion checkpoint

After a reviewed promotion, export its retained receipt with
`DecimalPromotionCheckpoint.export`. Keep the authenticated export and the
latest accepted receipt under independent custody. A signature authenticates
an export's contents. The separately retained latest receipt establishes which
export to use.

If the checkpoint file is lost, use `DecimalPromotionCheckpoint.recover` with
the original checkpoint key, export, separately retained latest receipt, signed
promotion, and reviewed reservation and prepared receipts. Recovery requires the
exact witness tip and verifies the prepared ledger under a read transaction.
It creates a checkpoint at a new path. The helper refuses an existing file,
missing resources, stale exports, and witness evidence from another lineage.
A still-frozen local receipt can be acknowledged separately using the restored
checkpoint and the original signed promotion. When there is no exact completed
promotion to recover, explicit signed terminal quarantine remains available.

The rehearsal assumes independent retention of the latest receipt. Coordinated
rollback of all retained evidence and power-loss consistency across resources
remain open.

## Quarantined restore security state

Pinned publication, inspection and cleanup compare the restored identity and
security records against the sealed archive. The audit includes account and
connection ownership, encrypted credential bytes, passkey identifiers and
counters, existing revocation timestamps, identity records and authentication
audit history. It verifies invalidation of saved sessions, challenges, invites
and worker leases. Connections without a linked account receive the same
revocation checks as linked connections. The offline regressions verify the
same state through publication and staging-link cleanup.

## Owner history

The synthetic owner-history test exercises session revocation while the source
request is in flight. Real Public history remains session-only and still needs
[targeted owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
Earlier snapshot and MSFT quote acceptance still apply.
