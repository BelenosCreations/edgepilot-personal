# Generation marker rehearsal for late evidence changes

Six offline Linux cases cover terminal receipts and active checkpoints. The reader pauses after all record paths have passed their final sequential recheck. A cooperating writer then replaces the signed body and seal while preserving the old generation.

The unguarded cases demonstrate that sequential rechecks can still report the earlier authenticated record and active pin after those record paths change. This is a reproducible boundary of the existing test reader.

The guarded cases add an optional test-only generation file. Cooperating writers replace it with an odd value before modifying evidence and a new even value after completion. A reader observes an even generation before inventory and rechecks its bytes and identity before returning. Stable guarded inventory succeeds. Completed and pending updates at the late boundary cause it to report ambiguity.

Both record generations, the parked stage and publication link remain available. This prototype assumes a serialized cooperating writer that follows the marker protocol. It has no durable monotonic authority and cannot detect coordinated evidence rollback, marker reuse or an uncontrolled same-UID writer. Changes after the final generation read remain outside its observation. These tests provide no production recovery API or decision about stage use.
