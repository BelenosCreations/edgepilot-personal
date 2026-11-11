"""Read-only operator-console preflight. No HTTP routes or production cron."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import permanent_cutover_preflight as preflight


def main():
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("A trusted interactive operator terminal is required.", file=sys.stderr)
        return 2
    try:
        result = preflight.inspect_cutover(
            os.environ, os.environ["EDGE_DB_PATH"],
            os.environ["EDGE_TENANT_DB_PATH"])
        print(json.dumps(result, sort_keys=True))
        print("Inspection only: an independent encrypted backup/restore and "
              "owner recovery must still be verified before activation.")
        return 0
    except (KeyError, preflight.CutoverPreflightDenied):
        print("Cutover preflight denied; no databases were migrated.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
