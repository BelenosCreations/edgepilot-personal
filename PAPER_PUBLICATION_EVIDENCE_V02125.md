# Publication evidence

An offline terminal receipt repair checks the same independent receipt and
signed witness before linking a missing local receipt and after syncing the
destination directory. A loss detected before linking leaves the destination
absent. A loss or replacement detected after linking preserves the two names
for exact inspection after the evidence returns. Tests exercise both evidence
files and the operator's subsequent inspection and cleanup.

Active checkpoint readback rechecks the local receipt, signed witness and ledger
paths while the verification transactions are open. Cleanup makes the same
check immediately before unlink. A replacement with identical bytes still
interrupts the current review. A later operation can authenticate an exact
candidate with restored evidence. Second-generation archive readback refuses
a byte-identical replacement candidate after its audit and succeeds when the
original inode and exact archive pin are available again.

The synthetic owner history request returns no bars after logout and makes no
provider call. Real history remains limited to [owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
Combined rollback, filesystem changes after the final evidence check and
cross-resource power loss remain open. Production paper fills, live trading,
autonomous brokerage orders and bank transfers remain disabled.
