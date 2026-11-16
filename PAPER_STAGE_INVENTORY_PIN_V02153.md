# Read-only stage inventory and record pinning

This offline Linux rehearsal uses synthetic terminal receipts and active checkpoints. Twelve tests cover ambiguous directory names after a process exit and selection of the exact signed location record using an independently retained SHA-256 digest.

| Observation | Review result |
| --- | --- |
| The exact stage is still at its source and the parked name contains another directory | Report the two observed entries and refuse to select a stage. |
| The exact stage is parked and the source name contains another directory | Report the two observed entries and refuse to select a stage. |
| Both expected names are absent | Report both names absent. Preserve the displaced stage. |
| Earlier and current signed records are available | Select the exact pinned current record, then verify the observed parked location and independent evidence. |
| Only the earlier signed record is available for review | Refuse because no candidate matches the current pin. |
| Both signed records are available and the pin is missing | Refuse because independent selection evidence is missing. |

The earlier record comes from a completed parking operation on the same stage and publication link, signed by the same synthetic authority. The current operation uses a different holding directory. The tests retain the earlier record pair, current publication link and all observable candidates. Review checks directory identities without following symlinks during inventory. The test verifies the pin against the exact authenticated record bytes.

The digest models an independently retained pin. Its test file shares the host and user identity with the publisher, so the rehearsal cannot establish independent custody, monotonic state or durability across power loss. Coordinated rollback of all evidence and uncontrolled same-UID path changes remain unresolved. The rehearsal makes no production recovery or trading changes.
