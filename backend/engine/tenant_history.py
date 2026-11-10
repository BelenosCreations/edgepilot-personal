"""Dormant, tenant-scoped immutable history references for future account access.

This is intentionally a PROVENANCE-ONLY store, not migrated trade/order payload.
No old row is implicitly treated as a confirmed fill or tradable position.
No Flask route, Render worker, banking flow or broker adapter imports this.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from .tenant_foundation import TenantAccessError
from .account_scope import AccountScopeStore
from . import historical_reconciliation as history

KINDS = {
    "account_snapshots":"PORTFOLIO_SNAPSHOT",
    "attributed_positions":"BROKER_POSITION_REFERENCE",
    "broker_fills":"BROKER_FILL_REFERENCE",
    "interventions":"RISK_AUDIT_REFERENCE",
    "observed_orders":"BROKER_ORDER_OBSERVATION",
    "observed_trades":"BROKER_TRADE_OBSERVATION",
    "order_audit_alerts":"ORDER_AUDIT_REFERENCE",
    "order_audit_runs":"ORDER_AUDIT_REFERENCE",
    "orders":"LOCAL_ORDER_REFERENCE",
    "scan_runs":"MARKET_SCAN_REFERENCE",
    "submitted_order_provenance":"ORDER_PROVENANCE_REFERENCE",
    "sync_alerts":"BROKER_SYNC_REFERENCE",
    "sync_runs":"BROKER_SYNC_REFERENCE",
    "sync_snapshots":"BROKER_SYNC_REFERENCE",
    "sync_transactions":"BROKER_TRANSACTION_REFERENCE",
}
CATEGORIES = tuple(sorted(set(KINDS.values())))
STAGED_STATE = "REFERENCE_ONLY"


class TenantHistoryError(RuntimeError):
    """Sanitized error: never displays account names, credentials or source rows."""


def _db(path):
    con = sqlite3.connect(str(path), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=30000")
    return con


def prepare(con):
    """Add new dormant tables inside a disposable shadow SQLite database.

    The caller must have set up the tenant identity/account schema already.
    This helper never creates an active user, broker connection, worker, or
    authorization endpoint.
    """
    allowed = ",".join("'" + kind + "'" for kind in CATEGORIES)
    con.executescript(f"""
    CREATE TABLE IF NOT EXISTS tenant_history_batches (
        batch_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        account_id TEXT NOT NULL,
        source_schema_sha256 TEXT NOT NULL CHECK(length(source_schema_sha256)=64),
        expected_references INTEGER NOT NULL CHECK(expected_references>=0),
        staged_at TEXT NOT NULL,
        batch_state TEXT NOT NULL DEFAULT 'REFERENCE_ONLY'
            CHECK(batch_state='REFERENCE_ONLY'),
        UNIQUE(batch_id,user_id,account_id),
        FOREIGN KEY(account_id,user_id)
            REFERENCES tenant_accounts(account_id,user_id)
    );
    CREATE TABLE IF NOT EXISTS tenant_history_references (
        reference_id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        account_id TEXT NOT NULL,
        source_table TEXT NOT NULL,
        source_rowid INTEGER NOT NULL,
        source_sha256 TEXT NOT NULL CHECK(length(source_sha256)=64),
        kind TEXT NOT NULL CHECK(kind IN ({allowed})),
        record_state TEXT NOT NULL DEFAULT 'REFERENCE_ONLY'
            CHECK(record_state='REFERENCE_ONLY'),
        UNIQUE(account_id,user_id,source_table,source_rowid),
        FOREIGN KEY(batch_id,user_id,account_id)
            REFERENCES tenant_history_batches(batch_id,user_id,account_id),
        FOREIGN KEY(account_id,user_id)
            REFERENCES tenant_accounts(account_id,user_id)
    );
    CREATE INDEX IF NOT EXISTS idx_tenant_history_scope_page
      ON tenant_history_references(user_id,account_id,reference_id DESC);
    CREATE INDEX IF NOT EXISTS idx_tenant_history_batch
      ON tenant_history_references(batch_id,user_id,account_id);
    """)


def stage_from_reconciled_history(con, *, user_id, account_id,
                                  source_schema_sha256, expected_count):
    """Stage only matching, explicitly scoped provenance within existing txn.

    This function is called AFTER the verified owner/account are created and
    history.reconcile has reviewed all source rows. Does not commit or expose
    payloads; all changes are lost when the shadow rehearsal is discarded.
    """
    if (not isinstance(source_schema_sha256,str) or
        len(source_schema_sha256)!=64 or
        not isinstance(expected_count,int) or isinstance(expected_count,bool) or
        expected_count<0):
        raise TenantHistoryError("Invalid history staging parameters")
    valid = con.execute("""SELECT 1 FROM tenant_accounts
        WHERE user_id=? AND account_id=? AND disabled_at IS NULL""",
        (user_id,account_id)).fetchone()
    if not valid:
        raise TenantHistoryError("History owner scope unavailable")
    batch_id=str(uuid.uuid4())
    now=datetime.now(timezone.utc).isoformat()
    con.execute("""INSERT INTO tenant_history_batches
        (batch_id,user_id,account_id,source_schema_sha256,expected_references,
         staged_at,batch_state) VALUES(?,?,?,?,?,?,'REFERENCE_ONLY')""",
        (batch_id,user_id,account_id,source_schema_sha256,expected_count,now))

    rows=con.execute("""SELECT source_table,source_rowid,source_sha256,classification
        FROM tenant_shadow_history_index
        WHERE (classification=? OR classification=?)
          AND user_id=? AND account_id=?
        ORDER BY source_table,source_rowid""",
        (history.EXPLICIT, history.PREMAPPED, user_id,account_id)).fetchall()
    if len(rows)!=expected_count:
        raise TenantHistoryError("Account-labeled history count mismatch")
    count=0
    for row in rows:
        source_table=row["source_table"]
        if source_table not in KINDS:
            raise TenantHistoryError("Unsupported account-labeled historical table")
        kind=KINDS[source_table]
        con.execute("""INSERT INTO tenant_history_references
            (batch_id,user_id,account_id,source_table,source_rowid,
             source_sha256,kind,record_state)
            VALUES(?,?,?,?,?,?,?,'REFERENCE_ONLY')""",
            (batch_id,user_id,account_id,source_table,row["source_rowid"],
             row["source_sha256"],kind))
        count+=1
    check=con.execute("""SELECT COUNT(*) AS n FROM tenant_history_references
        WHERE batch_id=? AND user_id=? AND account_id=?
          AND record_state='REFERENCE_ONLY'""",
        (batch_id,user_id,account_id)).fetchone()["n"]
    missing=con.execute("""SELECT COUNT(*) FROM tenant_history_references r
        LEFT JOIN tenant_shadow_history_index i
        ON i.source_table=r.source_table AND i.source_rowid=r.source_rowid
           AND i.source_sha256=r.source_sha256
           AND i.user_id=r.user_id AND i.account_id=r.account_id
        WHERE r.batch_id=? AND r.user_id=? AND r.account_id=?
          AND i.source_table IS NULL""",
        (batch_id,user_id,account_id)).fetchone()[0]
    quarantined=con.execute("""SELECT COUNT(*) FROM tenant_history_references r
        JOIN tenant_shadow_history_index i
          ON i.source_table=r.source_table AND i.source_rowid=r.source_rowid
        WHERE r.batch_id=? AND i.classification NOT IN (?,?)""",
        (batch_id,history.EXPLICIT,history.PREMAPPED)).fetchone()[0]
    if count!=expected_count or check!=expected_count or missing or quarantined:
        raise TenantHistoryError("Historical reference reconciliation failed")
    if con.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise TenantHistoryError("Historical reference ownership integrity failed")
    return {
        "referencesStaged":count,
        "sourceRowsReconciled":True,
        "quarantinedRecordsImported":0,
        "rawTradePayloadsMigrated":False,
        "fillsOrOrdersExecuted":False,
        "referencesOnly":True,
        "loginOrWorkerActivated":False,
        "cutoverReady":False,
    }


class DormantHistoryReader:
    """Future-only identity-session-scoped historical reference access.

    The caller cannot supply a user ID. Authorize on each read with a verified
    identity session and an enabled account + provider connection. No HTTP
    route currently constructs this reader. All reads are metadata-only.
    """

    def __init__(self,path,identity_store):
        self.path=str(path)
        self.identity_store=identity_store

    def _principal(self,session_token):
        principal=self.identity_store.principal(session_token)
        if not principal or not principal.get("user_id"):
            raise TenantAccessError("Identity session unavailable")
        return principal["user_id"]

    def _authorize(self,con,user_id,account_id):
        if not isinstance(account_id,str) or not account_id:
            raise TenantAccessError("Account unavailable")
        return AccountScopeStore._check(con,user_id,account_id)

    def summary(self,session_token,account_id):
        user_id=self._principal(session_token)
        with _db(self.path) as con:
            self._authorize(con,user_id,account_id)
            row=con.execute("""SELECT COUNT(*) AS n
                FROM tenant_history_references
                WHERE user_id=? AND account_id=?""",
                (user_id,account_id)).fetchone()
            kinds=con.execute("""SELECT kind,COUNT(*) AS n
                FROM tenant_history_references WHERE user_id=? AND account_id=?
                GROUP BY kind ORDER BY kind""",(user_id,account_id)).fetchall()
            return {"referenceCount":row["n"],
                    "categories":{r["kind"]:r["n"] for r in kinds},
                    "referenceOnly":True,"containsVerifiedBrokerFills":False,
                    "canTrade":False}

    def page(self,session_token,account_id,*,before_id=None,limit=50):
        """Keyset-paginated and always scoped to the authorized owner/account."""
        if (not isinstance(limit,int) or isinstance(limit,bool) or
            not 1<=limit<=100 or before_id is not None and
            (not isinstance(before_id,int) or isinstance(before_id,bool) or
             before_id<=0)):
            raise ValueError("Invalid history page request")
        user_id=self._principal(session_token)
        with _db(self.path) as con:
            self._authorize(con,user_id,account_id)
            rows=con.execute("""SELECT reference_id,kind,source_table,record_state
                FROM tenant_history_references
                WHERE user_id=? AND account_id=?
                  AND (? IS NULL OR reference_id<?)
                ORDER BY reference_id DESC LIMIT ?""",
                (user_id,account_id,before_id,before_id,limit)).fetchall()
        return {"items":[dict(r) for r in rows],
                "nextBeforeId":rows[-1]["reference_id"] if len(rows)==limit else None,
                "referenceOnly":True,"canTrade":False}
