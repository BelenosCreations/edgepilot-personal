# Offline checkpoint staging cleanup and tenant re-enrollment

Concurrent recovery attempts publish at most one replacement checkpoint at the
reviewed destination. The publisher holds a lock on its private staging
directory through publication and removal of its staging link.

If a publisher exits after linking, inspect the destination against the
independently retained receipt and signed export. Review the specific staging
path and call `cleanup_recovered_stage` with the original recovery evidence.
Cleanup refuses an active publisher, an unrelated file or symlink, sidecars,
and unexpected additional links. It verifies the destination and the reviewed
staging name are links to the same inode, then unlinks only the staging name.
Reinspect the destination to confirm the authenticated receipt and a single
link. The staging directory remains available for operator review.

This rehearsal assumes private directories and cooperating local processes.
Combined rollback and cross-resource power-loss consistency remain open.
The existing signed terminal-quarantine workflow remains available.

## Restored tenant isolation

The synthetic test explicitly enrolls new connections and accounts for two
restored users and verifies each session sees only its own account and
credential. Each user can enroll a new synthetic passkey and obtain an
identity session for the correct user. The cryptographic verifier is stubbed
only in the test. A revoked passkey identifier cannot be reused. Revoked
connections refuse rotation, and old invitations remain unusable after a
new invitation succeeds.

The session-only Public history regression checks that a response is discarded
if the selected connection's encrypted credential changes during retrieval.
Real history acceptance remains on the owner's device. Follow the
[targeted steps](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
