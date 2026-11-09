"""Account-scoped, dormant storage and permissions for future EdgePilot tenants.

This repository never calls Public, schedules scans, places orders or transfers.
All authenticated HTTP reads must derive their principal from an identity
session cookie. A separately trusted backend worker will need its own internal
authorization path before tenant scans can run. Legacy worker is unchanged.
"""
from __future__ import annotations

import json
import math
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from .tenant_foundation import TenantAccessError

_ALLOWED_STATES = frozenset(("OK","PARTIAL","NO_DATA","MARKET_CLOSED",
                            "CALENDAR_UNKNOWN","ERROR"))
_ALLOWED_MODES = frozenset(("observe","paper"))
_ALLOWED_SESSIONS = frozenset(("OPEN","CLOSED","UNKNOWN","NOT_APPLICABLE"))
_MAX_SYMBOLS = 100


def _now():
    return datetime.now(timezone.utc).isoformat()


def _db(path):
    con=sqlite3.connect(str(path),timeout=30)
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=30000")
    return con


def _money(value):
    if isinstance(value,bool):
        raise ValueError("Invalid amount")
    try:
        amount=Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Invalid amount") from None
    if not amount.is_finite() or amount < 0 or amount > Decimal("100000000000"):
        raise ValueError("Invalid amount")
    return format(amount.quantize(Decimal("0.01")), "f")


def _symbols(values):
    if not isinstance(values,(list,tuple)) or len(values)>_MAX_SYMBOLS:
        raise ValueError("Invalid symbols list")
    symbols=[]
    for value in values:
        if (not isinstance(value,str) or not 1<=len(value)<=15 or
            not value.isascii() or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for c in value)):
            raise ValueError("Invalid observation symbols")
        if value not in symbols:
            symbols.append(value)
    return symbols


def setup(path):
    """Idempotently add account-scoped tables. No existing table is modified."""
    with _db(path) as con:
        con.executescript("""
        BEGIN IMMEDIATE;
        CREATE TABLE IF NOT EXISTS tenant_portfolio_snapshots (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            provider_timestamp TEXT NOT NULL,
            account_value TEXT NOT NULL,
            buying_power TEXT NOT NULL,
            FOREIGN KEY(account_id,user_id) REFERENCES tenant_accounts(account_id,user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_tenant_portfolio_recent
            ON tenant_portfolio_snapshots(user_id,account_id,snapshot_id);
        CREATE TABLE IF NOT EXISTS tenant_observation_cycles (
            cycle_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            mode TEXT NOT NULL CHECK(mode IN ('observe','paper')),
            state TEXT NOT NULL CHECK(state IN (
                'OK','PARTIAL','NO_DATA','MARKET_CLOSED','CALENDAR_UNKNOWN','ERROR')),
            market_session TEXT NOT NULL CHECK(market_session IN (
                'OPEN','CLOSED','UNKNOWN','NOT_APPLICABLE')),
            symbols_json TEXT NOT NULL,
            accepted INTEGER NOT NULL CHECK(accepted>=0),
            rejected INTEGER NOT NULL CHECK(rejected>=0),
            oldest_quote_age_seconds INTEGER,
            issue TEXT,
            FOREIGN KEY(account_id,user_id) REFERENCES tenant_accounts(account_id,user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_tenant_observation_recent
            ON tenant_observation_cycles(user_id,account_id,cycle_id);
        CREATE TABLE IF NOT EXISTS tenant_worker_leases (
            account_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            worker_id TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            PRIMARY KEY(account_id,user_id),
            FOREIGN KEY(account_id,user_id) REFERENCES tenant_accounts(account_id,user_id)
        );
        CREATE TABLE IF NOT EXISTS tenant_runtime_status (
            account_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            requested_mode TEXT NOT NULL DEFAULT 'observe'
                CHECK(requested_mode='observe'),
            worker_enabled INTEGER NOT NULL DEFAULT 0 CHECK(worker_enabled=0),
            paper_enabled INTEGER NOT NULL DEFAULT 0 CHECK(paper_enabled=0),
            live_enabled INTEGER NOT NULL DEFAULT 0 CHECK(live_enabled=0),
            PRIMARY KEY(account_id,user_id),
            FOREIGN KEY(account_id,user_id) REFERENCES tenant_accounts(account_id,user_id)
        );
        """)
        # No scan, order or worker is activated by schema creation.


