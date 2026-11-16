# Read-only review during location pin changes

Ten offline Linux tests exercise the terminal-receipt and active-checkpoint parking fixtures. The reviewer observes the location pin's directory entry identity and exact digest, checks the observation after reading the signed record, and checks it again before reporting the stage location. A visible pending pin update also causes review to refuse.

| Competing event | Evidence retained after refusal |
| --- | --- |
| The pin changes to an earlier valid signed record while the current record is open | Original and competing pins, both signed records and the parked stage |
| The pin changes after stage verification, immediately before the reviewer returns | Original and competing pins, both signed records and the parked stage |
| A writer exits after preparing the competing pin and before replacing the active pin | Original active pin, pending and retained competing pin, both signed records and the parked stage |
| A writer exits immediately after replacing the active pin | Original archived pin, newly active competing pin, both signed records and the parked stage |
| The pin is replaced by a different file containing the same digest | Both pin identities, both signed records and the parked stage |

The competing digest points to a genuinely signed record from an earlier parking operation on the same stage. The same-digest test isolates file identity from digest changes. Each case first verifies that stable read-only review can report the parked location with the same underlying evidence.

The test uses a local staged file and an atomic rename of the active pin pathname. Independent storage custody, behavior across power loss, combined evidence rollback and changes after the final recheck remain unresolved. The fixture's retained pins and record pairs model review evidence only.
