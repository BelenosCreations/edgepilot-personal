# Interrupted stage parking rehearsal

Twelve offline Linux tests exercise process exit during directory parking with synthetic terminal receipts and active checkpoints. The publisher prepares a source-attributed location record and its HMAC in a separate directory before a descriptor-anchored `renameat2(RENAME_NOREPLACE)`.

| Interruption or evidence | Read-only result |
| --- | --- |
| Exit before publication starts | The original stage and publication link survive. Location-record review refuses the missing record. |
| Exit after writing the record body | The original stage and unsealed record survive. Location-record review refuses the missing seal. |
| Exit after writing the seal, before parking | The signed record, directory identity, hard link and independent evidence identify the stage at its source. |
| Exit immediately after parking | The same evidence identifies the stage in the holding directory. |
| Two valid signed records name different parking locations | Review refuses the conflict and preserves both records. |
| Independent evidence changes after the publisher exits at the parked location | Review refuses the observed evidence mismatch and preserves the candidate and evidence. |

Review describes where the exact staged link was observed. It preserves candidate names, record bytes, independent evidence and the published link in every scenario. It never retries parking, accepts the candidate for recovery, restores it or unlinks it.

These are process-exit tests on an operating host. The separate writes and directory rename have no cross-resource durability guarantee. The HMAC key and expected record are synthetic review fixtures held in memory. Joint rollback of all evidence and uncontrolled same-UID swaps remain outside the rehearsal. Production recovery and trading paths are outside the scope of this milestone.
