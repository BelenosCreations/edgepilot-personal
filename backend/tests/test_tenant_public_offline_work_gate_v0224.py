"""v0.2.24: disconnected work checkpoint fencing tests, synthetic IDs only."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from engine import (
    tenant_public_durable_safety_rehearsal as safety,
    tenant_public_offline_work_gate as work,
    tenant_public_https_wire as wire,
    tenant_route_audit,
)

ROOT = Path(__file__).resolve().parents[2]
FIXED_TIME = 1_900_000_000


def competing_begin(directory, owner, account, lease):
    """A separate process attempts to consume the same synthetic stage."""
    gate = work.OfflineSyntheticWorkGate(
        safety.OfflineDurableSafetyRehearsal(directory,clock=lambda:FIXED_TIME))
    try:
        gate.stage(owner, account, lease, work.BEGIN)
        return "STAGE_OK"
    except (work.OfflineStageDenied,safety.OfflineSafetyDenied) as exc:
        return exc.code


def finish_or_stop(directory, owner, account, lease, choice):
    """Simultaneous fake finish/stop, both serialized on one fixture."""
    safe = safety.OfflineDurableSafetyRehearsal(directory,clock=lambda:FIXED_TIME)
    gate = work.OfflineSyntheticWorkGate(safe)
    try:
        if choice == "stop":
            safe.emergency_stop()
            return "STOPPED"
        gate.stage(owner,account,lease,work.FINISH)
        return "FINISHED"
    except (safety.OfflineSafetyDenied,work.OfflineStageDenied) as exc:
        return exc.code


class SyntheticWorkGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="edgepilot-work-v024-")
        self.now = [FIXED_TIME]
        self.owner = str(uuid.uuid4())
        self.other_owner = str(uuid.uuid4())
        self.account = str(uuid.uuid4())
        self.other_account = str(uuid.uuid4())
        self.safe = safety.OfflineDurableSafetyRehearsal.create_fixture(
            self.temp.name,phrase=safety.FIXTURE_PHRASE,
            clock=lambda:self.now[0])
        self.safe.enroll_synthetic(self.owner,self.account)
        self.safe.enroll_synthetic(self.other_owner,self.other_account)
        self.gate = work.OfflineSyntheticWorkGate(self.safe)
        self.assertFalse(self.gate.setup()["productionMigrationPerformed"])
        self.lease = self.safe.admit_synthetic(self.owner,self.account)["leaseId"]

    def tearDown(self):
        self.temp.cleanup()

    def test_progression_is_strict_ordered_fake_and_redacted(self):
        for stage in (work.BEGIN,work.CHECK,work.FINISH):
            result = self.gate.stage(self.owner,self.account,self.lease,stage)
            self.assertEqual(result["syntheticStageRecorded"],stage)
            for key in ("networkAuthorized","tradingAuthorized",
                        "transferAuthorized","productionWorkerStarted"):
                self.assertFalse(result[key])
        report = self.gate.redacted_status()
        self.assertEqual(report["workStates"],{"FINISHED":1})
        self.assertEqual(report["eventCounts"],{"BEGIN":1,"CHECK":1,"FINISH":1})
        self.assertFalse(report["productionIntegrated"])
        self.assertNotIn(self.account,str(report))
        self.assertNotIn(self.owner,str(report))
        with self.assertRaises(work.OfflineStageDenied) as caught:
            self.gate.stage(self.owner,self.account,self.lease,work.FINISH)
        self.assertEqual(caught.exception.code,"STALE_STAGE")
        with self.assertRaises(PermissionError):
            self.gate.activate_live()

    def test_rejects_out_of_order_duplicate_and_unknown_steps(self):
        for value in (work.CHECK,work.FINISH):
            with self.assertRaises(work.OfflineStageDenied):
                self.gate.stage(self.owner,self.account,self.lease,value)
        for value in ("TRADE","TRANSFER","scan SPY",None,{"stage":"BEGIN"}):
            with self.assertRaises(work.OfflineStageDenied) as caught:
                self.gate.stage(self.owner,self.account,self.lease,value)
            self.assertEqual(caught.exception.code,"INVALID_STAGE")
        self.gate.stage(self.owner,self.account,self.lease,work.BEGIN)
        with self.assertRaises(work.OfflineStageDenied):
            self.gate.stage(self.owner,self.account,self.lease,work.BEGIN)
        self.gate.stage(self.owner,self.account,self.lease,work.CHECK)
        self.assertEqual(self.gate.redacted_status()["workStates"],{"CHECKED":1})

    def test_wrong_owner_account_or_lease_denied(self):
        for owner,acct,lease in (
            (self.other_owner,self.account,self.lease),
            (self.owner,self.other_account,self.lease),
            (self.owner,self.account,str(uuid.uuid4())),
        ):
            with self.assertRaises(safety.OfflineSafetyDenied):
                self.gate.stage(owner,acct,lease,work.BEGIN)
        self.assertEqual(self.gate.redacted_status()["eventCounts"],{})

    def test_pause_then_resume_fences_old_lease_and_other_account_untouched(self):
        self.gate.stage(self.owner,self.account,self.lease,work.BEGIN)
        self.safe.pause_synthetic(self.owner,self.account)
        with self.assertRaises(safety.OfflineSafetyDenied) as caught:
            self.gate.stage(self.owner,self.account,self.lease,work.CHECK)
        self.assertEqual(caught.exception.code,"ACCOUNT_PAUSED")
        revision = self.safe.account_revision(self.owner,self.account)
        self.safe.resume_paused_synthetic(self.owner,self.account,
            expected_revision=revision,phrase=safety.PAUSE_CLEAR_PHRASE)
        with self.assertRaises(safety.OfflineSafetyDenied) as caught:
            self.gate.stage(self.owner,self.account,self.lease,work.CHECK)
        self.assertEqual(caught.exception.code,"STALE_LEASE")
        other_lease = self.safe.admit_synthetic(
            self.other_owner,self.other_account)["leaseId"]
        self.assertTrue(self.gate.stage(
            self.other_owner,self.other_account,other_lease,work.BEGIN)["offlineOnly"])

    def test_revocation_blocks_finish_but_not_other_owner(self):
        self.gate.stage(self.owner,self.account,self.lease,work.BEGIN)
        self.safe.revoke_synthetic(self.owner,self.account)
        with self.assertRaises(safety.OfflineSafetyDenied) as caught:
            self.gate.stage(self.owner,self.account,self.lease,work.CHECK)
        self.assertEqual(caught.exception.code,"ACCOUNT_UNAVAILABLE")
        lease_b = self.safe.admit_synthetic(
            self.other_owner,self.other_account)["leaseId"]
        self.assertTrue(self.gate.stage(
            self.other_owner,self.other_account,lease_b,work.BEGIN)["offlineOnly"])

    def test_expired_lease_and_rollback_clock_denied(self):
        self.gate.stage(self.owner,self.account,self.lease,work.BEGIN)
        self.now[0] -= 1
        with self.assertRaises(safety.OfflineSafetyDenied) as caught:
            self.gate.stage(self.owner,self.account,self.lease,work.CHECK)
        self.assertEqual(caught.exception.code,"CLOCK_INVALID")
        self.now[0] += safety.LEASE_SECONDS + 1
        with self.assertRaises(safety.OfflineSafetyDenied) as caught:
            self.gate.stage(self.owner,self.account,self.lease,work.CHECK)
        self.assertEqual(caught.exception.code,"STALE_LEASE")

    def test_emergency_stop_before_finish_keeps_incomplete_and_inspectable(self):
        self.gate.stage(self.owner,self.account,self.lease,work.BEGIN)
        self.gate.stage(self.owner,self.account,self.lease,work.CHECK)
        self.safe.emergency_stop()
        fresh = work.OfflineSyntheticWorkGate(
            safety.OfflineDurableSafetyRehearsal(self.temp.name,
                                                 clock=lambda:self.now[0]))
        with self.assertRaises(safety.OfflineSafetyDenied) as caught:
            fresh.stage(self.owner,self.account,self.lease,work.FINISH)
        self.assertEqual(caught.exception.code,"EMERGENCY_STOP")
        summary = fresh.redacted_status()
        self.assertTrue(summary["emergencyStopped"])
        self.assertEqual(summary["workStates"],{"CHECKED":1})
        self.assertEqual(summary["eventCounts"],{"BEGIN":1,"CHECK":1})

    def test_finish_before_stop_remains_historical_not_authorization(self):
        for stage in (work.BEGIN,work.CHECK,work.FINISH):
            self.gate.stage(self.owner,self.account,self.lease,stage)
        self.safe.emergency_stop()
        report = self.gate.redacted_status()
        self.assertEqual(report["workStates"],{"FINISHED":1})
        self.assertTrue(report["emergencyStopped"])
        with self.assertRaises(safety.OfflineSafetyDenied):
            self.gate.stage(self.owner,self.account,self.lease,work.BEGIN)

    def test_competing_processes_exactly_one_begin_commits(self):
        with ProcessPoolExecutor(max_workers=5) as pool:
            outcomes=list(pool.map(competing_begin,
                                   [self.temp.name]*7,
                                   [self.owner]*7,
                                   [self.account]*7,
                                   [self.lease]*7))
        self.assertEqual(outcomes.count("STAGE_OK"),1)
        self.assertEqual(outcomes.count("STALE_STAGE"),6)
        self.assertEqual(self.gate.redacted_status()["eventCounts"],{"BEGIN":1})

    def test_concurrent_stop_finish_are_serialized(self):
        self.gate.stage(self.owner,self.account,self.lease,work.BEGIN)
        self.gate.stage(self.owner,self.account,self.lease,work.CHECK)
        with ProcessPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(finish_or_stop,
                                   [self.temp.name]*2,
                                   [self.owner]*2,
                                   [self.account]*2,
                                   [self.lease]*2,
                                   ["finish","stop"]))
        self.assertIn("STOPPED",outcomes)
        self.assertIn(outcomes[0],("FINISHED","EMERGENCY_STOP"))
        report=self.gate.redacted_status()
        self.assertTrue(report["emergencyStopped"])
        if outcomes[0]=="FINISHED":
            self.assertEqual(report["workStates"],{"FINISHED":1})
        else:
            self.assertEqual(report["workStates"],{"CHECKED":1})

    def test_missing_audit_table_rolls_back_stage(self):
        with sqlite3.connect(self.safe.db_path) as con:
            con.execute("DROP TABLE offline_work_events")
        with self.assertRaises(safety.OfflineSafetyDenied) as caught:
            self.gate.stage(self.owner,self.account,self.lease,work.BEGIN)
        self.assertEqual(caught.exception.code,"STATE_UNAVAILABLE")
        with sqlite3.connect(self.safe.db_path) as con:
            count=con.execute("SELECT COUNT(*) FROM offline_work_progress").fetchone()[0]
        self.assertEqual(count,0)

    def test_audit_is_immutable_for_ordinary_sql_updates(self):
        self.gate.stage(self.owner,self.account,self.lease,work.BEGIN)
        with sqlite3.connect(self.safe.db_path) as con:
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("DELETE FROM offline_work_events")
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("UPDATE offline_work_events SET stage='FINISH'")

    def test_live_app_worker_and_public_network_remain_disconnected(self):
        app=(ROOT/"backend/app.py").read_text()
        worker=(ROOT/"backend/engine/automation_worker.py").read_text()
        module="tenant_public_offline_work_gate"
        self.assertNotIn(module,app)
        self.assertNotIn(module,worker)
        self.assertFalse(wire.NETWORK_ENABLED)
        audit=tenant_route_audit.inspect_sources(app,worker)
        self.assertFalse(audit["crossAccountProductionCutoverAllowed"])
        for aa,ww in ((app+"\nfrom engine import "+module+"\n",worker),
                      (app,worker+"\nfrom engine import "+module+"\n")):
            with self.assertRaises(tenant_route_audit.ApiBoundaryError):
                tenant_route_audit.inspect_sources(aa,ww)


if __name__=="__main__":
    unittest.main()
