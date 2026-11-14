# Preserved staging inventory

Offline terminal receipt and active checkpoint recovery leave the staging
directory in place after removing the verified staging link. An exclusive
publication that loses a race leaves its candidate intact. These paths sync
and recheck the exact publication and evidence after successful cleanup.
An empty same-name directory that arrives during this interval is preserved,
and a changed directory causes the current operation to refuse.

Pass `include_stages=True` to `inspect_local_terminal` or
`inspect_recovered` with the same exact evidence required for readback.
The result adds a `stages` list with the matching names under the destination
parent, their device and inode, each private directory's immediate entry
names, and whether its expected staging filename is a hard link to the
authenticated publication. Symlinks and other unreviewed objects are listed
without traversal. The inventory refuses if observed metadata or names
change during the scan. The default readback result is compatible with
existing callers. Use the inventory for review and the existing cleanup
method for a selected, verified staging hard link.

Empty directories accumulate until manually reviewed. Inventory is a
point-in-time view of direct children with the matching prefix and requires
a current, authenticated publication. The rehearsals cover sync failure,
process exit, later same-name files and evidence or publication changes.
Cross-resource power-loss consistency and combined rollback of all retained
evidence remain open. Tenant archive recovery retains its separate exact pin.
Authenticated paper preflight remains detached from execution.

The synthetic weekly Public history regression checks the exact displayed
source bar and exclusion of provider gain/loss fields. See
[Get bars v2](https://public.com/api/docs/resources/market-data/get-bars-v2)
and [owner-device acceptance](PAPER_RESTORE_AND_CUSTODY_V02110.md#owner-history-acceptance).
