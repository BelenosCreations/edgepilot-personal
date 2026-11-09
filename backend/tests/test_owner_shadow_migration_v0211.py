"""Offline owner shadow rehearsal: real schema shapes, redaction and rollback gates."""
import base64
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from engine import owner_shadow_migration as shadow, tenant_foundation, identity_auth, account_scope

ROOT=Path(__file__).resolve().parents[2]
PHRASE=shadow.APPROVAL_PHRASE
UTC="2026-11-09T08:00:00+00:00"


class ShadowOwnerMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir="/dev/shm")
        self.path=Path(self.temp.name)/"restored-isolated.db"
        self.key=Fernet.generate_key().decode("ascii")
        self.badkey=Fernet.generate_key().decode("ascii")
        self.secret="fixture-only-public-secret-not-a-real-key-2026"
        self.ciphertext=Fernet(self.key.encode()).encrypt(self.secret.encode())
        with sqlite3.connect(self.path) as conn:
            conn.executescript("""
                CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT NOT NULL);
                CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY,ciphertext BLOB,updated_at TEXT);
                CREATE TABLE account_snapshots(id INTEGER PRIMARY KEY,account TEXT NOT NULL,
                  ts TEXT NOT NULL,total_value TEXT NOT NULL,buying_power TEXT NOT NULL);
                CREATE TABLE observation_cycles(id INTEGER PRIMARY KEY,
                  completed_at TEXT NOT NULL,mode TEXT NOT NULL,state TEXT NOT NULL,
                  market_session TEXT NOT NULL,symbols_json TEXT NOT NULL,
                  quotes_accepted INTEGER NOT NULL,quotes_rejected INTEGER NOT NULL,
                  quote_age_seconds INTEGER,issue TEXT);
                CREATE TABLE activity(id INTEGER PRIMARY KEY,ts TEXT,message TEXT);
                CREATE TABLE automation_master(id INTEGER PRIMARY KEY,mode TEXT,enabled INTEGER);
                CREATE TABLE orders(id TEXT PRIMARY KEY,account TEXT,symbol TEXT);
            """)
            conn.executemany("INSERT INTO settings VALUES(?,?)",[
                ("account_id","TEST-PUBLIC-ONLY"),
                ("profile_label","My EdgePilot"),
                ("live_armed","0"),
                ("protected_pct","50"),
                ("micro_enabled","0"),
                ("ai_enabled","0"),
                ("chatgpt_connector_enabled","0"),
            ])
            conn.execute("INSERT INTO broker_credentials VALUES('public',?,?)",
                         (self.ciphertext,UTC))
            conn.executemany("INSERT INTO account_snapshots VALUES(?,?,?,?,?)",[
                (1,"TEST-PUBLIC-ONLY",UTC,"110.01","50.00"),
                (9,"TEST-PUBLIC-ONLY",UTC,"111.52","48.24"),
            ])
            conn.executemany("INSERT INTO observation_cycles VALUES(?,?,?,?,?,?,?,?,?,?)",[
                (2,UTC,"observe","OK","CLOSED",'["SPY","QQQ"]',2,0,4,None),
                (8,UTC,"observe","PARTIAL","OPEN",'["SPY"]',1,1,15,"fixture warning"),
            ])
            conn.execute("INSERT INTO activity VALUES(1,?,?)",(UTC,"Private note: not for output"))
            conn.execute("INSERT INTO automation_master VALUES(1,'observe',1)")
            conn.execute("INSERT INTO orders VALUES('local-order','TEST-PUBLIC-ONLY','SPY')")
        self.flag=patch.dict(os.environ,{shadow.ENABLE_FLAG:"true"})
        self.flag.start()

    def tearDown(self):
        self.flag.stop()
        self.temp.cleanup()

    def run_rehearsal(self,**kwargs):
        return shadow.rehearse_owner_shadow(self.path,credential_key=self.key,
            phrase=PHRASE,**kwargs)

    def test_successful_mapping_is_temporary_reconciled_and_redacted(self):
        before=hashlib.sha256(self.path.read_bytes()).hexdigest()
        report=self.run_rehearsal()
        self.assertEqual(report["snapshotRowsMapped"],2)
        self.assertEqual(report["observationRowsMapped"],2)
        self.assertEqual(report["settingsQuarantined"],7)
        self.assertTrue(report["credentialVerifiedWithoutDisclosure"])
        self.assertTrue(report["brokerCredentialCiphertextCopied"])
        self.assertTrue(report["stagingOnly"])
        self.assertFalse(report["cutoverReady"])
        self.assertFalse(report["workerEnabled"])
        self.assertFalse(report["liveEnabled"])
        self.assertFalse(report["paperEnabled"])
        self.assertEqual(report["newIdentitySessions"],0)
        self.assertFalse(report["migrationExecutedOnProduction"])
        self.assertTrue(report["isolatedIntegrityVerified"])
        self.assertTrue(report["sourceLogicalInventoryUnchanged"])
        self.assertIn("activity",report["pendingHistoricalTables"])
        self.assertIn("automation_master",report["pendingHistoricalTables"])
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),before)
        self.assertEqual({p.name for p in self.path.parent.iterdir()},{self.path.name})
        for private in ("TEST-PUBLIC-ONLY","fixture-only-public-secret",
                        "Private note: not for output","local-order"):
            self.assertNotIn(private,json.dumps(report))
        with sqlite3.connect(self.path) as con:
            self.assertFalse(con.execute("SELECT 1 FROM sqlite_master WHERE name='tenant_users'").fetchone())
            self.assertEqual(con.execute("SELECT COUNT(*) FROM observation_cycles").fetchone()[0],2)
            self.assertEqual(con.execute("SELECT ciphertext FROM broker_credentials").fetchone()[0],
                             self.ciphertext)
        # Repeated rehearsals always start from an unchanged source.
        again=self.run_rehearsal()
        self.assertEqual(again["snapshotRowsMapped"],2)
        self.assertEqual(again["observationRowsMapped"],2)

    def test_disposable_target_preserves_provenance_and_never_enables_runtime(self):
        # Inspect the shadow copy *only* inside a fixture, before disposal.
        from engine import migration_preflight
        target=Path(self.temp.name)/"shadow-inspection.db"
        with sqlite3.connect(self.path) as source, sqlite3.connect(target) as dest:
            source.backup(dest)
        inventory=migration_preflight.inspect_database(target)
        with shadow._conn(target) as conn:
            staged=shadow._stage(conn,self.key,inventory)
        self.assertEqual(staged["snapshotRowsMapped"],2)
        with sqlite3.connect(target) as c:
            c.row_factory=sqlite3.Row
            c.execute("PRAGMA foreign_keys=ON")
            self.assertIsNone(c.execute("PRAGMA foreign_key_check").fetchone())
            self.assertEqual(c.execute("SELECT COUNT(*) FROM tenant_users").fetchone()[0],1)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM tenant_accounts").fetchone()[0],1)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM tenant_identities").fetchone()[0]
                             if c.execute("SELECT 1 FROM sqlite_master WHERE name='tenant_identities'").fetchone()
                             else 0,0)
            owner=c.execute("SELECT user_id FROM tenant_users").fetchone()["user_id"]
            account=c.execute("SELECT account_id FROM tenant_accounts").fetchone()["account_id"]
            self.assertEqual(c.execute("SELECT credential_ciphertext FROM tenant_connections").fetchone()[0],
                             self.ciphertext)
            self.assertEqual([tuple(x) for x in c.execute(
                "SELECT account_value,buying_power FROM tenant_portfolio_snapshots ORDER BY snapshot_id")],
                [("110.01","50.00"),("111.52","48.24")])
            self.assertEqual([tuple(x) for x in c.execute(
                "SELECT mode,state,market_session,accepted,rejected FROM tenant_observation_cycles ORDER BY cycle_id")],
                [("observe","OK","CLOSED",2,0),("observe","PARTIAL","OPEN",1,1)])
            self.assertEqual([tuple(x) for x in c.execute(
                "SELECT source_table,source_id FROM tenant_shadow_lineage ORDER BY source_table,source_id")],
                [("account_snapshots",1),("account_snapshots",9),
                 ("observation_cycles",2),("observation_cycles",8)])
            runtime=c.execute("SELECT * FROM tenant_runtime_status").fetchone()
            self.assertEqual((runtime["worker_enabled"],runtime["paper_enabled"],
                              runtime["live_enabled"],runtime["requested_mode"]),
                             (0,0,0,"observe"))
            self.assertEqual(c.execute("SELECT COUNT(*) FROM tenant_shadow_settings").fetchone()[0],7)
            self.assertEqual(c.execute("SELECT source_value FROM tenant_shadow_settings WHERE source_key='account_id'").fetchone()[0],
                             "TEST-PUBLIC-ONLY")
            self.assertEqual(c.execute("SELECT COUNT(*) FROM orders").fetchone()[0],1)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM activity").fetchone()[0],1)
            self.assertEqual(c.execute("SELECT staging_state FROM tenant_shadow_rehearsal_marker").fetchone()[0],
                             "REHEARSED_ONLY")

    def test_rejects_wrong_key_without_leaking_credentials(self):
        before=self.path.read_bytes()
        with self.assertRaisesRegex(shadow.ShadowMigrationError,"verification failed") as context:
            shadow.rehearse_owner_shadow(self.path,credential_key=self.badkey,phrase=PHRASE)
        self.assertNotIn(self.secret,str(context.exception))
        self.assertEqual(before,self.path.read_bytes())

    def test_refuses_missing_account_and_unverified_credential(self):
        with sqlite3.connect(self.path) as c:
            c.execute("UPDATE settings SET v='' WHERE k='account_id'")
        with self.assertRaisesRegex(shadow.ShadowMigrationError,"unavailable"):
            self.run_rehearsal()
        with sqlite3.connect(self.path) as c:
            c.execute("UPDATE settings SET v='TEST-PUBLIC-ONLY' WHERE k='account_id'")
            c.execute("UPDATE broker_credentials SET ciphertext=NULL")
        with self.assertRaisesRegex(shadow.ShadowMigrationError,"unavailable"):
            self.run_rehearsal()

    def test_fail_closed_if_multiple_account_references_found(self):
        with sqlite3.connect(self.path) as c:
            c.execute("INSERT INTO account_snapshots VALUES(10,'OTHER',?,?,?)",
                      (UTC,"1.00","1.00"))
        with self.assertRaisesRegex(shadow.ShadowMigrationError,"Multiple account"):
            self.run_rehearsal()

    def test_refuses_order_history_from_other_account(self):
        with sqlite3.connect(self.path) as c:
            c.execute("INSERT INTO orders VALUES('another','OTHER','QQQ')")
        with self.assertRaisesRegex(shadow.ShadowMigrationError,"Conflicting account"):
            self.run_rehearsal()

    def test_invalid_history_rejected_not_silently_dropped(self):
        with sqlite3.connect(self.path) as c:
            c.execute("UPDATE account_snapshots SET total_value='NaN' WHERE id=1")
        with self.assertRaises(shadow.ShadowMigrationError):
            self.run_rehearsal()
        with sqlite3.connect(self.path) as c:
            c.execute("UPDATE account_snapshots SET total_value='110.01' WHERE id=1")
            c.execute("UPDATE observation_cycles SET symbols_json='[\"SPY;X\"]' WHERE id=2")
        with self.assertRaises(shadow.ShadowMigrationError):
            self.run_rehearsal()

    def test_refuses_existing_tenants(self):
        tenant_foundation.setup(str(self.path))
        tenant_foundation.TenantStore(self.path).provision_user("An existing user","owner")
        with self.assertRaisesRegex(shadow.ShadowMigrationError,"Existing tenant"):
            self.run_rehearsal()

    def test_default_disabled_and_wrong_phrase(self):
        with patch.dict(os.environ,{shadow.ENABLE_FLAG:"false"}):
            with self.assertRaisesRegex(shadow.ShadowMigrationError,"disabled"):
                self.run_rehearsal()
        with self.assertRaisesRegex(shadow.ShadowMigrationError,"disabled"):
            shadow.rehearse_owner_shadow(self.path,credential_key=self.key,
                                         phrase="MIGRATE TO PRODUCTION")

    def test_schema_and_runtime_boundaries(self):
        source=(ROOT/"backend/engine/owner_shadow_migration.py").read_text()
        app=(ROOT/"backend/app.py").read_text()
        worker=(ROOT/"backend/engine/automation_worker.py").read_text()
        self.assertNotIn("owner_shadow_migration",app)
        self.assertNotIn("owner_shadow_migration",worker)
        self.assertIn("'liveTradingAvailable':False",app)
        self.assertIn("SHADOW REHEARSAL ONLY",source)
        self.assertIn("REHEARSED_ONLY",source)
        self.assertIn("BEGIN IMMEDIATE",source)
        self.assertNotIn("DELETE FROM settings",source)
        self.assertNotIn("UPDATE automation_master",source)
        self.assertNotIn("public.com",source)

    def test_cli_uses_only_environment_key_and_does_not_reveal_values(self):
        tool=ROOT/"backend/tools/owner_shadow_rehearsal.py"
        environment={**os.environ,"EDGE_CREDENTIAL_KEY":self.key}
        cmd=[sys.executable,str(tool),"--database",str(self.path),
             "--approve",PHRASE]
        result=subprocess.run(cmd,env=environment,capture_output=True,text=True,timeout=35)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('"stagingOnly": true',result.stdout)
        self.assertNotIn("TEST-PUBLIC-ONLY",result.stdout)
        self.assertNotIn(self.secret,result.stdout)
        self.assertNotIn(self.key,result.stdout)


    def test_memory_only_source_gate_rejects_disk_and_symlink(self):
        with tempfile.TemporaryDirectory() as outside:
            disk=Path(outside)/"plaintext-disk.db"
            with sqlite3.connect(self.path) as src,sqlite3.connect(disk) as dest:
                src.backup(dest)
            with self.assertRaisesRegex(shadow.ShadowMigrationError,"tmpfs"):
                shadow.rehearse_owner_shadow(disk,credential_key=self.key,phrase=PHRASE)
            linked=Path(self.temp.name)/"link.db"
            linked.symlink_to(disk)
            with self.assertRaisesRegex(shadow.ShadowMigrationError,"tmpfs"):
                shadow.rehearse_owner_shadow(linked,credential_key=self.key,phrase=PHRASE)
        self.assertTrue(self.path.exists())

    def test_shadow_temp_directory_removed_after_rollback(self):
        memory=Path("/dev/shm")
        baseline={p.name for p in memory.glob("edgepilot-shadow-rehearsal-*")}
        original=hashlib.sha256(self.path.read_bytes()).hexdigest()
        with patch.object(
                shadow.historical_reconciliation,"verify_shadow_index",
                side_effect=shadow.historical_reconciliation.HistoryReconciliationError(
                    "Historical row provenance mismatch")):
            with self.assertRaisesRegex(shadow.ShadowMigrationError,"provenance mismatch"):
                self.run_rehearsal()
        self.assertEqual(baseline,{p.name for p in memory.glob(
            "edgepilot-shadow-rehearsal-*")})
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),original)

    def test_same_count_mutation_detected_by_fingerprint(self):
        from engine import migration_preflight
        target=Path(self.temp.name)/"fingerprint-target.db"
        with sqlite3.connect(self.path) as src,sqlite3.connect(target) as dest:
            src.backup(dest)
        inv=migration_preflight.inspect_database(target)
        with shadow._conn(target) as c:
            shadow._stage(c,self.key,inv)
        with sqlite3.connect(target) as c:
            c.execute("UPDATE activity SET message='altered in isolated target' WHERE id=1")
        with shadow._conn(target,readonly=True) as c:
            with self.assertRaisesRegex(
                shadow.historical_reconciliation.HistoryReconciliationError,
                "provenance mismatch"):
                shadow.historical_reconciliation.verify_shadow_index(c,inv["tableCounts"])

    def test_report_has_memory_and_content_and_quarantine_guarantees(self):
        result=self.run_rehearsal()
        for key in ("temporaryStorageVerifiedMemoryBacked",
                    "disposableWorkingCopyRemoved",
                    "sourceContentsUnchanged","sourceToCopyContentsMatched",
                    "historicalRowFingerprintsVerified"):
            self.assertTrue(result[key])
        review=result["historicalReconciliation"]["quarantineReview"]
        self.assertEqual(review["quarantinedRowsReviewed"],
            result["historicalReconciliation"]["quarantinedRows"]+
            result["historicalReconciliation"]["unexplainedRows"])
        self.assertTrue(review["everyQuarantinedRowHasReviewPolicy"])
        self.assertTrue(review["noAutomaticOwnerAssignments"])
        self.assertFalse(review["readyForCutover"])
        self.assertIn("unscoped_observations",review["groups"])
        self.assertIn("configuration_and_watchlists",review["groups"])
        self.assertNotIn("TEST-PUBLIC-ONLY",json.dumps(review))


if __name__=="__main__":
    unittest.main()
