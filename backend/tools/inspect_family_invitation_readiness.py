"""Operator-only read-only check before the FIRST private family invitation.

Run through the EXISTING Render SSH console, not as a web route or deployment
command. No recovery keys or Public API secrets should be passed through stdin,
argv, logs or GitHub. The ephemeral opt-in is not persisted on Render.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import private_family_rollout_preflight as preflight

LEGACY = Path("/data/edgepilot.db")
TENANT = Path("/data/edgepilot-tenants.db")
APPROVAL = "INSPECT PRIVATE FAMILY READINESS ONLY"


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    # Validate every operator option before opening either database.
    if args != ["--approve", APPROVAL]:
        print("Exact read-only operator approval is required.", file=sys.stderr)
        return 2
    if os.environ.get(preflight.AUDIT_FLAG) != "true":
        print("Ephemeral read-only inspection gate is not enabled.", file=sys.stderr)
        return 2
    if (os.environ.get("EDGE_DB_PATH") != str(LEGACY)
            or os.environ.get("EDGE_TENANT_DB_PATH") != str(TENANT)):
        print("Protected paired persistent paths are required.", file=sys.stderr)
        return 2

    # No credentials or file contents are printed even if an unexpected
    # runtime error occurs. A failure NEVER opts in member enrollment.
    try:
        result = preflight.inspect_first_invitation_readiness(
            dict(os.environ), LEGACY, TENANT)
        if (not isinstance(result, dict)
                or result.get("inspection") != "passed"
                or result.get("enrollment_currently_disabled") is not True
                or result.get("member_registration_authorized") is not False
                or result.get("live_trading_enabled") is not False
                or result.get("autonomous_orders_enabled") is not False
                or result.get("bank_transfers_enabled") is not False):
            raise preflight.FamilyRolloutReadinessDenied(
                "Unexpected inspection result")
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        print("Read-only first-invitation inspection DENIED. No settings or "
              "accounts were changed.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
