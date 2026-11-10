"""v0.2.14: isolated dormant history storage, read authorization and rollback."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from engine import (
    tenant_history, tenant_foundation, identity_auth, account_scope,
    owner_shadow_migration as shadow, migration_preflight
)

ROOT=Path(__file__).resolve().parents[2]


class TenantHistoryIsolationTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(dir="/dev/shm")
        self.db=Path(self.folder.name)/"inactive-tenants.sqlite3"
        tenant_foundation.setup(str(self.db))
        identity_auth.setup(str(self.db))
        with tenant_history._db(self.db) as con:
            tenant_history.prepare(con)
        key=Fernet.generate_key().decode()
        store=tenant_foundation.TenantStore(self.db,credential_key=key)
        self.a=store.provision_user("Owner A","owner")
        self.b=store.provision_user("Owner B","owner")
        self.a_conn=store.add_connection(self.a,"FAKE-PUBLIC-CREDENTIAL-FOR-OWNER-A-123456789")
        self.b_conn=store.add_connection(self.b,"FAKE-PUBLIC-CREDENTIAL-FOR-OWNER-B-123456789")
        self.a_one=store.link_account(self.a,self.a_conn,"A-PUBLIC-ONE","A primary")
        self.a_two=store.link_account(self.a,self.a_conn,"A-PUBLIC-TWO","A secondary")
        self.b_one=store.link_account(self.b,self.b_conn,"B-PUBLIC-ONE","B private")
        self.identity=identity_auth.IdentityStore(str(self.db))
        self.identity.provision(self.a,"owner_a","very-long-synthetic-password-A")
        self.identity.provision(self.b,"owner_b","very-long-synthetic-password-B")
        self.a_token=self.identity.authenticate(
            "owner_a","very-long-synthetic-password-A","synthetic-device-A")["token"]
        self.b_token=self.identity.authenticate(
            "owner_b","very-long-synthetic-password-B","synthetic-device-B")["token"]
        self.reader=tenant_history.DormantHistoryReader(self.db,self.identity)
        self._write(self.a,self.a_one,[("sync_transactions",1),("scan_runs",2)])
        self._write(self.a,self.a_two,[("account_snapshots",1)])
        self._write(self.b,self.b_one,[("sync_transactions",1),("orders",2)])

    def tearDown(self):
        self.folder.cleanup()

    def _write(self,user,account,spec):
        batch=str(uuid.uuid4())
        digest="a"*64
        with tenant_history._db(self.db) as con:
            con.execute("""INSERT INTO tenant_history_batches
                (batch_id,user_id,account_id,source_schema_sha256,
                 expected_references,staged_at)
                VALUES(?,?,?,?,?,?)""",(batch,user,account,digest,len(spec),
                                         "2026-11-09T19:00:00+00:00"))
            for table,rowid in spec:
                con.execute("""INSERT INTO tenant_history_references
                    (batch_id,user_id,account_id,source_table,source_rowid,
                    source_sha256,kind)
                    VALUES(?,?,?,?,?,?,?)""",(batch,user,account,table,rowid,
                                               "b"*64,tenant_history.KINDS[table]))

    def test_sessions_isolate_users_and_two_accounts_same_owner(self):
        first=self.reader.summary(self.a_token,self.a_one)
        other=self.reader.summary(self.a_token,self.a_two)
        b=self.reader.summary(self.b_token,self.b_one)
        self.assertEqual((first["referenceCount"],other["referenceCount"],b["referenceCount"]),(2,1,2))
        self.assertEqual(first["categories"]["BROKER_TRANSACTION_REFERENCE"],1)
        self.assertTrue(first["referenceOnly"])
        self.assertFalse(first["containsVerifiedBrokerFills"])
        self.assertFalse(first["canTrade"])
        a_page=self.reader.page(self.a_token,self.a_one,limit=10)
        b_page=self.reader.page(self.b_token,self.b_one,limit=10)
        self.assertEqual(len(a_page["items"]),2)
        self.assertEqual(len(b_page["items"]),2)
        self.assertEqual({x["source_table"] for x in a_page["items"]},
                         {"scan_runs","sync_transactions"})
        self.assertEqual({x["source_table"] for x in b_page["items"]},
                         {"orders","sync_transactions"})
        # No user/account IDs, external account identifiers, raw source values
        # or source fingerprints are exposed by the read API.
        for text in (json.dumps(a_page),json.dumps(b_page)):
            self.assertNotIn(self.a,text)
            self.assertNotIn(self.b,text)
            self.assertNotIn("A-PUBLIC-ONE",text)
            self.assertNotIn("source_sha256",text)
            self.assertNotIn("record_payload",text)

    def test_foreign_account_and_revoked_session_denied(self):
        for token,account in (
            (self.a_token,self.b_one),
            (self.b_token,self.a_one),
            (self.b_token,self.a_two),
            ("fabricated-token-with-sufficient-length-000001",self.a_one),
        ):
            with self.subTest(account=account):
                with self.assertRaises(tenant_foundation.TenantAccessError):
                    self.reader.summary(token,account)
                with self.assertRaises(tenant_foundation.TenantAccessError):
                    self.reader.page(token,account)
        self.identity.revoke(self.a_token)
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.reader.summary(self.a_token,self.a_one)

    def test_disabled_user_account_and_revoked_public_connection_denied(self):
        with tenant_history._db(self.db) as con:
            con.execute("UPDATE tenant_accounts SET disabled_at='2026-11-09' WHERE account_id=?",
                        (self.a_two,))
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.reader.summary(self.a_token,self.a_two)
        # Other account of same owner remains available.
        self.assertEqual(self.reader.summary(self.a_token,self.a_one)["referenceCount"],2)
        with tenant_history._db(self.db) as con:
            con.execute("UPDATE tenant_connections SET revoked_at='2026-11-09' WHERE connection_id=?",
                        (self.b_conn,))
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.reader.summary(self.b_token,self.b_one)
        with tenant_history._db(self.db) as con:
            con.execute("UPDATE tenant_users SET disabled_at='2026-11-09' WHERE user_id=?",(self.a,))
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.reader.summary(self.a_token,self.a_one)

    def test_read_limit_and_cursor_are_scoped(self):
        page=self.reader.page(self.a_token,self.a_one,limit=1)
        self.assertEqual(len(page["items"]),1)
        self.assertIsNotNone(page["nextBeforeId"])
        second=self.reader.page(self.a_token,self.a_one,limit=1,before_id=page["nextBeforeId"])
        self.assertNotEqual(second["items"][0]["reference_id"],page["items"][0]["reference_id"])
        # Cursor from another account cannot bypass account WHERE clause.
        seen=self.reader.page(self.a_token,self.a_two,limit=10,
                             before_id=max(x["reference_id"] for x in
                                 self.reader.page(self.b_token,self.b_one)["items"]))
        self.assertTrue(all(x["source_table"]=="account_snapshots" for x in seen["items"]))
        for opts in ({"limit":0},{"limit":101},{"limit":True},{"before_id":-1},
                     {"before_id":"1"},{"before_id":True}):
            with self.assertRaises(ValueError):
                self.reader.page(self.a_token,self.a_one,**opts)

    def test_cross_tenant_forged_batch_and_repeated_source_denied(self):
        with tenant_history._db(self.db) as con:
            source=con.execute("""SELECT batch_id,source_table,source_rowid,source_sha256,kind
                FROM tenant_history_references WHERE user_id=? AND account_id=? LIMIT 1""",
                (self.a,self.a_one)).fetchone()
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("""INSERT INTO tenant_history_references
                    (batch_id,user_id,account_id,source_table,source_rowid,source_sha256,kind)
                    VALUES(?,?,?,?,?,?,?)""",
                    (source["batch_id"],self.b,self.b_one,
                     "scan_runs",99,"c"*64,"MARKET_SCAN_REFERENCE"))
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("""INSERT INTO tenant_history_references
                    (batch_id,user_id,account_id,source_table,source_rowid,source_sha256,kind)
                    VALUES(?,?,?,?,?,?,?)""",
                    (source["batch_id"],self.a,self.a_one,
                     source["source_table"],source["source_rowid"],
                     source["source_sha256"],source["kind"]))
        # Existing records survived attempted invalid inserts.
        self.assertEqual(self.reader.summary(self.a_token,self.a_one)["referenceCount"],2)
        self.assertEqual(self.reader.summary(self.b_token,self.b_one)["referenceCount"],2)

    def test_no_runtime_wiring(self):
        app=(ROOT/"backend/app.py").read_text()
        worker=(ROOT/"backend/engine/automation_worker.py").read_text()
        self.assertNotIn("tenant_history",app)
        self.assertNotIn("tenant_history",worker)
        self.assertIn("'liveTradingAvailable':False",app)


class ShadowHistoryStageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir="/dev/shm")
        self.path=Path(self.temp.name)/"restored-synthetic.db"
        self.key=Fernet.generate_key().decode()
        cipher=Fernet(self.key.encode()).encrypt(b"TEST-FAKE-PUBLIC-CREDENTIAL-ONLY-1234")
        with sqlite3.connect(self.path) as con:
            con.executescript("""
                CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT NOT NULL);
                CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY,ciphertext BLOB);
                CREATE TABLE account_snapshots(id INTEGER PRIMARY KEY,account TEXT NOT NULL,
                    ts TEXT NOT NULL,total_value TEXT NOT NULL,buying_power TEXT NOT NULL);
                CREATE TABLE observation_cycles(id INTEGER PRIMARY KEY,
                    completed_at TEXT NOT NULL,mode TEXT NOT NULL,state TEXT NOT NULL,
                    market_session TEXT NOT NULL,symbols_json TEXT NOT NULL,
                    quotes_accepted INTEGER NOT NULL,quotes_rejected INTEGER NOT NULL,
                    quote_age_seconds INTEGER,issue TEXT);
                CREATE TABLE sync_transactions(id INTEGER PRIMARY KEY,account TEXT,
                    provider_transaction_id TEXT);
                CREATE TABLE activity(id INTEGER PRIMARY KEY, note TEXT);
            """)
            con.executemany("INSERT INTO settings VALUES(?,?)",[
                ("account_id","TEST-ONLY-BROKER"),("profile_label","Synthetic")])
            con.execute("INSERT INTO broker_credentials VALUES('public',?)",(cipher,))
            con.execute("""INSERT INTO account_snapshots VALUES
                (1,'TEST-ONLY-BROKER','2026-11-09T19:00:00+00:00','125.00','90.00')""")
            con.execute("""INSERT INTO observation_cycles VALUES
                (1,'2026-11-09T19:01:00+00:00','observe','OK','CLOSED',
                '["SPY"]',1,0,3,NULL)""")
            con.execute("INSERT INTO sync_transactions VALUES(2,'TEST-ONLY-BROKER','reference-2')")
            con.execute("INSERT INTO activity VALUES(7,'Unscoped private activity')")
        self.flag=patch.dict(os.environ,{shadow.ENABLE_FLAG:"true"})
        self.flag.start()

    def tearDown(self):
        self.flag.stop()
        self.temp.cleanup()

    def test_disposable_history_references_exactly_match_labeled_records(self):
        before=hashlib.sha256(self.path.read_bytes()).hexdigest()
        report=shadow.rehearse_owner_shadow(self.path,credential_key=self.key,
                                            phrase=shadow.APPROVAL_PHRASE)
        self.assertEqual(report["historicalReconciliation"]["accountLabeledRows"],2)
        self.assertEqual(report["historicalReconciliation"]["quarantinedRows"],2)
        staged=report["tenantHistoricalReferences"]
        self.assertEqual(staged["referencesStaged"],2)
        self.assertEqual(staged["quarantinedRecordsImported"],0)
        self.assertTrue(staged["sourceRowsReconciled"])
        self.assertTrue(staged["referencesOnly"])
        self.assertFalse(staged["rawTradePayloadsMigrated"])
        self.assertFalse(staged["fillsOrOrdersExecuted"])
        self.assertFalse(staged["loginOrWorkerActivated"])
        self.assertFalse(staged["cutoverReady"])
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),before)

    def test_injected_failure_rolls_back_staging_and_removes_disposable_files(self):
        before=hashlib.sha256(self.path.read_bytes()).hexdigest()
        prior={p.name for p in Path("/dev/shm").glob("edgepilot-shadow-rehearsal-*")}
        with patch.object(tenant_history,"stage_from_reconciled_history",
                          side_effect=tenant_history.TenantHistoryError(
                              "Historical reference reconciliation failed")):
            with self.assertRaisesRegex(shadow.ShadowMigrationError,
                                        "Historical reference reconciliation"):
                shadow.rehearse_owner_shadow(self.path,credential_key=self.key,
                                            phrase=shadow.APPROVAL_PHRASE)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),before)
        self.assertEqual(prior,{p.name for p in Path("/dev/shm").glob(
            "edgepilot-shadow-rehearsal-*")})
        with sqlite3.connect(self.path) as con:
            self.assertIsNone(con.execute(
                "SELECT 1 FROM sqlite_master WHERE name='tenant_history_references'").fetchone())

    def test_staged_reference_tamper_and_unscoped_owner_fail_closed(self):
        work=Path(self.temp.name)/"shadow-work.db"
        with sqlite3.connect(self.path) as src, sqlite3.connect(work) as dest:
            src.backup(dest)
        report=migration_preflight.inspect_database(work)
        with shadow._conn(work) as con:
            staged=shadow._stage(con,self.key,report)
            self.assertEqual(staged["tenantHistoricalReferences"]["referencesStaged"],2)
            owner=con.execute("SELECT user_id,account_id FROM tenant_accounts").fetchone()
            with self.assertRaises(tenant_history.TenantHistoryError):
                tenant_history.stage_from_reconciled_history(
                    con,user_id=owner["user_id"],account_id=owner["account_id"],
                    source_schema_sha256=report["schemaSha256"],
                    expected_count=3)
        with shadow._conn(work) as con:
            row=con.execute("SELECT reference_id FROM tenant_history_references LIMIT 1").fetchone()
            con.execute("UPDATE tenant_history_references SET source_sha256=? WHERE reference_id=?",
                        ("0"*64,row["reference_id"]))
            row=con.execute("""SELECT COUNT(*) FROM tenant_history_references r
                LEFT JOIN tenant_shadow_history_index i
                ON i.source_table=r.source_table AND i.source_rowid=r.source_rowid
                   AND i.source_sha256=r.source_sha256
                WHERE i.source_table IS NULL""").fetchone()
            self.assertEqual(row[0],1)


if __name__=="__main__":
    unittest.main()
