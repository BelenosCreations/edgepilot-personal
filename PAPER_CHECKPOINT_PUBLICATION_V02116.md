# Interrupted synthetic checkpoint recovery

Checkpoint recovery verifies the signed export, retained receipt, witness and
prepared ledger before building a replacement in a private staging directory.
It reads the staged database back before publishing it with an exclusive hard
link. A partial staging database never appears at the reviewed destination.
An existing destination or SQLite sidecar stops publication.

After a process exit, inspect the reviewed destination with `inspect_recovered`
and the same evidence used for recovery. A matching receipt and a second link
mean the verified checkpoint reached its destination. After confirming the
publisher exited, compare device and inode for the specific staging path and
the destination. Remove only that verified staging link, then inspect again.
Normal receipt operations require a single link. If the destination is missing,
recovery can publish at that path. If the destination is partial or ambiguous,
retain it for review and use a fresh destination with the same independently
retained evidence. Signed terminal quarantine remains available when exact
recovery evidence is unavailable.

The tests exit during SQLite staging, before publication, and immediately after
the final link. They also verify that recovery refuses to overwrite a partial
checkpoint. This is an offline rehearsal. Combined evidence rollback and power
loss across the witness, ledger and receipts remain open.

## Quarantined tenant access

The restored synthetic tenant fixture rejects its archived session and CSRF
pair, saved WebAuthn request, and unused invitation. A fresh password session
can authenticate the existing identity. Its quarantined account and provider
credential remain unavailable, and other tenants' bindings stay inaccessible.
A fresh WebAuthn request also rejects a restored, revoked passkey before the
cryptographic verification step. Publication and cleanup continue to preserve
historical revocations.

Public history remains source-attributed and session-only. Real history still
requires [targeted owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
Earlier snapshot and MSFT quote acceptance still apply.
