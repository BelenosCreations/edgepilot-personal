"""Inactive Phase 6 ledger: strictly trace every legacy history row in a shadow DB.

An explicit account column equal to the verified selected broker account is
ownership EVIDENCE, not proof that an order was filled, realized P&L exists,
or permission to run any engine. Unscoped or ambiguous records are quarantined.
Only called by the offline Phase 5 disposable shadow rehearsal. No production
routes, workers, accounts, orders or broker interfaces use this module.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3

# These tables have an explicit account column in released EdgePilot schemas.
# Snapshot & cycles already have their own Phase 5 mapping; still get a
# source-row provenance record in this separate reconciliation index.
ACCOUNT_LABELED = frozenset((
    "account_snapshots", "attributed_positions", "broker_fills",
    "interventions", "observed_orders", "observed_trades",
    "order_audit_alerts", "order_audit_runs", "orders", "scan_runs",
    "submitted_order_provenance", "sync_alerts", "sync_runs",
    "sync_snapshots", "sync_transactions",
))
ALREADY_SHADOW_MAPPED = frozenset(("account_snapshots", "observation_cycles"))
# Legacy tables that have no reliable account owner. KEEP the original data
# intact and quarantine it, even in a single-user source.
UNSCOPED = frozenset((
    "activity", "ai_runs", "automation_engines", "automation_events",
    "automation_highwater", "automation_master", "automation_quotes",
    "automation_worker_lease", "discovery_config", "engine_configs",
    "ledger_meta", "observation_cycles", "paper_positions", "scan_config",
    "watch",
))
# System or secret tables are not ever copied into history archives.
SYSTEM = frozenset(("broker_credentials", "edge_sessions", "edge_login_failures",
                    "settings"))
KNOWN = ACCOUNT_LABELED | UNSCOPED | SYSTEM
UNACCOUNTED = "UNKNOWN_REVIEW"
EXPLICIT = "ACCOUNT_LABEL_VERIFIED"
QUARANTINE = "NO_ACCOUNT_EVIDENCE"
AMBIGUOUS = "BLANK_ACCOUNT_REFERENCE"
PREMAPPED = "ALREADY_SHADOW_MAPPED"
SECRET = "SYSTEM_EXCLUDED"
VALID_CLASSES = frozenset((UNACCOUNTED, EXPLICIT, QUARANTINE, AMBIGUOUS,
                           PREMAPPED, SECRET))


class HistoryReconciliationError(RuntimeError):
    """Sanitized fail-closed error. No underlying data or account IDs."""


def _q(table):
    if not isinstance(table, str) or not 1 <= len(table) <= 80 or not all(
            c.isascii() and (c.isalnum() or c == "_") for c in table):
        raise HistoryReconciliationError("Invalid history table name")
    return '"' + table + '"'


def _digest(row):
    # Hash row content for internal provenance only. The values, digests and
    # source row IDs never leave the temporary working copy.
    def norm(item):
        if isinstance(item, bytes):
            return {"blobB64":base64.b64encode(item).decode("ascii")}
        if isinstance(item, (str,int,float,bool)) or item is None:
            return item
        raise HistoryReconciliationError("Unsupported history data type")
    payload=json.dumps([(key,norm(row[key])) for key in row.keys()],
                       ensure_ascii=True,separators=(",",":"),allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prepare(con):
    """Initialize additive shadow-only tables before BEGIN IMMEDIATE."""
    con.executescript("""
        CREATE TABLE IF NOT EXISTS tenant_shadow_history_index (
            source_table TEXT NOT NULL,
            source_rowid INTEGER NOT NULL,
            source_sha256 TEXT NOT NULL CHECK(length(source_sha256)=64),
            classification TEXT NOT NULL CHECK(classification IN (
              'UNKNOWN_REVIEW','ACCOUNT_LABEL_VERIFIED','NO_ACCOUNT_EVIDENCE',
              'BLANK_ACCOUNT_REFERENCE','ALREADY_SHADOW_MAPPED',
              'SYSTEM_EXCLUDED')),
            user_id TEXT,
            account_id TEXT,
            PRIMARY KEY(source_table,source_rowid),
            CHECK ((classification='ACCOUNT_LABEL_VERIFIED' OR
                    classification='ALREADY_SHADOW_MAPPED') =
                   (user_id IS NOT NULL AND account_id IS NOT NULL)),
            FOREIGN KEY(account_id,user_id)
                REFERENCES tenant_accounts(account_id,user_id)
        );
        CREATE TABLE IF NOT EXISTS tenant_shadow_history_inventory (
            source_table TEXT PRIMARY KEY,
            recorded_count INTEGER NOT NULL CHECK(recorded_count>=0),
            verified_account_count INTEGER NOT NULL CHECK(verified_account_count>=0),
            quarantined_count INTEGER NOT NULL CHECK(quarantined_count>=0),
            unexplained_count INTEGER NOT NULL CHECK(unexplained_count>=0),
            CHECK(recorded_count=verified_account_count+
                  quarantined_count+unexplained_count)
        );
    """)


def reconcile(con,source_table_counts,selected_account,user_id,account_id):
    """Require complete per-row reconciliation without assuming ownership.

    Caller has already checked the Public credential and established the
    dormant owner/account in the SAME disposable DB and transaction.
    """
    if not selected_account or not user_id or not account_id:
        raise HistoryReconciliationError("Verified scope required")
    result={}
    for name,expected in sorted(source_table_counts.items()):
        if name.startswith("tenant_") or name.startswith("sqlite_"):
            continue
        table=_q(name)
        schema=con.execute("SELECT sql FROM sqlite_master WHERE name=? AND type='table'",
                           (name,)).fetchone()
        if schema is None:
            raise HistoryReconciliationError("Historical table missing")
        if "WITHOUT ROWID" in (schema["sql"] or "").upper():
            raise HistoryReconciliationError("Unsupported row-identifier scheme")
        columns={r["name"] for r in con.execute("PRAGMA table_info("+table+")")}
        if name in ACCOUNT_LABELED and "account" not in columns:
            raise HistoryReconciliationError("Account column missing")
        if name in UNSCOPED and "account" in columns:
            raise HistoryReconciliationError("Unexpected account column in unscoped table")
        counts={"verified":0,"quarantined":0,"unexplained":0}
        scanned=0
        # SELECT rowid, * works for all released SQLite tables except WITHOUT ROWID.
        for row in con.execute("SELECT rowid AS _shadow_source_rowid, * FROM "+table):
            scanned+=1
            rowid=row["_shadow_source_rowid"]
            if not isinstance(rowid,int):
                raise HistoryReconciliationError("Unsupported source row ID")
            if name in SYSTEM:
                classification=SECRET
            elif name in ACCOUNT_LABELED:
                reference=row["account"]
                if reference is None or reference == "":
                    classification=AMBIGUOUS
                elif reference!=selected_account:
                    raise HistoryReconciliationError(
                        "Conflicting account reference in historical records")
                else:
                    classification=PREMAPPED if name in ALREADY_SHADOW_MAPPED else EXPLICIT
            elif name in UNSCOPED:
                classification=PREMAPPED if name in ALREADY_SHADOW_MAPPED else QUARANTINE
            else:
                classification=UNACCOUNTED
            verified=classification in (EXPLICIT, PREMAPPED)
            if verified:
                counts["verified"]+=1
            elif classification==UNACCOUNTED:
                counts["unexplained"]+=1
            else:
                counts["quarantined"]+=1
            con.execute("""INSERT INTO tenant_shadow_history_index
                (source_table,source_rowid,source_sha256,classification,user_id,account_id)
                VALUES(?,?,?,?,?,?)""",
                (name,rowid,_digest(row),classification,
                 user_id if verified else None,account_id if verified else None))
        if scanned!=expected:
            raise HistoryReconciliationError("Historical table row count changed")
        con.execute("""INSERT INTO tenant_shadow_history_inventory
            (source_table,recorded_count,verified_account_count,
             quarantined_count,unexplained_count)
            VALUES(?,?,?,?,?)""",
            (name,scanned,counts["verified"],counts["quarantined"],counts["unexplained"]))
        result[name]={"rows":scanned,**counts}
    actual=con.execute("SELECT COUNT(*) n FROM tenant_shadow_history_index").fetchone()["n"]
    expected=sum(v["rows"] for v in result.values())
    if actual!=expected:
        raise HistoryReconciliationError("Historical reconciliation incomplete")
    if con.execute("PRAGMA foreign_key_check").fetchone():
        raise HistoryReconciliationError("History ownership foreign key failed")
    return {
        "tablesInventoried":len(result),
        "rowsInventoried":expected,
        "accountLabeledRows":sum(v["verified"] for v in result.values()),
        "quarantinedRows":sum(v["quarantined"] for v in result.values()),
        "unexplainedRows":sum(v["unexplained"] for v in result.values()),
        "accountLabeledTables":sorted(k for k,v in result.items() if v["verified"]),
        "quarantinedTables":sorted(k for k,v in result.items() if v["quarantined"]),
        "unknownTablesNeedingReview":sorted(k for k,v in result.items() if v["unexplained"]),
        "allRowsInventoried":True,
        "historicalRowsActivated":False,
        "ordersOrFillsInferred":False,
        "fullHistoryMigrated":False,
        "cutoverReady":False,
    }
