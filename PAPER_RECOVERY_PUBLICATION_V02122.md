# Interrupted recovery publication

The offline terminal receipt rehearsal exited during stage initialization and
immediately after the destination hard link was created. A partial stage
remained outside the destination. A stale but authentic witness could neither
authorize a retry nor verify the published receipt. Exact read-only inspection
verified the independent receipt, signed terminal witness and published inode.
It reported the additional link. A retry left the destination and unrelated
staging files intact. Operator-reviewed terminal staging cleanup remains open.

Second-generation restore cleanup tests inject a directory sync error before
unlink and after unlink. The first leaves the reviewed staging link in place.
The second leaves only the destination name in the running process. Exact-pin
inspection distinguishes the two outcomes. The earlier archive and its valid
pin cannot inspect or change the newer candidate. The published inode, bytes,
scoped requests, loss history and quarantined bindings survive both tests.

A synthetic HTTP test verifies that history reports Public API, Get bars v2
and the selected period. Real history still needs
[targeted owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
Earlier snapshot and MSFT quote acceptance still apply.

Combined rollback of all evidence and cross-resource power-loss consistency
remain open. Production paper fills, live orders, autonomous brokerage orders
and bank transfers remain disabled.
