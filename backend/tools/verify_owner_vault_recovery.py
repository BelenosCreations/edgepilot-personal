"""Manual-only owner vault-key proof. Never prints or logs a credential."""
from __future__ import annotations

import getpass
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import permanent_owner_key_recovery


def main():
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("Trusted interactive operator terminal required.", file=sys.stderr)
        return 2
    candidate = None
    try:
        legacy = os.environ["EDGE_DB_PATH"]
        if legacy != "/data/edgepilot.db":
            print("Only existing paid owner storage may be inspected.", file=sys.stderr)
            return 2
        print("Use your separately saved EDGE_CREDENTIAL_KEY; never your login token.")
        print("No decrypted credential, account ID or key is displayed.")
        approval = input("Type VERIFY OWNER VAULT RECOVERY to approve: ")
        candidate = getpass.getpass("Enter independently held recovery Fernet key: ")
        result = permanent_owner_key_recovery.verify_private_owner_key(
            os.environ, legacy, recovery_key=candidate, approval=approval)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (KeyError, EOFError, KeyboardInterrupt,
            permanent_owner_key_recovery.OwnerKeyRecoveryDenied):
        print("Owner key recovery verification not established.", file=sys.stderr)
        return 2
    finally:
        candidate = None


if __name__ == "__main__":
    raise SystemExit(main())
