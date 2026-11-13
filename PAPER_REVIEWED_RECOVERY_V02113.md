# Reviewed synthetic paper recovery

## Resolve a frozen receipt reservation

Keep the reserved receipt and the reviewed prepared receipt under independent
custody. The witness must authenticate both positions in the same chain. The
prepared receipt must be at the reservation or immediately after it. A rotation
requires a consumed claim. A ledger at the old checkpoint remains ambiguous.

Use `approve_decimal_promotion` with the signed prepared record and exact
target, then give the resulting signed active record to
`DecimalReceiptStore.promote_frozen` with the reserved and prepared receipts.
Use the key for the prepared target. The resolution checks the target under a
read transaction, authenticates the checkpoint and promotes only the reviewed
record. It never retries the interrupted ledger write. If the witness recorded
the exact promotion before the receipt store retained it, repeat the review
with the same two receipts and signed record. The helper reaudits the target
before retaining the exact successor. Use terminal quarantine if the target
or receipt ancestry cannot be established.

The witness and receipt store use separate SQLite commits. The regression
covers process exit between commits. Protection against rollback of all
resources and externally retained evidence, operational custody, and
cross-resource power loss still require independent verification.

## Remove an orphaned staging link

For a synthetic restore interrupted after its final link, inspect the candidate
with `inspect_pinned_paper_publication`. Review the retained archive pin,
policies, destination and specific staging path in the private fixture directory.
When the publisher has exited, call `cleanup_pinned_paper_staging_link` with
both paths and the original archive, key, policies and retained pin. The helper
checks both names against the same inode, requires exactly two links, checks
the publication lock and SQLite state, and reaudits the destination before
unlinking only the staging name. Reinspect the destination to confirm that it
has one link and account bindings remain quarantined. A refusal leaves the
candidate for operator inspection. Cleanup assumes an owner-only directory and
cooperating local processes. It offers no protection from a privileged process
rewriting directory entries during unlink.

## Owner history acceptance

The synthetic provider regression covers selecting only Public's regular-market
series even when the response includes other session series. The manual read
stays source-attributed and session-only. See [Public Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2).

Real history acceptance remains pending on the owner's device. Follow the
[targeted history steps](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
The previous snapshot and MSFT quote acceptance still apply.
