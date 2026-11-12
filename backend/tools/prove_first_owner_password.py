"""Private console proof of original tenant owner's stored password only.

No HTTP session, password reset, account modification or production cutover.
"""
from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import permanent_owner_password_proof


def main():
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("A trusted interactive Render console is required.", file=sys.stderr)
        return 2
    if (os.getenv("EDGE_DB_PATH") != "/data/edgepilot.db" or
            os.getenv("EDGE_TENANT_DB_PATH") != "/data/edgepilot-tenants.db"):
        print("Required separate paid storage is not configured.", file=sys.stderr)
        return 2
    password = None
    try:
        print("Offline password verification only. No login session will be created.")
        password = getpass.getpass("Enter the new EdgePilot owner password (hidden): ")
        report = permanent_owner_password_proof.prove_first_owner_password(
            dict(os.environ),
            Path("/data/edgepilot.db"),
            Path("/data/edgepilot-tenants.db"),
            password)
        print(json.dumps(report, sort_keys=True))
        return 0 if report["first_owner_password_verified"] else 2
    except (EOFError, KeyboardInterrupt, OSError,
            permanent_owner_password_proof.OwnerPasswordProofDenied):
        print("Independent owner password not verified; no identity was changed.",
              file=sys.stderr)
        return 2
    finally:
        password = None


if __name__ == "__main__":
    raise SystemExit(main())
