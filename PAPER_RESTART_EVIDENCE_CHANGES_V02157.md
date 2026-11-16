# Signed evidence changes during fresh inventory

Eight offline Linux cases pause a fresh reader at a known point. A cooperating writer replaces retained evidence, then allows the reader to resume. The cases run for both terminal receipts and active checkpoints.

| Replacement | Read-only result |
| --- | --- |
| The record body and seal are replaced after the body read | Report the changed body and suppress conclusions from the mixed pair. |
| A signed pair and active pin advance between the record and pin reads | Report the changed pair and suppress the mixed record and pin result. |
| A pin is replaced after the reader observes it | Report the changed pin and suppress the earlier result. |
| A record body is replaced with identical bytes in another file | Report the changed file identity. |

The reported paths describe which observations changed on recheck. A file replaced before its first observation has no earlier observation in that pass. Both generations, the parked stage and the published hard link survive the rehearsal.

The final reads are sequential and provide no atomic multi-file snapshot. Changes after the final read, uncontrolled same-UID races, coordinated rollback and power-loss consistency remain unresolved. The test process inventories evidence only and does not select a stage for use.
