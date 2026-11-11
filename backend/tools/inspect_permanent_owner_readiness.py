"""Console-only read-only identity readiness check on the existing paid disk."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import permanent_owner_readiness


def main():
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("Trusted interactive console required.", file=sys.stderr)
        return 2
    try:
        legacy = os.environ["EDGE_DB_PATH"]
        tenant = os.environ["EDGE_TENANT_DB_PATH"]
        if legacy != "/data/edgepilot.db" or tenant != "/data/edgepilot-tenants.db":
            print("Only the existing paid persistent disk may be inspected.", file=sys.stderr)
            return 2
        report = permanent_owner_readiness.inspect_owner_readiness(
            os.environ, legacy, tenant)
        print(json.dumps(report, sort_keys=True))
        print("Readiness report is NOT cutover approval.")
        return 0
    except (KeyError, permanent_owner_readiness.OwnerReadinessDenied):
        print("Independent owner readiness not established.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
