"""Read phone-held backup key from SSH standard input, never CLI arguments."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import permanent_tenant_owner_backup as backup


def main():
    secret = None
    try:
        if sys.argv[1:] != ["--approve", backup.APPROVAL]:
            print("Explicit nonsecret approval required.", file=sys.stderr)
            return 2
        if (os.getenv("EDGE_DB_PATH") != "/data/edgepilot.db"
                or os.getenv("EDGE_TENANT_DB_PATH") != "/data/edgepilot-tenants.db"):
            print("Existing paid database paths required.", file=sys.stderr)
            return 2
        secret = sys.stdin.readline(170).strip()
        if not secret:
            print("Private backup key missing from SSH standard input.", file=sys.stderr)
            return 2
        name = "edgepilot-tenant-owner-" + datetime.now(timezone.utc).strftime("%Y%m%d") + ".epbk"
        result = backup.create_verified_owner_archive(
            os.environ, "/data/edgepilot.db", "/data/edgepilot-tenants.db",
            Path("/dev/shm") / name, key_b64=secret, approval=backup.APPROVAL)
        print("Verified temporary archive:", name)
        print(json.dumps(result, sort_keys=True))
        print("Copy the ephemeral archive OFF Render and verify SHA-256.")
        return 0
    except (backup.OwnerArchiveDenied, OSError, ValueError):
        print("Owner backup not established. Neither database was modified.",
              file=sys.stderr)
        return 2
    finally:
        secret = None


if __name__ == "__main__":
    raise SystemExit(main())
