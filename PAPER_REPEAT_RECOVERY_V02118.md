# Repeated offline recovery rehearsal

Checkpoint cleanup was interrupted immediately before and after unlink. In
both cases, the original signed export verified the same destination inode,
receipt and bytes. A separate concurrency test allowed exactly one cleanup to
remove the staging link. When the witness had moved to signed terminal
quarantine, the earlier export could no longer authorize inspection or cleanup.
The checkpoint and staging names remained available for review.

The tenant test sealed a second pinned backup after two synthetic users enrolled
new passkeys and separate provider bindings. A second restore preserved paper
rows, request digests and prior revocations, quarantined the new bindings, and
invalidated sessions, invitations and pending passkey challenges. A pin from
the first archive was refused. Password authentication still opened an identity
session with an empty active account list on the second restore.

The browser regression verifies that a delayed successful Public history
response is discarded after the owner changes the requested period. Real history
still needs [targeted owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
Earlier snapshot and MSFT quote acceptance still apply.

These tests cover synthetic process failures and repeat restores. Coordinated
rollback of all evidence and cross-resource power loss remain open.
