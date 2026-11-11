"""Manual-only empty tenant database initialization on the paid Render disk.

Not a migration, service startup hook, HTTP endpoint, or owner bootstrap.
An operator must already have independently verified backup and recovery.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import permanent_storage_init


def main():
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("Trusted interactive console required.", file=sys.stderr)
        return 2
    try:
        legacy = os.environ["EDGE_DB_PATH"]
        tenant = os.environ["EDGE_TENANT_DB_PATH"]
        if legacy != "/data/edgepilot.db" or tenant != "/data/edgepilot-tenants.db":
            print("Only the existing paid /data disk may be prepared.", file=sys.stderr)
            return 2
        print("Requires independently verified encrypted backup and restore.")
        print("This creates ONLY a NEW EMPTY tenant file; no member or broker access.")
        approval = input("Type PREPARE ISOLATED EDGEPILOT STORAGE to approve: ")
        result = permanent_storage_init.prepare_private_tenant_storage(
            os.environ, legacy, tenant, approval=approval)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (KeyError, EOFError, KeyboardInterrupt,
            permanent_storage_init.PrivateStorageInitDenied):
        print("Private tenant storage not prepared or cannot be verified.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
