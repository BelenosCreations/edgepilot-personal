"""Interactive, opt-in one-time EdgePilot permanent owner bootstrap.

Run ONLY inside the already paid Render service console after documented
backup, validation, tenant schema preparation and account-recovery checks.
Do not supply passwords, tokens or approvals in shell arguments.
"""
from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import permanent_owner_bootstrap


def main():
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("An interactive, trusted operator terminal is required.", file=sys.stderr)
        return 2
    try:
        legacy = os.environ["EDGE_DB_PATH"]
        tenant = os.environ["EDGE_TENANT_DB_PATH"]
        if legacy != "/data/edgepilot.db" or tenant != "/data/edgepilot-tenants.db":
            print("Expected existing paid persistent disk configuration required.", file=sys.stderr)
            return 2
        print("This creates a NEW EdgePilot identity only; it does not migrate brokerage data.")
        label = input("New EdgePilot owner display label: ")
        login = input("New EdgePilot owner login identifier: ")
        password = getpass.getpass("New unique EdgePilot password (14–128 characters): ")
        verify = getpass.getpass("Confirm new password: ")
        approval = getpass.getpass("Type INITIALIZE FIRST EDGEPILOT OWNER to authorize: ")
        if password != verify:
            print("Passwords did not match; nothing changed.", file=sys.stderr)
            return 2
        result = permanent_owner_bootstrap.create_first_owner(
            os.environ, legacy, tenant, label=label, login_name=login,
            password=password, approval=approval)
        if result["created"]:
            print("First EdgePilot owner identity created; old brokerage data was NOT migrated.")
            return 0
    except (KeyError, EOFError, KeyboardInterrupt,
            permanent_owner_bootstrap.OwnerBootstrapDenied):
        print("Owner identity was not created or cannot be verified.", file=sys.stderr)
        return 2
    finally:
        password = None
        verify = None
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
