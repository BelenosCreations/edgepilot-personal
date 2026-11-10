"""v0.2.23 disconnected, disk-backed synthetic safety regression tests.

No real broker secrets, calls, production DB or trading operations.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid

from engine import (
    tenant_public_durable_safety_rehearsal as offline,
    tenant_public_https_wire as wire,
    tenant_route_audit,
)

ROOT = Path(__file__).resolve().parents[2]


def competing_admit(directory, owner, account):
    """Separate processes contend on the same disposable SQLite fixture."""
    guard = offline.OfflineDurableSafetyRehearsal(directory)
    try:
        guard.admit_synthetic(owner,account)
        return "ADMITTED"
    except offline.OfflineSafetyDenied as exc:
        return exc.code


class OfflineDurableSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="edgepilot-synthetic-v023-")
        self.path = self.temp.name
        self.now = [1_800_000_000]
        self.owner_a = str(uuid.uuid4())
        self.owner_b = str(uuid.uuid4())
        self.account_a = str(uuid.uuid4())
        self.account_b = str(uuid.uuid4())
        self.guard = offline.OfflineDurableSafetyRehearsal.create_fixture(
            self.path, phrase=offline.FIXTURE_PHRASE, clock=lambda:self.now[0])
        self.guard.enroll_synthetic(self.owner_a,self.account_a)
        self.guard.enroll_synthetic(self.owner_b,self.account_b)

    def tearDown(self):
        self.temp.cleanup()

    def test_separate_process_restart_keeps_stop_latched(self):
        lease = self.guard.admit_synthetic(self.owner_a,self.account_a)
        self.assertFalse(lease["networkAuthorized"])
        self.guard.emergency_stop()
        script = ("import sys; from engine.tenant_public_durable_safety_rehearsal "
                  "import OfflineDurableSafetyRehearsal as Guard; "
                  "print(Guard(sys.argv[1]).is_stopped())")
        process = subprocess.run([sys.executable,"-c",script,self.path],
                                 cwd=str(ROOT/"backend"),text=True,
                                 capture_output=True,timeout=15)
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(process.stdout.strip(),"True")
        reopened = offline.OfflineDurableSafetyRehearsal(self.path)
        with self.assertRaises(offline.OfflineSafetyDenied) as caught:
            reopened.admit_synthetic(self.owner_a,self.account_a)
        self.assertEqual(caught.exception.code,"EMERGENCY_STOP")
        with self.assertRaises(offline.OfflineSafetyDenied):
            reopened.revalidate_synthetic(self.owner_a,self.account_a,lease["leaseId"])
        self.assertTrue(reopened.is_stopped())
        with self.assertRaises(offline.OfflineSafetyDenied):
            offline.OfflineDurableSafetyRehearsal.create_fixture(
                self.path,phrase=offline.FIXTURE_PHRASE)

    def test_cross_process_atomic_account_limit(self):
        # Each child process owns a fresh SQLite connection. Only two can win.
        with ProcessPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(competing_admit,
                                        [self.path]*8,
                                        [self.owner_a]*8,
                                        [self.account_a]*8))
        self.assertEqual(results.count("ADMITTED"),2)
        self.assertEqual(results.count("BUDGET_EXHAUSTED"),6)
        self.assertTrue(self.guard.admit_synthetic(self.owner_b,self.account_b)
                        ["offlineOnly"])

    def test_global_limit_and_clock_regression_across_instances(self):
        extra = [(self.owner_a,str(uuid.uuid4())) for _ in range(4)]
        for owner,account in extra:
            self.guard.enroll_synthetic(owner,account)
        all_accounts = [(self.owner_a,self.account_a),
                        (self.owner_b,self.account_b)] + extra
        for owner,account in all_accounts[:5]:
            self.guard.admit_synthetic(owner,account)
            self.guard.admit_synthetic(owner,account)
        with self.assertRaises(offline.OfflineSafetyDenied) as caught:
            self.guard.admit_synthetic(*all_accounts[5])
        self.assertEqual(caught.exception.code,"BUDGET_EXHAUSTED")
        stale_clock = offline.OfflineDurableSafetyRehearsal(
            self.path,clock=lambda:self.now[0]-2)
        with self.assertRaises(offline.OfflineSafetyDenied) as caught:
            stale_clock.admit_synthetic(*all_accounts[5])
        self.assertEqual(caught.exception.code,"CLOCK_INVALID")
        self.now[0] += 61
        self.assertTrue(self.guard.admit_synthetic(*all_accounts[5])["offlineOnly"])

    def test_pause_manual_fencing_recovery_does_not_restore_old_lease(self):
        lease = self.guard.admit_synthetic(self.owner_a,self.account_a)["leaseId"]
        self.assertTrue(self.guard.revalidate_synthetic(
            self.owner_a,self.account_a,lease)["offlineLeaseValidAtCheck"])
        self.guard.pause_synthetic(self.owner_a,self.account_a)
        revision = self.guard.account_revision(self.owner_a,self.account_a)
        with self.assertRaises(offline.OfflineSafetyDenied) as caught:
            self.guard.revalidate_synthetic(self.owner_a,self.account_a,lease)
        self.assertEqual(caught.exception.code,"ACCOUNT_PAUSED")
        for phrase,rev in (("wrong",revision),(offline.PAUSE_CLEAR_PHRASE,revision-1)):
            with self.assertRaises(offline.OfflineSafetyDenied):
                self.guard.resume_paused_synthetic(
                    self.owner_a,self.account_a,phrase=phrase,expected_revision=rev)
        self.guard.resume_paused_synthetic(
            self.owner_a,self.account_a,phrase=offline.PAUSE_CLEAR_PHRASE,
            expected_revision=revision)
        with self.assertRaises(offline.OfflineSafetyDenied) as caught:
            self.guard.revalidate_synthetic(self.owner_a,self.account_a,lease)
        self.assertEqual(caught.exception.code,"STALE_LEASE")
        self.assertTrue(self.guard.admit_synthetic(self.owner_a,self.account_a)["offlineOnly"])

    def test_revoke_is_permanent_within_fixture_and_cross_owner_denied(self):
        lease = self.guard.admit_synthetic(self.owner_a,self.account_a)["leaseId"]
        with self.assertRaises(offline.OfflineSafetyDenied):
            self.guard.admit_synthetic(self.owner_b,self.account_a)
        with self.assertRaises(offline.OfflineSafetyDenied):
            self.guard.revoke_synthetic(self.owner_b,self.account_a)
        self.guard.revoke_synthetic(self.owner_a,self.account_a)
        for action in (
            lambda:self.guard.admit_synthetic(self.owner_a,self.account_a),
            lambda:self.guard.revalidate_synthetic(
                self.owner_a,self.account_a,lease),
            lambda:self.guard.resume_paused_synthetic(
                self.owner_a,self.account_a,expected_revision=2,
                phrase=offline.PAUSE_CLEAR_PHRASE),
            lambda:self.guard.enroll_synthetic(self.owner_a,self.account_a),
        ):
            with self.assertRaises(offline.OfflineSafetyDenied):
                action()
        self.assertTrue(self.guard.admit_synthetic(self.owner_b,self.account_b)["offlineOnly"])

    def test_lease_expiration_invalid_clock_and_redacted_audit(self):
        lease = self.guard.admit_synthetic(self.owner_a,self.account_a)["leaseId"]
        self.now[0] += offline.LEASE_SECONDS
        with self.assertRaises(offline.OfflineSafetyDenied) as caught:
            self.guard.revalidate_synthetic(self.owner_a,self.account_a,lease)
        self.assertEqual(caught.exception.code,"STALE_LEASE")
        summary = self.guard.audit_summary()
        self.assertFalse(summary["productionIntegrated"])
        self.assertEqual(summary["eventCounts"]["ENROLL"],2)
        self.assertEqual(summary["eventCounts"]["ADMIT"],1)
        text = str(summary)
        self.assertNotIn(self.owner_a,text)
        self.assertNotIn(self.account_a,text)
        with sqlite3.connect(self.guard.db_path) as con:
            rows = str(con.execute("SELECT * FROM offline_audit").fetchall())
            self.assertNotIn(self.account_a,rows)
            self.assertNotIn(self.owner_a,rows)
        self.now[0] = float("nan")
        with self.assertRaises(offline.OfflineSafetyDenied) as caught:
            self.guard.admit_synthetic(self.owner_a,self.account_a)
        self.assertEqual(caught.exception.code,"CLOCK_INVALID")

    def test_deleted_corrupt_symlink_and_permissive_state_fail_closed(self):
        with self.assertRaises(offline.OfflineSafetyDenied):
            self.guard.enroll_synthetic("REAL_PUBLIC_ACCOUNT_ID",self.account_a)
        with self.assertRaises(offline.OfflineSafetyDenied):
            offline.OfflineDurableSafetyRehearsal.create_fixture(
                self.path,phrase="maybe create")
        with sqlite3.connect(self.guard.db_path) as con:
            con.execute("DROP TABLE offline_guard")
        with self.assertRaises(offline.OfflineSafetyDenied):
            self.guard.admit_synthetic(self.owner_a,self.account_a)
        with self.assertRaises(offline.OfflineSafetyDenied):
            self.guard.is_stopped()
        self.guard.db_path.unlink()
        with self.assertRaises(offline.OfflineSafetyDenied) as caught:
            self.guard.admit_synthetic(self.owner_a,self.account_a)
        self.assertEqual(caught.exception.code,"STATE_UNAVAILABLE")
        self.assertFalse(self.guard.db_path.exists())
        os.chmod(self.path,0o755)
        with self.assertRaises(offline.OfflineSafetyDenied):
            offline.OfflineDurableSafetyRehearsal(self.path)

    def test_stop_cannot_be_cleared_through_sql_trigger(self):
        self.guard.emergency_stop()
        with sqlite3.connect(self.guard.db_path) as con:
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("UPDATE offline_guard SET stopped=0 WHERE id=1")
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("DELETE FROM offline_guard")
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("DELETE FROM offline_audit")
        self.assertTrue(self.guard.is_stopped())
        with self.assertRaises(offline.OfflineSafetyDenied) as caught:
            self.guard.resume_paused_synthetic(
                self.owner_b,self.account_b,expected_revision=1,
                phrase=offline.PAUSE_CLEAR_PHRASE)
        self.assertEqual(caught.exception.code,"EMERGENCY_STOP")

    def test_dormant_not_wired_to_production_or_real_public(self):
        app = (ROOT/"backend/app.py").read_text()
        worker = (ROOT/"backend/engine/automation_worker.py").read_text()
        module = "tenant_public_durable_safety_rehearsal"
        self.assertNotIn(module,app)
        self.assertNotIn(module,worker)
        self.assertFalse(wire.NETWORK_ENABLED)
        report = tenant_route_audit.inspect_sources(app,worker)
        self.assertFalse(report["crossAccountProductionCutoverAllowed"])
        self.assertFalse(report["productionKillSwitchDeployed"])
        for a,w in ((app+"\nfrom engine import "+module+"\n",worker),
                    (app,worker+"\nfrom engine import "+module+"\n")):
            with self.assertRaises(tenant_route_audit.ApiBoundaryError):
                tenant_route_audit.inspect_sources(a,w)


if __name__=="__main__":
    unittest.main()
