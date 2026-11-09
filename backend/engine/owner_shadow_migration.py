"""Offline-only rehearsal of legacy owner -> dormant tenant shadow mapping.

NEVER invoked by Flask, the Android app, Render startup, or automation workers.
It creates a PRIVATE, TEMPORARY, THROWAWAY COPY of an *already isolated*
recovered database, then stages identity/account mapping in that copy only.
It makes no Public API requests, never provisions login credentials, and
never writes to the source database or activates trading.

A real cutover is explicitly NOT implemented or authorized here.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from . import tenant_foundation, account_scope, migration_preflight, historical_reconciliation

ENABLE_FLAG="EDGE_OWNER_MIGRATION_REHEARSAL_ENABLED"
APPROVAL_PHRASE="SHADOW REHEARSAL ONLY"
MAPPED_TABLES=frozenset(("settings","broker_credentials",
                        "account_snapshots","observation_cycles"))
SENSITIVE_WORDS=("secret","password","private_key","credential","access_token","refresh_token")
MAX_SETTINGS=300


class ShadowMigrationError(RuntimeError):
    """Errors intentionally omit account identifiers and sensitive database values."""


def _conn(path,*,readonly=False):
    if readonly:
        db=sqlite3.connect(Path(path).as_uri()+"?mode=ro",uri=True,timeout=30)
        db.execute("PRAGMA query_only=ON")
    else:
        db=sqlite3.connect(str(path),timeout=30)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=30000")
    return db


def _required_tables(con):
    required={"settings","broker_credentials","account_snapshots","observation_cycles"}
    names={r["name"] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if not required.issubset(names):
        raise ShadowMigrationError("Legacy schema incomplete")
    for table in ("tenant_users","tenant_connections","tenant_accounts"):
        if table in names and con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]:
            raise ShadowMigrationError("Existing tenant records require a different migration plan")


def _settings(con):
    entries=list(con.execute("SELECT k,v FROM settings ORDER BY k"))
    if len(entries)>MAX_SETTINGS or len({r["k"] for r in entries})!=len(entries):
        raise ShadowMigrationError("Unexpected settings inventory")
    settings={}
    for row in entries:
        k,v=row["k"],row["v"]
        if (not isinstance(k,str) or not 1<=len(k)<=100 or
            not isinstance(v,str) or len(v)>4096 or
            any(word in k.casefold() for word in SENSITIVE_WORDS)):
            raise ShadowMigrationError("Unsupported or potentially sensitive setting key")
        settings[k]=v
    return settings


def _validate_account(con,settings,credential_key):
    account=settings.get("account_id","").strip()
    if not 1<=len(account)<=128 or any(c in account for c in "\r\n\0"):
        raise ShadowMigrationError("Selected legacy account unavailable")
    rows=list(con.execute(
        "SELECT provider,ciphertext FROM broker_credentials WHERE provider='public'"))
    if len(rows)!=1 or rows[0]["ciphertext"] is None:
        raise ShadowMigrationError("Encrypted Public connection unavailable")
    if not credential_key:
        raise ShadowMigrationError("Credential recovery key unavailable")
    try:
        f=Fernet(credential_key.encode("ascii") if isinstance(credential_key,str) else credential_key)
        plaintext=f.decrypt(rows[0]["ciphertext"])
    except (ValueError,TypeError,InvalidToken,UnicodeError):
        raise ShadowMigrationError("Legacy credential verification failed") from None
    if not 20<=len(plaintext)<=2048:
        raise ShadowMigrationError("Legacy credential verification failed")
    # No decrypted secret is returned, written, displayed, or sent to a provider.
    del plaintext
    for row in con.execute("SELECT DISTINCT account FROM account_snapshots"):
        if row["account"]!=account:
            raise ShadowMigrationError("Multiple account references in legacy snapshots")
    # Unscoped orders/sync tables may contain other accounts. Explicitly reject
    # conflicting account references rather than silently misattributing them.
    for table in ("orders","sync_runs","sync_transactions"):
        exists=con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                           (table,)).fetchone()
        if not exists:continue
        columns={r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
        if "account" in columns:
            row=con.execute(f"SELECT 1 FROM {table} WHERE account IS NOT NULL"
                            " AND account!='' AND account!=? LIMIT 1",(account,)).fetchone()
            if row:
                raise ShadowMigrationError("Conflicting account ownership found in legacy records")
    return account,rows[0]["ciphertext"]


def _install_shadow_tables(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS tenant_shadow_settings (
        user_id TEXT NOT NULL,
        account_id TEXT NOT NULL,
        source_key TEXT NOT NULL,
        source_value TEXT NOT NULL,
        PRIMARY KEY(user_id,account_id,source_key),
        FOREIGN KEY(account_id,user_id)
          REFERENCES tenant_accounts(account_id,user_id)
    );
    CREATE TABLE IF NOT EXISTS tenant_shadow_lineage (
        user_id TEXT NOT NULL,
        account_id TEXT NOT NULL,
        source_table TEXT NOT NULL CHECK(source_table IN
          ('account_snapshots','observation_cycles')),
        source_id INTEGER NOT NULL,
        target_id INTEGER NOT NULL,
        PRIMARY KEY(user_id,account_id,source_table,source_id),
        FOREIGN KEY(account_id,user_id)
          REFERENCES tenant_accounts(account_id,user_id)
    );
    CREATE TABLE IF NOT EXISTS tenant_shadow_rehearsal_marker (
        id INTEGER PRIMARY KEY CHECK(id=1),
        source_schema_sha256 TEXT NOT NULL,
        source_account_sha256 TEXT NOT NULL,
        staging_state TEXT NOT NULL CHECK(staging_state='REHEARSED_ONLY'),
        created_at TEXT NOT NULL
    );
    """)


