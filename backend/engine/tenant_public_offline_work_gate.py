"""Offline-only atomic work-stage fencing using v0.2.23's SYNTHETIC fixture.

No threads, worker loop, callable execution, provider integration, HTTP,
balances, trading, transfers or production database changes. Every step
records ONLY a dummy lifecycle stage under the same SQLite write lock as
stop, pause, revocation and admission. This proves local ordering, not
distributed request cancellation or a production safety architecture.
"""
from __future__ import annotations

from .tenant_public_durable_safety_rehearsal import (
    OfflineDurableSafetyRehearsal,
    OfflineSafetyDenied,
    _synthetic_uuid,
)

BEGIN = "BEGIN"
CHECK = "CHECK"
FINISH = "FINISH"
STAGES = frozenset((BEGIN, CHECK, FINISH))
STATES = {BEGIN: "BEGUN", CHECK: "CHECKED", FINISH: "FINISHED"}
PREVIOUS = {BEGIN: None, CHECK: "BEGUN", FINISH: "CHECKED"}


class OfflineStageDenied(RuntimeError):
    CODES = frozenset(("INVALID_STAGE", "STALE_STAGE"))
    def __init__(self, code):
        self.code = code if code in self.CODES else "STALE_STAGE"
        super().__init__(self.code)


class OfflineSyntheticWorkGate:
    """A test-only transactional ledger of fake work checkpoints.

    Each accepted stage is serialized with v0.2.23's emergency stop.
    A stop committed before a stage blocks that stage; a step committed
    before a stop remains historical evidence. No actual work is invoked.
    """

    def __init__(self, safety):
        if type(safety) is not OfflineDurableSafetyRehearsal:
            raise TypeError("Exact offline synthetic safety fixture required")
        self.safety = safety
        self.safety._check_fixture()

    def setup(self):
        """Explicit fixture-only schema installation; never auto-migrates live data."""
        with self.safety._transaction() as con:
            self.safety._guard(con)
            # sqlite3.executescript implicitly commits and could release the
            # guard transaction before setup finishes. Use execute() for every
            # DDL statement to keep STOP ordering atomic.
            statements = (
                """CREATE TABLE IF NOT EXISTS offline_work_progress(
                    lease_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN
                        ('BEGUN','CHECKED','FINISHED')),
                    revision INTEGER NOT NULL CHECK(revision >= 1),
                    FOREIGN KEY(lease_id) REFERENCES offline_leases(lease_id),
                    FOREIGN KEY(owner_id,account_id)
                      REFERENCES offline_accounts(owner_id,account_id)
                )""",
                """CREATE TABLE IF NOT EXISTS offline_work_events(
                    id INTEGER PRIMARY KEY,
                    stage TEXT NOT NULL CHECK(stage IN ('BEGIN','CHECK','FINISH')),
                    at_seconds INTEGER NOT NULL
                )""",
                """CREATE TRIGGER IF NOT EXISTS no_offline_work_event_delete
                  BEFORE DELETE ON offline_work_events
                  BEGIN SELECT RAISE(ABORT,'synthetic audit cannot be deleted'); END""",
                """CREATE TRIGGER IF NOT EXISTS no_offline_work_event_update
                  BEFORE UPDATE ON offline_work_events
                  BEGIN SELECT RAISE(ABORT,'synthetic audit cannot be rewritten'); END""",
            )
            for statement in statements:
                con.execute(statement)
        return {"syntheticSchemaReady":True, "productionMigrationPerformed":False}

    def stage(self, owner_id, account_id, lease_id, stage):
        if type(stage) is not str or stage not in STAGES:
            raise OfflineStageDenied("INVALID_STAGE")
        owner = _synthetic_uuid(owner_id)
        account = _synthetic_uuid(account_id)
        lease = _synthetic_uuid(lease_id)
        now = self.safety._now()
        with self.safety._transaction() as con:
            global_row = self.safety._guard(con)
            scoped = self.safety._account(con, owner, account)
            if now < global_row["last_at"]:
                raise OfflineSafetyDenied("CLOCK_INVALID")
            lease_row = con.execute("""SELECT guard_revision,account_revision,expires_at
                FROM offline_leases
                WHERE lease_id=? AND owner_id=? AND account_id=?""",
                (lease, owner, account)).fetchone()
            if (lease_row is None or lease_row["expires_at"] <= now or
                lease_row["guard_revision"] != global_row["revision"] or
                lease_row["account_revision"] != scoped["revision"]):
                raise OfflineSafetyDenied("STALE_LEASE")

            progress = con.execute("""SELECT state,revision
                FROM offline_work_progress WHERE lease_id=? AND
                owner_id=? AND account_id=?""",
                (lease, owner, account)).fetchone()
            expected = PREVIOUS[stage]
            if expected is None:
                if progress is not None:
                    raise OfflineStageDenied("STALE_STAGE")
                con.execute("""INSERT INTO offline_work_progress
                    (lease_id,owner_id,account_id,state,revision)
                    VALUES(?,?,?,'BEGUN',1)""", (lease, owner, account))
            else:
                if progress is None or progress["state"] != expected:
                    raise OfflineStageDenied("STALE_STAGE")
                changed = con.execute("""UPDATE offline_work_progress
                    SET state=?,revision=revision+1
                    WHERE lease_id=? AND owner_id=? AND account_id=?
                      AND state=? AND revision=?""",
                    (STATES[stage],lease,owner,account,expected,
                     progress["revision"])).rowcount
                if changed != 1:
                    raise OfflineStageDenied("STALE_STAGE")

            con.execute("""INSERT INTO offline_work_events(stage,at_seconds)
                VALUES(?,?)""", (stage, now))
        return {"syntheticStageRecorded":stage, "offlineOnly":True,
                "networkAuthorized":False, "tradingAuthorized":False,
                "transferAuthorized":False, "productionWorkerStarted":False}

    def redacted_status(self):
        """Incident inspection works even while stop is latched; never unmutes it."""
        with self.safety._connection() as con:
            guard = con.execute("""SELECT stopped FROM offline_guard
                WHERE id=1""").fetchone()
            if guard is None:
                raise OfflineSafetyDenied("STATE_UNAVAILABLE")
            events = con.execute("""SELECT stage,COUNT(*) AS n
                FROM offline_work_events GROUP BY stage""").fetchall()
            progress = con.execute("""SELECT state,COUNT(*) AS n
                FROM offline_work_progress GROUP BY state""").fetchall()
            return {
                "syntheticOnly": True,
                "emergencyStopped": bool(guard["stopped"]),
                "productionIntegrated": False,
                "eventCounts": {r["stage"]: r["n"] for r in events},
                "workStates": {r["state"]: r["n"] for r in progress},
            }

    def activate_live(self, *args, **kwargs):
        raise PermissionError("DISCONNECTED_SYNTHETIC_ONLY")
