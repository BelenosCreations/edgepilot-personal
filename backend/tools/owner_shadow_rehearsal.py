#!/usr/bin/env python3
"""EdgePilot owner migration rehearsal ONLY. No production cutover.

Never pass secrets as arguments. Supply EDGE_CREDENTIAL_KEY through an
approved protected process environment in an isolated, encrypted workspace.
DO NOT run this against /data/edgepilot.db or any active database.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import owner_shadow_migration as shadow


def main(argv=None):
    parser=argparse.ArgumentParser(
        description="Discardable owner-to-tenant shadow migration test (NOT production migration)")
    parser.add_argument("--database",required=True,
                        help="Already restored, isolated SQLite copy; never the live database")
    parser.add_argument("--approve",required=True,
                        help="Required phrase: SHADOW REHEARSAL ONLY")
    args=parser.parse_args(argv)
    try:
        result=shadow.rehearse_owner_shadow(
            args.database,credential_key=os.getenv("EDGE_CREDENTIAL_KEY",""),
            phrase=args.approve)
        print(json.dumps(result,sort_keys=True,indent=2))
        return 0
    except (shadow.ShadowMigrationError,ValueError,OSError) as exc:
        # Avoid leaking internal DB paths/account IDs/keys into logs or terminals.
        if isinstance(exc,shadow.ShadowMigrationError):
            print("EdgePilot migration rehearsal: "+str(exc),file=sys.stderr)
        else:
            print("EdgePilot migration rehearsal refused",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
