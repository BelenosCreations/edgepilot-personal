"""Phase 6: all-history owner evidence vs quarantine on isolated synthetic DBs."""
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from engine import (historical_reconciliation as history,
                    owner_shadow_migration as shadow,
                    migration_preflight, ledger, reconcile, order_audit,
                    engine_config, automation, observation_health)

ROOT=Path(__file__).resolve().parents[2]
UTC="2026-11-09T08:00:00+00:00"


class Phase6HistoricalReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir="/dev/shm")
        self.path=Path(self.temp.name)/"isolated.db"
        self.key=Fernet.generate_key().decode()
        cipher=Fernet(self.key.encode()).encrypt(b"ONLY-A-FAKE-TEST-PUBLIC-CREDENTIAL-0001")
        with sqlite3.connect(self.path) as c:
            c.executescript("""
                CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT NOT NULL);
                CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY,ciphertext BLOB,updated_at TEXT);
                CREATE TABLE account_snapshots(id INTEGER PRIMARY KEY,account TEXT NOT NULL,
                  ts TEXT NOT NULL,total_value TEXT NOT NULL,buying_power TEXT NOT NULL);
                CREATE TABLE orders(id TEXT PRIMARY KEY,account TEXT,symbol TEXT,
                  event TEXT,side TEXT,qty INTEGER,limit_price TEXT,reserved TEXT,
                  state TEXT,created TEXT,broker_reply TEXT);
                CREATE TABLE activity(id INTEGER PRIMARY KEY,ts TEXT,message TEXT);
                CREATE TABLE watch(id TEXT PRIMARY KEY,event TEXT,symbol TEXT,fair_pct TEXT,
                  buy_below TEXT,sell_above TEXT,quantity INTEGER,enabled INTEGER DEFAULT 0);
                CREATE TABLE ai_runs(id INTEGER PRIMARY KEY,created TEXT,note TEXT);
                CREATE TABLE edge_sessions(token_hash TEXT PRIMARY KEY);
                CREATE TABLE edge_login_failures(id INTEGER PRIMARY KEY);
            """)
            c.executemany("INSERT INTO settings VALUES(?,?)",[
                ("account_id","TEST-BROKER-A"),("profile_label","My EdgePilot"),
                ("risk_profile","aggressive"),("live_armed","0")])
            c.execute("INSERT INTO broker_credentials VALUES('public',?,?)",(cipher,UTC))
            c.execute("INSERT INTO account_snapshots VALUES(1,'TEST-BROKER-A',?,?,?)",
                      (UTC,"123.00","24.00"))
            c.execute("""INSERT INTO orders(id,account,symbol,state)
                VALUES('order-1','TEST-BROKER-A','SPY','NEW')""")
            c.execute("""INSERT INTO orders(id,account,symbol,state)
                VALUES('order-2',NULL,'QQQ','NEW')""")
            c.execute("INSERT INTO activity VALUES(1,?,'private audit comment')",(UTC,))
            c.execute("INSERT INTO watch(id,symbol) VALUES('w1','SPY')")
            c.execute("INSERT INTO ai_runs VALUES(1,?,'private question')",(UTC,))
            c.execute("INSERT INTO edge_sessions VALUES('test-token-hash')")
        ledger.setup(str(self.path))
        reconcile.setup(str(self.path))
        order_audit.setup(str(self.path))
        engine_config.setup(str(self.path))
        automation.setup(str(self.path))
        observation_health.setup(str(self.path))
        with sqlite3.connect(self.path) as c:
            c.execute("""INSERT INTO broker_fills VALUES
                ('fill1','TEST-BROKER-A','SPY','BUY','1','100','0','EXTERNAL',?,?)""",
                (UTC,UTC))
            c.execute("INSERT INTO sync_runs VALUES(1,'TEST-BROKER-A',?,'READ_ONLY_COMPLETE',0,1,'ok')",(UTC,))
            c.execute("INSERT INTO observed_orders(account,order_id,status,side,symbol,created_at,filled_quantity,last_seen,origin,raw_json) VALUES('TEST-BROKER-A','orderX','NEW','BUY','SPY',?,'0',?,'UNVERIFIED','{}')",(UTC,UTC))
            c.execute("INSERT INTO automation_events VALUES(1,?,'auto','RUNNING','Observe only')",(UTC,))
            c.execute("INSERT INTO engine_configs VALUES('auto','{}',?)",(UTC,))
            c.execute("INSERT INTO observation_cycles VALUES(1,?,'observe','OK','CLOSED','[\"SPY\"]',1,0,1,NULL)",(UTC,))
            c.execute("INSERT INTO paper_positions(id,engine,asset_class,symbol,strategy,qty,entry_ask,entry_fee,opened_at,last_bid,last_ask,status) VALUES('paper1','auto','stock','SPY','TEST','1','100','0',?,'99','100','OPEN')",(UTC,))
        self.flags=patch.dict(os.environ,{shadow.ENABLE_FLAG:"true"})
        self.flags.start()

    def tearDown(self):
        self.flags.stop()
        self.temp.cleanup()

    def _staged(self):
        work=Path(self.temp.name)/"target.db"
        with sqlite3.connect(self.path) as a,sqlite3.connect(work) as b:
            a.backup(b)
        report=migration_preflight.inspect_database(work)
        with shadow._conn(work) as con:
            summary=shadow._stage(con,self.key,report)
        return work,summary

    def test_account_labeled_rows_and_ambiguous_activity_are_distinct(self):
        original=hashlib.sha256(self.path.read_bytes()).hexdigest()
        work,stage=self._staged()
        hist=stage["historicalReconciliation"]
        self.assertTrue(hist["allRowsInventoried"])
        self.assertFalse(hist["fullHistoryMigrated"])
        self.assertFalse(hist["ordersOrFillsInferred"])
        self.assertFalse(hist["cutoverReady"])
        self.assertEqual(stage["snapshotRowsMapped"],1)
        self.assertEqual(stage["observationRowsMapped"],1)
        self.assertIn("orders",hist["accountLabeledTables"])
        self.assertIn("broker_fills",hist["accountLabeledTables"])
        self.assertIn("automation_events",hist["quarantinedTables"])
        self.assertIn("paper_positions",hist["quarantinedTables"])
        self.assertIn("observation_cycles",hist["quarantinedTables"])
        self.assertIn("edge_sessions",hist["quarantinedTables"])
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),original)
        self.assertEqual(hist["unexplainedRows"],0)
        with sqlite3.connect(work) as c:
            c.row_factory=sqlite3.Row
            self.assertEqual(c.execute("""SELECT classification FROM
                tenant_shadow_history_index WHERE source_table='broker_fills'""").fetchone()[0],
                history.EXPLICIT)
            self.assertEqual(c.execute("""SELECT classification FROM
                tenant_shadow_history_index WHERE source_table='observation_cycles'""").fetchone()[0],
                history.QUARANTINE)
            self.assertEqual([r[0] for r in c.execute("""SELECT classification FROM
                tenant_shadow_history_index WHERE source_table='orders'
                ORDER BY source_rowid""")],[history.EXPLICIT,history.AMBIGUOUS])
            self.assertEqual(c.execute("""SELECT COUNT(*) FROM tenant_shadow_history_index
                WHERE classification='ACCOUNT_LABEL_VERIFIED'
                AND (account_id IS NULL OR user_id IS NULL)""").fetchone()[0],0)
            self.assertEqual(c.execute("""SELECT COUNT(*) FROM tenant_shadow_history_index
                WHERE classification!='ACCOUNT_LABEL_VERIFIED'
                AND classification!='ALREADY_SHADOW_MAPPED'
                AND (account_id IS NOT NULL OR user_id IS NOT NULL)""").fetchone()[0],0)
            for row in c.execute("SELECT source_table,recorded_count FROM tenant_shadow_history_inventory"):
                n=c.execute("SELECT COUNT(*) FROM tenant_shadow_history_index WHERE source_table=?",
                            (row["source_table"],)).fetchone()[0]
                self.assertEqual(row["recorded_count"],n)
            self.assertFalse(c.execute("PRAGMA foreign_key_check").fetchall())
            self.assertEqual(c.execute("SELECT COUNT(*) FROM tenant_identity_sessions").fetchone()[0]
                             if c.execute("SELECT 1 FROM sqlite_master WHERE name='tenant_identity_sessions'").fetchone()
                             else 0,0)
            runtime=c.execute("SELECT worker_enabled,paper_enabled,live_enabled FROM tenant_runtime_status").fetchone()
            self.assertEqual(tuple(runtime),(0,0,0))
            self.assertEqual(c.execute("SELECT COUNT(*) FROM orders").fetchone()[0],2)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM broker_fills").fetchone()[0],1)
        result=json.dumps(hist)
        for val in ("TEST-BROKER-A","private question","test-token-hash","fill1"):
            self.assertNotIn(val,result)

    def test_mixed_account_from_any_explicit_source_fails_closed(self):
        for sql in (
            "INSERT INTO broker_fills VALUES ('fill2','OTHER','QQQ','BUY','1','5','0','EXTERNAL','"+UTC+"','"+UTC+"')",
            "INSERT INTO sync_runs VALUES (2,'OTHER','"+UTC+"','READ_ONLY_COMPLETE',0,1,'ok')",
            "INSERT INTO observed_orders(account,order_id,status,side,symbol,created_at,filled_quantity,last_seen,origin,raw_json) VALUES('OTHER','orderY','NEW','BUY','SPY','"+UTC+"','0','"+UTC+"','UNVERIFIED','{}')",
        ):
            with self.subTest(sql=sql[:60]):
                with sqlite3.connect(self.path) as c:
                    c.execute(sql)
                try:
                    with self.assertRaises((history.HistoryReconciliationError,
                                            shadow.ShadowMigrationError)):
                        self._staged()
                finally:
                    with sqlite3.connect(self.path) as c:
                        if "broker_fills" in sql: c.execute("DELETE FROM broker_fills WHERE id='fill2'")
                        elif "sync_runs" in sql:c.execute("DELETE FROM sync_runs WHERE id=2")
                        else:c.execute("DELETE FROM observed_orders WHERE account='OTHER'")

    def test_unknown_table_is_inventory_only_not_owner_linked(self):
        with sqlite3.connect(self.path) as c:
            c.execute("CREATE TABLE hypothetical_source(id INTEGER PRIMARY KEY,note TEXT)")
            c.execute("INSERT INTO hypothetical_source VALUES(1,'unsupported')")
        work,stage=self._staged()
        h=stage["historicalReconciliation"]
        self.assertIn("hypothetical_source",h["unknownTablesNeedingReview"])
        self.assertEqual(h["unexplainedRows"],1)
        with sqlite3.connect(work) as c:
            row=c.execute("""SELECT classification,user_id,account_id FROM
                tenant_shadow_history_index WHERE source_table='hypothetical_source'""").fetchone()
            self.assertEqual(row,(history.UNACCOUNTED,None,None))

    def test_full_rehearsal_preserves_source_and_remains_disabled(self):
        before=hashlib.sha256(self.path.read_bytes()).hexdigest()
        report=shadow.rehearse_owner_shadow(self.path,
            credential_key=self.key,phrase=shadow.APPROVAL_PHRASE)
        self.assertTrue(report["historicalReconciliation"]["allRowsInventoried"])
        self.assertTrue(report["sourceLogicalInventoryUnchanged"])
        self.assertFalse(report["productionDatabaseChanged"])
        self.assertFalse(report["tenantActivationAuthorized"])
        self.assertFalse(report["historicalReconciliation"]["fullHistoryMigrated"])
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),before)

    def test_scope_changes_fail_closed(self):
        with sqlite3.connect(self.path) as c:
            c.execute("ALTER TABLE observed_orders RENAME COLUMN account TO owner_account")
        with self.assertRaisesRegex(history.HistoryReconciliationError,
                                     "Account column missing"):
            self._staged()

    def test_no_live_wiring(self):
        app=(ROOT/"backend/app.py").read_text()
        worker=(ROOT/"backend/engine/automation_worker.py").read_text()
        self.assertNotIn("historical_reconciliation",app)
        self.assertNotIn("historical_reconciliation",worker)
        self.assertIn("'liveTradingAvailable':False",app)


if __name__=="__main__":
    unittest.main()
