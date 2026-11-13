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
        self.assertEqual(results.count("ADMITTED"),2,results)
        # The SQLite lock guarantees exactly two admissions. A losing
        # process may fail closed with STATE_UNAVAILABLE under contention,
        # or CLOCK_INVALID if its timestamp was sampled before acquiring the
        # serialized write lock and another process advanced last_at.
        # A CLOCK_INVALID response remains a strict refusal, not a bypass.
        # The separate clock-regression test still requires rejection of
        # a genuinely backward clock. Never admit more than the limit.
        self.assertEqual(len(results),8,results)
        self.assertEqual(sum(result in (
            "BUDGET_EXHAUSTED", "STATE_UNAVAILABLE", "CLOCK_INVALID")
            for result in results),6,results)
        with sqlite3.connect(self.guard.db_path) as db:
            persisted=db.execute("""SELECT COUNT(*) FROM offline_usage
                WHERE owner_id=? AND account_id=?""",
                (self.owner_a,self.account_a)).fetchone()[0]
        self.assertEqual(persisted,2)
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

    def test_lease_validation_rejects_backward_clock(self):
        lease = self.guard.admit_synthetic(self.owner_a,self.account_a)["leaseId"]
        self.now[0] -= 1
        with self.assertRaises(offline.OfflineSafetyDenied) as caught:
            self.guard.revalidate_synthetic(self.owner_a,self.account_a,lease)
        self.assertEqual(caught.exception.code,"CLOCK_INVALID")

    def test_expired_leases_pruned_on_next_safe_admission(self):
        stale = self.guard.admit_synthetic(self.owner_a,self.account_a)["leaseId"]
        self.now[0] += offline.LEASE_SECONDS + 1
        current = self.guard.admit_synthetic(self.owner_a,self.account_a)["leaseId"]
        with sqlite3.connect(self.guard.db_path) as con:
            ids = [row[0] for row in con.execute("SELECT lease_id FROM offline_leases")]
        self.assertNotIn(stale,ids)
        self.assertEqual(ids,[current])
        with self.assertRaises(offline.OfflineSafetyDenied) as caught:
            self.guard.revalidate_synthetic(self.owner_a,self.account_a,stale)
        self.assertEqual(caught.exception.code,"STALE_LEASE")

    def test_sqlite_handle_closes_on_inode_validation_failure(self):
        from unittest.mock import patch
        original_connect = sqlite3.connect
        opened = []

        class TrackedConnection:
            def __init__(self, inner):
                self.inner = inner
                self.closed = False

            def __getattr__(self, name):
                return getattr(self.inner,name)

            def close(self):
                self.closed = True
                return self.inner.close()

        def tracked_connect(*args,**kwargs):
            wrapped = TrackedConnection(original_connect(*args,**kwargs))
            opened.append(wrapped)
            return wrapped

        original_private_file = self.guard._private_file
        db_checks = [0]

        def changed_inode(path):
            result = original_private_file(path)
            if path == self.guard.db_path:
                db_checks[0] += 1
                if db_checks[0] == 2:
                    return (result[0],result[1] + 1)
            return result

        with patch.object(offline.sqlite3,"connect",side_effect=tracked_connect):
            with patch.object(self.guard,"_private_file",side_effect=changed_inode):
                with self.assertRaises(offline.OfflineSafetyDenied) as caught:
                    self.guard.is_stopped()
        self.assertEqual(caught.exception.code,"STATE_UNAVAILABLE")
        self.assertEqual(len(opened),1)
        self.assertTrue(opened[0].closed)

    def test_fixture_requires_standard_scratch_even_if_tmpdir_redirected(self):
        # No external mount or custom TMPDIR may turn this fixture into a
        # production-disk store. It is not a persistent service.
        from unittest.mock import patch
        with patch.object(offline.tempfile,"gettempdir",return_value="/data"):
            with self.assertRaises(offline.OfflineSafetyDenied) as caught:
                offline.OfflineDurableSafetyRehearsal(self.path)
            self.assertEqual(caught.exception.code,"STATE_UNAVAILABLE")
        with tempfile.TemporaryDirectory(prefix="edgepilot-outside-scratch-",
                                         dir="/dev/shm") as outside:
            with self.assertRaises(offline.OfflineSafetyDenied) as caught:
                offline.OfflineDurableSafetyRehearsal(outside)
            self.assertEqual(caught.exception.code,"STATE_UNAVAILABLE")

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
        incident = self.guard.audit_summary()
        self.assertTrue(incident["emergencyStopped"])
        self.assertEqual(incident["eventCounts"]["STOP"],1)
        self.assertFalse(incident["productionIntegrated"])
        self.assertNotIn(self.account_a,str(incident))
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
