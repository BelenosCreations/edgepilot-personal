# Independent promotion checkpoint rehearsal

Before promoting a frozen synthetic ledger, independently review the reserved
receipt and the exact prepared witness tip. Provision `DecimalPromotionCheckpoint`
in a separate private directory with a separate key. Its initial receipt must
match the prepared tip. A rotation also requires its consumed witness claim.
Supply the checkpoint to `promote_frozen` with the existing signed approval,
the reviewed receipts and the key for the exact prepared ledger.

The rehearsal verifies the signed ledger and receipt ancestry, commits the
witness promotion, retains its exact receipt in the separate checkpoint, and
then updates the local receipt store. The same approval can complete receipt
retention after process exit. Readback rechecks the ledger and both receipts.
The legacy rehearsal and explicit terminal quarantine remain available.

| Evidence after interruption or rollback | Result |
| --- | --- |
| Current witness and ledger, local reservation restored, independent checkpoint current | Reaudit the exact target and retain the already-published receipt locally |
| Witness restored to the prepared tip, independent checkpoint current | Refuse promotion and require operator review |
| Ledger restored to the old checkpoint, independent checkpoint current | Refuse promotion and require operator review |
| Independent checkpoint restored to the prepared tip, local receipt current | Refuse the inconsistent readback |
| Witness, checkpoint and local reservation restored together with the exact prepared ledger | Same evidence as first promotion. The operator can publish the same signed successor again |

The process-exit test covers the boundaries before the witness update and
between each of the three commits, plus exit after local retention. The
checkpoint models monotonic compare-and-swap under a separate custodian.
It does not establish operational custody, resistance to coordinated rollback
of all evidence, or cross-resource power-loss consistency. All writes use
synthetic evidence and the ledger remains read-only throughout promotion.

## Restore cleanup and owner history

Concurrent cleanup attempts allow one operator to unlink the orphan staging
name. When a process exits before or after unlink, use the original ciphertext,
policies and retained pin to inspect the destination. The regression verifies
the same destination inode and bytes, including archived request digests,
historical paper accounting and quarantined account bindings.

Source-attributed Public history stays limited to the session and supports
one-week and one-month requests. The synthetic regression verifies that an
unsupported period is rejected before a provider request. Real history still
requires [targeted owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
Earlier snapshot and MSFT quote acceptance still apply.
