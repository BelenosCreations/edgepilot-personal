"""Persisted *within a disposable tmpfs fixture* Public safety policy.

All reads/writes require detached /dev/shm SQLite. This is not persistent
across host restart and is NOT connected to live EdgePilot. No live request,
credential access, trading or account activation is permitted.
"""
from __future__ import annotations

import math
import time

from . import account_scope, shadow_storage
from .tenant_foundation import TenantAccessError

ACCOUNT_BUDGET=2
GLOBAL_BUDGET=10
WINDOW_SECONDS=60


class SafetyGateDenied(RuntimeError):
    _CODES=frozenset(("NOT_INITIALIZED","EMERGENCY_STOP","ACCOUNT_PAUSED",
                      "BUDGET_EXHAUSTED","CLOCK_INVALID","OFFLINE_REVIEW_REQUIRED"))
    def __init__(self,code):
        self.code=code if code in self._CODES else "NOT_INITIALIZED"
        super().__init__(self.code)


class OfflinePersistentSafety:
    """Test fixture database persists kill state across controller objects.

    No unstop method: relaunching Python or creating another controller on
    the same synthetic DB does not clear an emergency stop. Recreating
    the disposable fixture, or losing tmpfs on restart, *does* lose data.
    That is a production blocker, not an acceptable emergency control.
    """

    def __init__(self,path,*,clock=None):
        self.path=str(path)
        shadow_storage.require_isolated_source(self.path)
        self.clock=clock or time.time

    def setup(self):
        shadow_storage.require_isolated_source(self.path)
        with account_scope._db(self.path) as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS tenant_test_safety_global(
                id INTEGER PRIMARY KEY CHECK(id=1),
                emergency_stopped INTEGER NOT NULL DEFAULT 0
                  CHECK(emergency_stopped IN (0,1)),
                revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1),
                last_at INTEGER NOT NULL DEFAULT 0,
                stopped_at INTEGER
            );
            INSERT OR IGNORE INTO tenant_test_safety_global
                (id,emergency_stopped,revision,last_at) VALUES(1,0,1,0);
            CREATE TABLE IF NOT EXISTS tenant_test_safety_pauses(
                user_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                paused INTEGER NOT NULL CHECK(paused IN (0,1)),
                revision INTEGER NOT NULL CHECK(revision>=1),
                PRIMARY KEY(user_id,account_id),
                FOREIGN KEY(account_id,user_id)
                  REFERENCES tenant_accounts(account_id,user_id)
            );
            CREATE TABLE IF NOT EXISTS tenant_test_safety_budget(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                at_seconds INTEGER NOT NULL,
                FOREIGN KEY(account_id,user_id)
                  REFERENCES tenant_accounts(account_id,user_id)
            );
            CREATE INDEX IF NOT EXISTS idx_tenant_test_budget_time
                ON tenant_test_safety_budget(at_seconds);
            CREATE INDEX IF NOT EXISTS idx_tenant_test_budget_account
                ON tenant_test_safety_budget(user_id,account_id,at_seconds);
            """)

    @staticmethod
    def _global(con):
        row=con.execute("""SELECT emergency_stopped,revision,last_at
            FROM tenant_test_safety_global WHERE id=1""").fetchone()
        if row is None:
            raise SafetyGateDenied("NOT_INITIALIZED")
        if row["emergency_stopped"]:
            raise SafetyGateDenied("EMERGENCY_STOP")
        return row

    def _time(self):
        value=self.clock()
        if (type(value) not in (int,float) or
            not math.isfinite(value) or value<0):
            raise SafetyGateDenied("CLOCK_INVALID")
        return int(value)

    def is_stopped(self):
        shadow_storage.require_isolated_source(self.path)
        with account_scope._db(self.path) as con:
            row=con.execute("SELECT emergency_stopped FROM tenant_test_safety_global WHERE id=1").fetchone()
            if row is None:
                raise SafetyGateDenied("NOT_INITIALIZED")
            return bool(row["emergency_stopped"])

    def emergency_stop(self):
        shadow_storage.require_isolated_source(self.path)
        now=self._time()
        with account_scope._db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            row=con.execute("SELECT revision,emergency_stopped FROM tenant_test_safety_global WHERE id=1").fetchone()
            if row is None:
                raise SafetyGateDenied("NOT_INITIALIZED")
            if not row["emergency_stopped"]:
                con.execute("""UPDATE tenant_test_safety_global
                    SET emergency_stopped=1,revision=revision+1,stopped_at=?
                    WHERE id=1""",(now,))
        return {"emergencyStopped":True,"canEnableLiveNetwork":False,
                "productionStopDeployed":False}

    def _check_account(self,con,user_id,account_id):
        account_scope.AccountScopeStore._check(con,user_id,account_id)

    def require_ready(self,user_id,account_id):
        shadow_storage.require_isolated_source(self.path)
        with account_scope._db(self.path) as con:
            self._global(con)
            self._check_account(con,user_id,account_id)
            row=con.execute("""SELECT paused FROM tenant_test_safety_pauses
                WHERE user_id=? AND account_id=?""",(user_id,account_id)).fetchone()
            if row and row["paused"]:
                raise SafetyGateDenied("ACCOUNT_PAUSED")
        return True

    def pause(self,user_id,account_id):
        shadow_storage.require_isolated_source(self.path)
        with account_scope._db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            self._check_account(con,user_id,account_id)
            con.execute("""INSERT INTO tenant_test_safety_pauses
                (user_id,account_id,paused,revision) VALUES(?,?,1,1)
                ON CONFLICT(user_id,account_id) DO UPDATE
                  SET paused=1,revision=revision+1""",(user_id,account_id))
        return {"pausedForOfflineTesting":True}

    def offline_manual_clear(self,user_id,account_id,*,phrase,expected_revision):
        if (phrase!="CLEAR SYNTHETIC ACCOUNT PAUSE ONLY" or
            type(expected_revision) is not int or expected_revision<1):
            raise SafetyGateDenied("OFFLINE_REVIEW_REQUIRED")
        shadow_storage.require_isolated_source(self.path)
        with account_scope._db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            self._global(con)
            self._check_account(con,user_id,account_id)
            changed=con.execute("""UPDATE tenant_test_safety_pauses
                SET paused=0,revision=revision+1
                WHERE user_id=? AND account_id=? AND paused=1
                  AND revision=?""",
                (user_id,account_id,expected_revision)).rowcount
            if changed!=1:
                raise SafetyGateDenied("OFFLINE_REVIEW_REQUIRED")
        return {"offlineOnly":True,"canEnableLiveNetwork":False}

    def pause_revision(self,user_id,account_id):
        shadow_storage.require_isolated_source(self.path)
        with account_scope._db(self.path) as con:
            self._check_account(con,user_id,account_id)
            row=con.execute("""SELECT revision FROM tenant_test_safety_pauses
                WHERE user_id=? AND account_id=?""",(user_id,account_id)).fetchone()
        return row["revision"] if row else 0

    def acquire_simulated(self,user_id,account_id):
        shadow_storage.require_isolated_source(self.path)
        now=self._time()
        with account_scope._db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            global_row=self._global(con)
            self._check_account(con,user_id,account_id)
            if now<global_row["last_at"]:
                raise SafetyGateDenied("CLOCK_INVALID")
            paused=con.execute("""SELECT paused FROM tenant_test_safety_pauses
                WHERE user_id=? AND account_id=?""",(user_id,account_id)).fetchone()
            if paused and paused["paused"]:
                raise SafetyGateDenied("ACCOUNT_PAUSED")
            con.execute("DELETE FROM tenant_test_safety_budget WHERE at_seconds<=?",
                        (now-WINDOW_SECONDS,))
            global_count=con.execute("SELECT COUNT(*) FROM tenant_test_safety_budget").fetchone()[0]
            owned_count=con.execute("""SELECT COUNT(*) FROM tenant_test_safety_budget
                WHERE user_id=? AND account_id=?""",(user_id,account_id)).fetchone()[0]
            if global_count>=GLOBAL_BUDGET or owned_count>=ACCOUNT_BUDGET:
                raise SafetyGateDenied("BUDGET_EXHAUSTED")
            con.execute("""INSERT INTO tenant_test_safety_budget
                (user_id,account_id,at_seconds) VALUES(?,?,?)""",
                (user_id,account_id,now))
            con.execute("UPDATE tenant_test_safety_global SET last_at=? WHERE id=1",(now,))
        return {"simulatedBudgetConsumed":True,"liveNetworkEnabled":False,
                "canTrade":False}
