# Signed record evidence after a restart

Twelve additional offline Linux tests cover missing record pairs, a missing body or seal, an invalid seal, a malformed signed body, and a valid seal for the wrong source. Each case runs for both terminal receipts and active checkpoints. The fresh reader reports the condition of each record slot and matches pin digests only to authenticated records attributed to the expected source.

The existing replacement cases now explicitly verify that the active pin can authenticate an earlier record while the stage and exact publication link remain in the later holding directory. The earlier parking name is absent. The pin reader reports the authenticated reference. The independent location review refuses the mismatch. File identities, links and bytes survive both observations.

The rehearsal uses local synthetic evidence. Pin inventory has no authority to select a stage for use, and it leaves independent storage custody, coordinated rollback, uncontrolled same-UID changes and durability across power loss unresolved.