class AccountScopeStore:
    """One authenticated session principal -> zero or more owned accounts.

    No user_id is accepted from an HTTP parameter. The identity store must be
    a verified back-end module, not a caller-supplied request object.
    """

    def __init__(self, path, identity_store):
        self.path=str(path)
        self.identity_store=identity_store

    def _principal(self, session_token):
        principal=self.identity_store.principal(session_token)
        if principal is None:
            raise TenantAccessError("Identity session unavailable")
        return principal["user_id"]

    @staticmethod
    def _check(con, user_id, account_id):
        row=con.execute("""SELECT a.account_id,a.label,a.provider
            FROM tenant_accounts a
            JOIN tenant_users u ON u.user_id=a.user_id
            JOIN tenant_connections c ON c.connection_id=a.connection_id
                                    AND c.user_id=a.user_id
            WHERE a.account_id=? AND a.user_id=? AND a.disabled_at IS NULL
              AND u.disabled_at IS NULL AND c.revoked_at IS NULL""",
            (account_id,user_id)).fetchone()
        if row is None:
            raise TenantAccessError("Account unavailable")
        return row

    def list_accounts(self, session_token):
        user_id=self._principal(session_token)
        with _db(self.path) as con:
            return [dict(row) for row in con.execute("""SELECT a.account_id,a.label,a.provider
                FROM tenant_accounts a
                JOIN tenant_users u ON u.user_id=a.user_id
                JOIN tenant_connections c ON c.connection_id=a.connection_id
                                        AND c.user_id=a.user_id
                WHERE a.user_id=? AND a.disabled_at IS NULL
                  AND u.disabled_at IS NULL AND c.revoked_at IS NULL
                ORDER BY a.created_at,a.account_id""",(user_id,))]

    def account_summary(self, session_token, account_id):
        user_id=self._principal(session_token)
        with _db(self.path) as con:
            account=self._check(con,user_id,account_id)
            portfolio=con.execute("""SELECT captured_at,provider_timestamp,
                account_value,buying_power FROM tenant_portfolio_snapshots
                WHERE user_id=? AND account_id=?
                ORDER BY snapshot_id DESC LIMIT 1""",(user_id,account_id)).fetchone()
            latest=con.execute("""SELECT completed_at,mode,state,market_session,
                symbols_json,accepted,rejected,oldest_quote_age_seconds,issue
                FROM tenant_observation_cycles WHERE user_id=? AND account_id=?
                ORDER BY cycle_id DESC LIMIT 1""",(user_id,account_id)).fetchone()
            after=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
            recent=con.execute("""SELECT COUNT(*) AS cycles,
                COALESCE(SUM(accepted),0) AS accepted,
                COALESCE(SUM(rejected),0) AS rejected
                FROM tenant_observation_cycles
                WHERE user_id=? AND account_id=? AND completed_at>=?""",
                (user_id,account_id,after)).fetchone()
            runtime=con.execute("""SELECT requested_mode,worker_enabled,paper_enabled,live_enabled
                FROM tenant_runtime_status WHERE user_id=? AND account_id=?""",
                (user_id,account_id)).fetchone()
        return {
            "account":{"id":account["account_id"],"label":account["label"],
                       "provider":account["provider"]},
            "portfolio":dict(portfolio) if portfolio else None,
            "observation":({**dict(latest),"symbols":json.loads(latest["symbols_json"])}
                           if latest else None),
            "last24h":dict(recent),
            "runtime":dict(runtime) if runtime else {
                "requested_mode":"observe","worker_enabled":0,
                "paper_enabled":0,"live_enabled":0},
            "readOnly":True,
            "providerRequestMade":False,
            "historicalDataMigrated":False,
        }


