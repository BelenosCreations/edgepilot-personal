#!/usr/bin/env python3
"""OFFLINE EdgePilot database inspection and migration rehearsal; no live migration.

Default production app never imports or starts this script.
Enable only in a controlled maintenance environment, with explicit confirmation.
NEVER pass a backup encryption key as a CLI argument or commit it to GitHub.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import migration_preflight as safeguards


def main(argv=None):
    p=argparse.ArgumentParser(description="EdgePilot offline migration safety checks (no migration)")
    commands=p.add_subparsers(dest="action",required=True)
    for name in ("inspect","rehearse","backup","restore-test"):
        parser=commands.add_parser(name)
        if name!="restore-test":
            parser.add_argument("--database",required=True,help="Explicit SQLite source path")
        if name in ("backup","restore-test"):
            parser.add_argument("--output",required=True,
                help="Brand-new output path; no overwrite")
        if name=="restore-test":
            parser.add_argument("--archive",required=True,help="Encrypted archive path")
        if name!="inspect":
            parser.add_argument("--approve",required=True,
                help="Required phrase: REHEARSE OFFLINE ONLY")
    args=p.parse_args(argv)
    try:
        if args.action=="inspect":
            result=safeguards.inspect_database(args.database)
        else:
            key=os.getenv("EDGE_BACKUP_KEY_B64","")
            if args.action=="rehearse":
                result=safeguards.rehearse_restore(args.database,key=key,phrase=args.approve)
            elif args.action=="backup":
                result=safeguards.create_encrypted_backup(
                    args.database,args.output,key=key,phrase=args.approve)
            else:
                result=safeguards.restore_encrypted_backup(
                    args.archive,args.output,key=key,phrase=args.approve)
        print(json.dumps(result,indent=2,sort_keys=True))
        return 0
    except (safeguards.MigrationSafetyError, OSError, ValueError) as exc:
        # Only sanitized errors; do not print filesystem paths or secrets.
        if isinstance(exc,safeguards.MigrationSafetyError):
            print("EdgePilot offline safeguard: "+str(exc),file=sys.stderr)
        else:
            print("EdgePilot offline safeguard: operation refused",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
