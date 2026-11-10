"""Inactive, tenant-scoped *summaries* of allowlisted historical source records.

Only the offline /dev/shm shadow rehearsal imports this module. Records are
not brokerage-confirmed executions, are not traded, and cannot be promoted.
No raw provider JSON, order messages, bank details, tokens or credentials
are copied. A source that cannot be fully validated stays reference-only.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from . import tenant_history
from .tenant_foundation import TenantAccessError
from .account_scope import AccountScopeStore

TRANSACTION_TABLES=frozenset(("sync_transactions",))
BROKER_TABLES=frozenset(("broker_fills","observed_orders","observed_trades"))
AUDIT_TABLES=frozenset(("sync_runs","sync_alerts","order_audit_runs","order_audit_alerts"))
SUPPORTED_TABLES=TRANSACTION_TABLES | BROKER_TABLES | AUDIT_TABLES
_REQUIRED={
    "sync_transactions":frozenset(("tx_id","timestamp","symbol","side","type","subtype")),
    "broker_fills":frozenset(("id","symbol","side","quantity","price","fee","source","timestamp")),
    "observed_orders":frozenset(("order_id","symbol","side","status","created_at")),
    "observed_trades":frozenset(("trade_id","symbol","side","quantity","price","timestamp")),
    "sync_runs":frozenset(("ts","status")),
    "sync_alerts":frozenset(("created","kind","state")),
    "order_audit_runs":frozenset(("ts","state")),
    "order_audit_alerts":frozenset(("created","kind","state")),
}
_SYMBOL=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,79}$")


class DetailSafetyError(RuntimeError):
    """Never includes values from the original brokerage database."""


class UnsupportedDetail(ValueError):
    """Record is intentionally left reference-only, rather than guessed."""


def _label(value, limit=96, *, required=False):
    if value is None or value=="":
        if required:raise UnsupportedDetail()
        return None
    if not isinstance(value,str) or len(value)>limit or not value.strip() or any(
        ord(c)<32 or ord(c)==127 for c in value):
        raise UnsupportedDetail()
    return value


def _symbol(value):
    value=_label(value,80)
    if value is not None and not _SYMBOL.fullmatch(value):
        raise UnsupportedDetail()
    return value


def _timestamp(value):
    value=_label(value,64,required=True)
    try:
        dt=datetime.fromisoformat(value.replace("Z","+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None or not 1900<=dt.year<=2100:
            raise UnsupportedDetail()
        return dt.isoformat()
    except (TypeError,ValueError,OverflowError):
        raise UnsupportedDetail() from None


def _money(value, *, positive=False):
    try:
        number=Decimal(str(value))
        if (not number.is_finite() or
            number<0 or (positive and number==0) or
            number>Decimal("1000000000000")):
            raise UnsupportedDetail()
        return str(number)
    except (InvalidOperation,TypeError,ValueError):
        raise UnsupportedDetail() from None


def _digest_ref(value):
    value=_label(value,512,required=True)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def prepare(con):
    """Create only new tenant-scoped, status-locked summary tables."""
    con.executescript("""
    CREATE TABLE IF NOT EXISTS tenant_history_transaction_details(
        reference_id INTEGER NOT NULL,
        user_id TEXT NOT NULL,
        account_id TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        identifier_sha256 TEXT NOT NULL CHECK(length(identifier_sha256)=64),
        symbol TEXT,
        side_label TEXT,
        type_label TEXT,
        subtype_label TEXT,
        validation_state TEXT NOT NULL DEFAULT 'SOURCE_ONLY_UNVERIFIED'
          CHECK(validation_state='SOURCE_ONLY_UNVERIFIED'),
        PRIMARY KEY(reference_id,user_id,account_id),
        FOREIGN KEY(reference_id,user_id,account_id)
          REFERENCES tenant_history_references(reference_id,user_id,account_id)
    );
    CREATE TABLE IF NOT EXISTS tenant_history_broker_details(
        reference_id INTEGER NOT NULL,
        user_id TEXT NOT NULL,
        account_id TEXT NOT NULL,
        activity_kind TEXT NOT NULL CHECK(activity_kind IN
          ('broker_fills','observed_orders','observed_trades')),
        occurred_at TEXT NOT NULL,
        identifier_sha256 TEXT NOT NULL CHECK(length(identifier_sha256)=64),
        symbol TEXT,
        side_label TEXT,
        status_label TEXT,
        quantity_label TEXT,
        price_label TEXT,
        fee_label TEXT,
        validation_state TEXT NOT NULL DEFAULT 'SOURCE_ONLY_UNVERIFIED'
          CHECK(validation_state='SOURCE_ONLY_UNVERIFIED'),
        PRIMARY KEY(reference_id,user_id,account_id),
        FOREIGN KEY(reference_id,user_id,account_id)
          REFERENCES tenant_history_references(reference_id,user_id,account_id)
    );
    CREATE TABLE IF NOT EXISTS tenant_history_audit_details(
        reference_id INTEGER NOT NULL,
        user_id TEXT NOT NULL,
        account_id TEXT NOT NULL,
        audit_kind TEXT NOT NULL CHECK(audit_kind IN
          ('sync_runs','sync_alerts','order_audit_runs','order_audit_alerts')),
        occurred_at TEXT NOT NULL,
        status_label TEXT,
        event_label TEXT,
        validation_state TEXT NOT NULL DEFAULT 'SOURCE_ONLY_UNVERIFIED'
          CHECK(validation_state='SOURCE_ONLY_UNVERIFIED'),
        PRIMARY KEY(reference_id,user_id,account_id),
        FOREIGN KEY(reference_id,user_id,account_id)
          REFERENCES tenant_history_references(reference_id,user_id,account_id)
    );
    """)


def _stage_one(con, source, ref):
    """Allowlist source fields only; never copy raw_json, messages or account IDs."""
    table=ref["source_table"]
    user,acct,rid=ref["user_id"],ref["account_id"],ref["reference_id"]
    if table=="sync_transactions":
        con.execute("""INSERT INTO tenant_history_transaction_details(
            reference_id,user_id,account_id,occurred_at,identifier_sha256,
            symbol,side_label,type_label,subtype_label)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (rid,user,acct,_timestamp(source["timestamp"]),
             _digest_ref(source["tx_id"]),_symbol(source["symbol"]),
             _label(source["side"]),_label(source["type"]),
             _label(source["subtype"])))
    elif table in BROKER_TABLES:
        identifier_field={"broker_fills":"id",
                          "observed_orders":"order_id",
                          "observed_trades":"trade_id"}[table]
        time_field={"broker_fills":"timestamp","observed_orders":"created_at",
                    "observed_trades":"timestamp"}[table]
        if table=="broker_fills":
            side=_label(source["side"],required=True)
            if side not in ("BUY","SELL") or source["source"] not in ("EDGEPILOT","EXTERNAL"):
                raise UnsupportedDetail()
            qty,price,fee=_money(source["quantity"],positive=True),_money(
                source["price"],positive=True),_money(source["fee"])
            status="SOURCE_LABEL_"+source["source"]
        elif table=="observed_trades":
            side=_label(source["side"],required=True)
            if side not in ("BUY","SELL"):raise UnsupportedDetail()
            qty,price,fee=_money(source["quantity"],positive=True),_money(
                source["price"],positive=True),None
            status=None
        else:
            side=_label(source["side"])
            qty,price,fee=None,None,None
            status=_label(source["status"])
        con.execute("""INSERT INTO tenant_history_broker_details(
            reference_id,user_id,account_id,activity_kind,occurred_at,
            identifier_sha256,symbol,side_label,status_label,quantity_label,
            price_label,fee_label)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (rid,user,acct,table,_timestamp(source[time_field]),
             _digest_ref(source[identifier_field]),_symbol(source["symbol"]),
             side,status,qty,price,fee))
    elif table in AUDIT_TABLES:
        stamp="ts" if table.endswith("_runs") else "created"
        state="status" if table=="sync_runs" else "state"
        category=source["kind"] if table.endswith("_alerts") else None
        con.execute("""INSERT INTO tenant_history_audit_details(
            reference_id,user_id,account_id,audit_kind,occurred_at,
            status_label,event_label) VALUES(?,?,?,?,?,?,?)""",
            (rid,user,acct,table,_timestamp(source[stamp]),
             _label(source[state]),_label(category)))
    else:
        raise UnsupportedDetail()


def stage(con, *, user_id,account_id, expected_references):
    """Only rows already provisionally scoped by v0.2.14 can be summarized.

    All data writes are inside the caller's disposable shadow transaction.
    Incomplete/invalid records remain reference-only and are counted as
    pending, never silently 'fixed', dropped or assumed to be filled orders.
    """
    if not isinstance(expected_references,int) or expected_references<0:
        raise DetailSafetyError("Invalid expected history count")
    refs=con.execute("""SELECT r.reference_id,r.source_table,r.source_rowid,
        r.source_sha256,r.user_id,r.account_id
        FROM tenant_history_references r
        WHERE r.user_id=? AND r.account_id=?
          AND r.record_state='REFERENCE_ONLY'
        ORDER BY r.reference_id""",(user_id,account_id)).fetchall()
    if len(refs)!=expected_references:
        raise DetailSafetyError("Historical reference count mismatch")
    staged={"transactionSummaries":0,"brokerActivitySummaries":0,"auditSummaries":0}
    unsupported=0
    for ref in refs:
        table=ref["source_table"]
        if table not in SUPPORTED_TABLES:
            unsupported+=1
            continue
        columns={r["name"] for r in con.execute(
            "PRAGMA table_info("+ '"'+table+'"'+")")}
        if not _REQUIRED[table].issubset(columns):
            unsupported+=1
            continue
        source=con.execute("SELECT * FROM "+'"'+table+'"'+
                           " WHERE rowid=?",(ref["source_rowid"],)).fetchone()
        if source is None:
            raise DetailSafetyError("Source history missing")
        from .historical_reconciliation import _digest
        if _digest(source)!=ref["source_sha256"] or source["account"] is None:
            raise DetailSafetyError("Source history provenance mismatch")
        owner=con.execute("""SELECT provider_account_ref
            FROM tenant_accounts WHERE user_id=? AND account_id=?""",
            (user_id,account_id)).fetchone()
        if owner is None or source["account"]!=owner["provider_account_ref"]:
            raise DetailSafetyError("History reference owner mismatch")
        try:
            _stage_one(con,source,ref)
        except UnsupportedDetail:
            unsupported+=1
            continue
        staged[("transactionSummaries" if table in TRANSACTION_TABLES
                else "brokerActivitySummaries" if table in BROKER_TABLES
                else "auditSummaries")]+=1

    rows_staged=sum(staged.values())
    for target,key in (
        ("tenant_history_transaction_details","transactionSummaries"),
        ("tenant_history_broker_details","brokerActivitySummaries"),
        ("tenant_history_audit_details","auditSummaries"),
    ):
        count=con.execute("SELECT COUNT(*) FROM "+target+
                          " WHERE user_id=? AND account_id=?",
                          (user_id,account_id)).fetchone()[0]
        if count!=staged[key]:
            raise DetailSafetyError("Typed history reconciliation mismatch")
    if rows_staged+unsupported!=expected_references:
        raise DetailSafetyError("Historical summaries incomplete")
    if con.execute("PRAGMA foreign_key_check").fetchone():
        raise DetailSafetyError("Typed history owner foreign key failed")
    return {**staged,"referenceOnlyOrUnsupportedRows":unsupported,
            "totalReferencesPreserved":expected_references,
            "supportedSummariesStaged":rows_staged,
            "allReferencedRowsAccountMatched":True,
            "sourceOnlyNotBrokerVerified":True,
            "rawBrokerJsonCopied":False,"fullHistoryPayloadMigrated":False,
            "userSessionsCreated":0,"workerActivated":False,
            "cutoverReady":False}


class DormantDetailsReader:
    """Scoped, non-executable summary reader; not wired to HTTP or workers."""

    def __init__(self,path,identity_store):
        self.path=str(path)
        self.identity_store=identity_store

    def summary(self,session_token,account_id):
        principal=self.identity_store.principal(session_token)
        if principal is None or not principal.get("user_id"):
            raise TenantAccessError("Identity session unavailable")
        user_id=principal["user_id"]
        with tenant_history._db(self.path) as con:
            AccountScopeStore._check(con,user_id,account_id)
            groups={}
            for table,key in (
                ("tenant_history_transaction_details","transactions"),
                ("tenant_history_broker_details","brokerActivity"),
                ("tenant_history_audit_details","audits"),
            ):
                groups[key]=con.execute("SELECT COUNT(*) FROM "+table+
                  " WHERE user_id=? AND account_id=?",(user_id,account_id)).fetchone()[0]
        return {"counts":groups,"sourceOnlyNotBrokerVerified":True,
                "canTrade":False,"transfersEnabled":False}