class DormantAccountWorkerStore:
    """Backend-internal storage for a *future* trusted per-account scheduler.

    No HTTP routes, broker calls, executors, threads or start actions use this.
    The caller must obtain a trusted user/account pair from an internal
    scheduler and supply its private worker identifier. Never forward a
    client-provided user ID into this interface.
    """

    def __init__(self, path):
        self.path=str(path)

    @staticmethod
    def _check(con,user_id,account_id):
        return AccountScopeStore._check(con,user_id,account_id)

    def claim_lease(self,user_id,account_id,worker_id,*,now=None,ttl=120):
        if (not isinstance(worker_id,str) or not 16<=len(worker_id)<=128 or
            not worker_id.isascii() or not 60<=ttl<=900):
            raise ValueError("Invalid worker lease")
        now=int(time.time() if now is None else now)
        with _db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            self._check(con,user_id,account_id)
            con.execute("""INSERT INTO tenant_worker_leases
                (user_id,account_id,worker_id,expires_at)
                VALUES(?,?,?,?)
                ON CONFLICT(account_id,user_id) DO UPDATE
                SET worker_id=excluded.worker_id,expires_at=excluded.expires_at
                WHERE tenant_worker_leases.expires_at<=? OR
                      tenant_worker_leases.worker_id=excluded.worker_id""",
                (user_id,account_id,worker_id,now+ttl,now))
            row=con.execute("""SELECT worker_id FROM tenant_worker_leases
                WHERE user_id=? AND account_id=?""",(user_id,account_id)).fetchone()
            return row is not None and row["worker_id"]==worker_id

    def release_lease(self,user_id,account_id,worker_id):
        with _db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            self._check(con,user_id,account_id)
            return con.execute("""DELETE FROM tenant_worker_leases
                WHERE user_id=? AND account_id=? AND worker_id=?""",
                (user_id,account_id,worker_id)).rowcount==1

    def _require_lease(self,con,user_id,account_id,worker_id,now):
        self._check(con,user_id,account_id)
        row=con.execute("""SELECT 1 FROM tenant_worker_leases
            WHERE user_id=? AND account_id=? AND worker_id=?
            AND expires_at>?""",(user_id,account_id,worker_id,now)).fetchone()
        if row is None:
            raise TenantAccessError("No valid account-scoped worker lease")

    def record_observation(self,user_id,account_id,worker_id,*,mode,state,
                           symbols=(),market_session="NOT_APPLICABLE",
                           accepted=0,rejected=0,quote_age_seconds=None,issue=None,now=None):
        if mode not in _ALLOWED_MODES or state not in _ALLOWED_STATES or market_session not in _ALLOWED_SESSIONS:
            raise ValueError("Invalid observation state")
        if (not isinstance(accepted,int) or isinstance(accepted,bool) or accepted<0 or
            not isinstance(rejected,int) or isinstance(rejected,bool) or rejected<0):
            raise ValueError("Invalid quote counts")
        if quote_age_seconds is not None and (
            not isinstance(quote_age_seconds,int) or isinstance(quote_age_seconds,bool) or
            not 0<=quote_age_seconds<=86400):
            raise ValueError("Invalid quote age")
        if issue is not None and (not isinstance(issue,str) or len(issue)>160):
            raise ValueError("Invalid diagnostic note")
        symbols=_symbols(list(symbols))
        now=int(time.time() if now is None else now)
        with _db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            self._require_lease(con,user_id,account_id,worker_id,now)
            con.execute("""INSERT INTO tenant_observation_cycles
                (user_id,account_id,completed_at,mode,state,market_session,
                symbols_json,accepted,rejected,oldest_quote_age_seconds,issue)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (user_id,account_id,_now(),mode,state,market_session,
                 json.dumps(symbols),accepted,rejected,quote_age_seconds,issue))
            # Retain up to 200 cycles per account, never delete a second account's data.
            con.execute("""DELETE FROM tenant_observation_cycles
                WHERE user_id=? AND account_id=? AND cycle_id NOT IN (
                SELECT cycle_id FROM tenant_observation_cycles
                WHERE user_id=? AND account_id=? ORDER BY cycle_id DESC LIMIT 200)""",
                (user_id,account_id,user_id,account_id))

    def record_portfolio_snapshot(self,user_id,account_id,worker_id,*,
                                  total_value,buying_power,provider_timestamp,now=None):
        """Accept only provider-verified snapshot values from a future adapter."""
        value=_money(total_value)
        buying=_money(buying_power)
        if not isinstance(provider_timestamp,str) or not 10<=len(provider_timestamp)<=64:
            raise ValueError("Source timestamp required")
        try:
            stamp=datetime.fromisoformat(provider_timestamp.replace("Z","+00:00"))
        except ValueError:
            raise ValueError("Invalid source timestamp") from None
        if stamp.tzinfo is None:
            raise ValueError("Timezone-aware source timestamp required")
        now=int(time.time() if now is None else now)
        with _db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            self._require_lease(con,user_id,account_id,worker_id,now)
            con.execute("""INSERT INTO tenant_portfolio_snapshots
                (user_id,account_id,captured_at,provider_timestamp,account_value,buying_power)
                VALUES(?,?,?,?,?,?)""",
                (user_id,account_id,_now(),stamp.isoformat(),value,buying))
            con.execute("""DELETE FROM tenant_portfolio_snapshots
                WHERE user_id=? AND account_id=? AND snapshot_id NOT IN (
                SELECT snapshot_id FROM tenant_portfolio_snapshots
                WHERE user_id=? AND account_id=? ORDER BY snapshot_id DESC LIMIT 2500)""",
                (user_id,account_id,user_id,account_id))