def _stage(conn,credential_key,source_report):
    _required_tables(conn)
    settings=_settings(conn)
    source_account,ciphertext=_validate_account(conn,settings,credential_key)
    tenant_foundation.setup(conn.execute("PRAGMA database_list").fetchone()["file"])
    account_scope.setup(conn.execute("PRAGMA database_list").fetchone()["file"])
    _install_shadow_tables(conn)
    historical_reconciliation.prepare(conn)
    # A new transaction contains all mapping writes. Never create working
    # sessions or activate the real account/worker.
    conn.execute("BEGIN IMMEDIATE")
    profile=settings.get("profile_label","My EdgePilot").strip() or "My EdgePilot"
    if len(profile)>64:raise ShadowMigrationError("Invalid legacy owner label")
    user_id,connection_id,account_id=(str(uuid.uuid4()) for _ in range(3))
    now=datetime.now(timezone.utc).isoformat()
    conn.execute("""INSERT INTO tenant_users(user_id,label,role,created_at)
        VALUES(?,?,'owner',?)""",(user_id,profile,now))
    conn.execute("""INSERT INTO tenant_connections
        (connection_id,user_id,provider,credential_ciphertext,created_at)
        VALUES(?,?,'public',?,?)""",(connection_id,user_id,ciphertext,now))
    conn.execute("""INSERT INTO tenant_accounts
        (account_id,user_id,connection_id,provider,provider_account_ref,label,created_at)
        VALUES(?,?,?,'public',?,?,?)""",
        (account_id,user_id,connection_id,source_account,profile,now))
    conn.execute("""INSERT INTO tenant_runtime_status
        (user_id,account_id,requested_mode,worker_enabled,paper_enabled,live_enabled)
        VALUES(?,?,'observe',0,0,0)""",(user_id,account_id))
    for k,v in settings.items():
        conn.execute("""INSERT INTO tenant_shadow_settings
            (user_id,account_id,source_key,source_value) VALUES(?,?,?,?)""",
            (user_id,account_id,k,v))
    conn.execute("""INSERT INTO tenant_account_settings
        (user_id,account_id,setting_key,setting_value)
        VALUES(?,?,'profile_label',?)""",(user_id,account_id,profile))

    snapshot_count=0
    for row in conn.execute("""SELECT id,ts,total_value,buying_power
        FROM account_snapshots ORDER BY id""").fetchall():
        try:
            # Preserve original source strings in the legacy table; target is
            # normalized to cents so scoped summaries can parse safely.
            value=account_scope._money(row["total_value"])
            buying=account_scope._money(row["buying_power"])
            stamp=datetime.fromisoformat(row["ts"].replace("Z","+00:00"))
            if stamp.tzinfo is None:raise ValueError()
        except (ValueError,AttributeError,TypeError):
            raise ShadowMigrationError("Unsupported historical portfolio snapshot") from None
        cur=conn.execute("""INSERT INTO tenant_portfolio_snapshots
            (user_id,account_id,captured_at,provider_timestamp,account_value,buying_power)
            VALUES(?,?,?,?,?,?)""",(user_id,account_id,stamp.isoformat(),
                                     stamp.isoformat(),value,buying))
        conn.execute("""INSERT INTO tenant_shadow_lineage
            (user_id,account_id,source_table,source_id,target_id)
            VALUES(?,?,'account_snapshots',?,?)""",
            (user_id,account_id,row["id"],cur.lastrowid))
        snapshot_count+=1

    cycle_count=0
    for row in conn.execute("""SELECT * FROM observation_cycles ORDER BY id""").fetchall():
        try:
            symbols=account_scope._symbols(json.loads(row["symbols_json"]))
            mode,state,session=row["mode"],row["state"],row["market_session"]
            if (mode not in ("observe","paper") or
                state not in account_scope._ALLOWED_STATES or
                session not in account_scope._ALLOWED_SESSIONS):
                raise ValueError()
            accepted,rejected=row["quotes_accepted"],row["quotes_rejected"]
            age=row["quote_age_seconds"]
            if (not isinstance(accepted,int) or accepted<0 or
                not isinstance(rejected,int) or rejected<0 or
                age is not None and (not isinstance(age,int) or not 0<=age<=86400)):
                raise ValueError()
            stamp=datetime.fromisoformat(row["completed_at"].replace("Z","+00:00"))
            if stamp.tzinfo is None:raise ValueError()
        except (ValueError,TypeError,AttributeError,KeyError):
            raise ShadowMigrationError("Unsupported historical observation cycle") from None
        cur=conn.execute("""INSERT INTO tenant_observation_cycles
            (user_id,account_id,completed_at,mode,state,market_session,
             symbols_json,accepted,rejected,oldest_quote_age_seconds,issue)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id,account_id,stamp.isoformat(),mode,state,session,
             json.dumps(symbols),accepted,rejected,age,row["issue"]))
        conn.execute("""INSERT INTO tenant_shadow_lineage
            (user_id,account_id,source_table,source_id,target_id)
            VALUES(?,?,'observation_cycles',?,?)""",
            (user_id,account_id,row["id"],cur.lastrowid))
        cycle_count+=1

    history=historical_reconciliation.reconcile(
        conn,source_report["tableCounts"],source_account,user_id,account_id)
    digest=hashlib.sha256(source_account.encode("utf-8")).hexdigest()
    conn.execute("""INSERT INTO tenant_shadow_rehearsal_marker
        (id,source_schema_sha256,source_account_sha256,staging_state,created_at)
        VALUES(1,?,?,'REHEARSED_ONLY',?)""",
        (source_report["schemaSha256"],digest,now))
    if (conn.execute("PRAGMA foreign_key_check").fetchone() is not None or
        conn.execute("SELECT COUNT(*) FROM tenant_shadow_settings").fetchone()[0]!=len(settings) or
        conn.execute("SELECT COUNT(*) FROM tenant_shadow_lineage").fetchone()[0]!=
                    snapshot_count+cycle_count or
        conn.execute("""SELECT COUNT(*) FROM tenant_runtime_status WHERE
            worker_enabled!=0 OR paper_enabled!=0 OR live_enabled!=0
            OR requested_mode!='observe'""").fetchone()[0]):
        raise ShadowMigrationError("Staged mapping verification failed")
    conn.commit()
    return {"snapshotRowsMapped":snapshot_count,
            "observationRowsMapped":cycle_count,
            "settingsQuarantined":len(settings),
            "brokerCredentialCiphertextCopied":True,
            "credentialVerifiedWithoutDisclosure":True,
            "newIdentitySessions":0,
            "historicalReconciliation":history,
            "workerEnabled":False,"paperEnabled":False,"liveEnabled":False,
            "pendingHistoricalTables":sorted(
                name for name in source_report["tableCounts"]
                if name not in MAPPED_TABLES and not name.startswith("tenant_")),
            "stagingOnly":True,"cutoverReady":False}


def rehearse_owner_shadow(source_db, *, credential_key, phrase):
    """Rehearse against an isolated restored DB; source never opened read-write."""
    if os.getenv(ENABLE_FLAG,"false").lower()!="true" or phrase!=APPROVAL_PHRASE:
        raise ShadowMigrationError("Offline shadow rehearsal is disabled")
    try:
        path=Path(source_db).expanduser().resolve(strict=True)
    except (OSError,ValueError):
        raise ShadowMigrationError("Isolated source file missing") from None
    # Prevent accidentally targeting the known live Render persistent volume.
    if path==Path("/data") or Path("/data") in path.parents:
        raise ShadowMigrationError("Live Render volume is not a rehearsal source")
    if not path.is_file():
        raise ShadowMigrationError("Expected an isolated SQLite file")
    try:
        before=migration_preflight.inspect_database(path)
        with tempfile.TemporaryDirectory(prefix="edgepilot-shadow-rehearsal-") as root:
            work=Path(root)/"shadow.db"
            with _conn(path,readonly=True) as src, _conn(work) as dest:
                src.backup(dest)
            os.chmod(work,0o600)
            snapshot_report=migration_preflight.inspect_database(work)
            if before!=snapshot_report:
                raise ShadowMigrationError("Isolated source changed during snapshot")
            with _conn(work) as stage:
                report=_stage(stage,credential_key,before)
            shadow=migration_preflight.inspect_database(work)
            if shadow["integrity"]!="ok" or shadow["foreignKeys"]!="ok":
                raise ShadowMigrationError("Shadow database failed integrity validation")
            after=migration_preflight.inspect_database(path)
            if after!=before:
                raise ShadowMigrationError("Isolated source changed during rehearsal")
            return {**report,"sourceLogicalInventoryUnchanged":True,
                "isolatedIntegrityVerified":True,
                "sourceSchemaSha256":before["schemaSha256"],
                "originalTableCounts":before["tableCounts"],
                "migrationExecutedOnProduction":False,
                "productionDatabaseChanged":False,
                "tenantActivationAuthorized":False}
    except ShadowMigrationError:
        raise
    except (sqlite3.Error,OSError,ValueError,TypeError,KeyError):
        raise ShadowMigrationError("Shadow rehearsal failed; source remains untouched") from None
