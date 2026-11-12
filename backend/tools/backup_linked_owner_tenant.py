"""Private recovery snapshot of a verified linked Public owner. SSH stdin key."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import permanent_tenant_linked_backup as backup


def main():
    secret = None
    try:
        if sys.argv[1:] != ["--approve", backup.APPROVAL]:
            print("Exact nonsecret linked-backup approval is required.",
                  file=sys.stderr)
            return 2
        if (os.getenv("EDGE_DB_PATH") != "/data/edgepilot.db" or
                os.getenv("EDGE_TENANT_DB_PATH") != "/data/edgepilot-tenants.db"):
            print("The existing paired paid-disk paths are required.",
                  file=sys.stderr)
            return 2
        secret = sys.stdin.readline(170).strip()
        if not secret:
            print("Offline backup key was not received through SSH stdin.",
                  file=sys.stderr)
            return 2
        filename = ("edgepilot-tenant-linked-" +
                    datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ") +
                    ".epbk")
        report = backup.create_linked_owner_backup(
            dict(os.environ),
            Path("/data/edgepilot.db"),
            Path("/data/edgepilot-tenants.db"),
            Path("/dev/shm") / filename,
            key_b64=secret, approval=backup.APPROVAL)
        print("Verified temporary archive:", filename)
        print(json.dumps(report, sort_keys=True))
        print("Temporary on Render: copy encrypted archive off-service and compare SHA-256.")
        return 0
    except (backup.LinkedOwnerBackupDenied, OSError, ValueError):
        print("Linked owner backup was denied. Existing databases not changed.",
              file=sys.stderr)
        return 2
    finally:
        secret = None


if __name__ == "__main__":
    raise SystemExit(main())
