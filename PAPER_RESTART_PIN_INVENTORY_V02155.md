# Read-only pin inventory after a process restart

Twelve offline Linux tests cover the synthetic terminal receipt and active checkpoint parking fixtures. A writer exits after leaving a staged digest or after replacing the active pin. A fresh Python interpreter then reads the retained files and checks complete digests against the exact bytes of authenticated, source-attributed location records.

| State left by the writer | Fresh review |
| --- | --- |
| Active and staged pins reference different valid signed records | Report both record references and mark the update ambiguous. |
| The staged file contains a partial hexadecimal digest | Report the partial staged file and mark the update ambiguous. |
| The active and staged digests both reference the same valid record | Report the matching references and mark the update ambiguous while the staged file survives. |
| The staged digest is complete and refers to no authenticated record | Report the unmatched digest and mark the update ambiguous. |
| The staged digest contains an invalid character | Report the malformed staged file and mark the update ambiguous. |
| The writer replaced the active pin and the staged name is absent | Report which signed record the active pin references. The prior active pin remains available as retained evidence. |

The fresh reader reports pin evidence only. The active digest can reference an earlier signed record after replacement, even though the actual stage remains in the later holding directory. Record authentication does not establish that a location is current. The tests verify unchanged file contents, identities and links through inventory. Review performs no cleanup, promotion, repair, or retry.

The fixture supplies an ephemeral test key to the new interpreter. The rehearsal models process exit on an operating host. Independent storage custody, coordinated rollback, uncontrolled same-UID races and durability across power loss remain unresolved.
