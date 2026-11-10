"""v0.2.15 dormant typed history / rollback tests — synthetic broker rows only."""
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from engine import (owner_shadow_migration as shadow, tenant_history_details as details,
                    tenant_history, migration_preflight, tenant_foundation, identity_auth)

NOW="2026-11-09T19:00:00+00:00"


class TypedShadowHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir="/dev/shm")
        self.source=Path(self.temp.name)/"restored-source.db"
        self.key=Fernet.generate_key().decode()
        ciphertext=Fernet(self.key.encode()).encrypt(b"ONLY-SYNTHETIC-FAKE-PUBLIC-SECRET-12345")
        with sqlite3.connect(self.source) as c:
            c.executescript("""
                CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT NOT NULL);
                CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY,ciphertext BLOB);
                CREATE TABLE account_snapshots(id INTEGER PRIMARY KEY,account TEXT,
                   ts TEXT,total_value TEXT,buying_power TEXT);
                CREATE TABLE observation_cycles(id INTEGER PRIMARY KEY,
                   completed_at TEXT,mode TEXT,state TEXT,market_session TEXT,
                   symbols_json TEXT,quotes_accepted INTEGER,quotes_rejected INTEGER,
                   quote_age_seconds INTEGER,issue TEXT);
                CREATE TABLE sync_transactions(account TEXT NOT NULL,tx_id TEXT NOT NULL,
                   timestamp TEXT NOT NULL,symbol TEXT,side TEXT,type TEXT,
                   subtype TEXT,raw_json TEXT,first_seen TEXT,
                   PRIMARY KEY(account,tx_id));
                CREATE TABLE broker_fills(id TEXT PRIMARY KEY,account TEXT NOT NULL,
                   symbol TEXT NOT NULL,side TEXT NOT NULL,quantity TEXT NOT NULL,
                   price TEXT NOT NULL,fee TEXT NOT NULL,source TEXT NOT NULL,
                   timestamp TEXT NOT NULL,recorded_at TEXT NOT NULL);
                CREATE TABLE observed_orders(account TEXT,order_id TEXT,status TEXT,
                   side TEXT,symbol TEXT,created_at TEXT,filled_quantity TEXT,
                   last_seen TEXT,origin TEXT,raw_json TEXT,
                   PRIMARY KEY(account,order_id));
                CREATE TABLE observed_trades(account TEXT,trade_id TEXT,order_id TEXT,
                   symbol TEXT,side TEXT,quantity TEXT,price TEXT,timestamp TEXT,
                   fees_status TEXT,origin TEXT,raw_json TEXT,
                   PRIMARY KEY(account,trade_id));
                CREATE TABLE sync_runs(id INTEGER PRIMARY KEY,account TEXT,ts TEXT,
                   status TEXT,imported_count INTEGER,pages INTEGER,message TEXT);
                CREATE TABLE sync_alerts(id INTEGER PRIMARY KEY,account TEXT,kind TEXT,
                   fingerprint TEXT,message TEXT,detail_json TEXT,state TEXT,
                   created TEXT);
                CREATE TABLE order_audit_runs(id INTEGER PRIMARY KEY,account TEXT,
                   ts TEXT,count_orders INTEGER,count_trades INTEGER,state TEXT,note TEXT);
                CREATE TABLE order_audit_alerts(id INTEGER PRIMARY KEY,account TEXT,
                   fingerprint TEXT,kind TEXT,message TEXT,state TEXT,created TEXT);
                CREATE TABLE activity(id INTEGER PRIMARY KEY,message TEXT);
            """)
            c.executemany("INSERT INTO settings VALUES(?,?)",[
                ("account_id","FAKE-PUBLIC-ACCOUNT"),("profile_label","Test Owner")])
            c.execute("INSERT INTO broker_credentials VALUES('public',?)",(ciphertext,))
            c.execute("INSERT INTO account_snapshots VALUES(1,'FAKE-PUBLIC-ACCOUNT',?,?,?)",
                      (NOW,"123.45","101.01"))
            c.execute("INSERT INTO observation_cycles VALUES(1,?,'observe','OK','CLOSED','[\"SPY\"]',1,0,3,NULL)",(NOW,))
            c.execute("""INSERT INTO sync_transactions VALUES
                ('FAKE-PUBLIC-ACCOUNT','tx-1',?,'SPY','BUY','TRADE','EQUITY',
                 '{"hidden":"VERY_SECRET_RAW_PROVIDER_DATA"}',?)""",(NOW,NOW))
            c.execute("""INSERT INTO sync_transactions VALUES
                ('FAKE-PUBLIC-ACCOUNT','tx-2','unparseable date','QQQ',
                 'SELL','TRADE',NULL,'{}',?)""",(NOW,))
            c.execute("""INSERT INTO broker_fills VALUES('fill-1','FAKE-PUBLIC-ACCOUNT',
                'SPY','BUY','2.1','123.25','0.01','EXTERNAL',?,?)""",(NOW,NOW))
            c.execute("""INSERT INTO observed_orders VALUES('FAKE-PUBLIC-ACCOUNT',
                'order1','NEW','BUY','SPY',?,'0',?,'UNVERIFIED',
                '{"secret":"VERY_SECRET_RAW_PROVIDER_DATA"}')""",(NOW,NOW))
            c.execute("""INSERT INTO observed_trades VALUES('FAKE-PUBLIC-ACCOUNT',
                'trade1','order1','SPY','BUY','1','122.95',?,
                'UNKNOWN','UNVERIFIED','{}')""",(NOW,))
            c.execute("""INSERT INTO sync_runs VALUES
                (1,'FAKE-PUBLIC-ACCOUNT',?,'READ_ONLY_COMPLETE',0,1,'private run')""",(NOW,))
            c.execute("""INSERT INTO sync_alerts VALUES
                (1,'FAKE-PUBLIC-ACCOUNT','MISMATCH','fp','private alert',
                '{}','OPEN',?)""",(NOW,))
            c.execute("""INSERT INTO order_audit_runs VALUES
                (1,'FAKE-PUBLIC-ACCOUNT',?,1,1,'OK','private audit')""",(NOW,))
            c.execute("""INSERT INTO order_audit_alerts VALUES
                (1,'FAKE-PUBLIC-ACCOUNT','a1','REVIEW',
                'private broker notes','OPEN',?)""",(NOW,))
            c.execute("INSERT INTO activity VALUES(1,'NO_ACCOUNT_PROOF')")
        self.flag=patch.dict(os.environ,{shadow.ENABLE_FLAG:"true"})
        self.flag.start()

    def tearDown(self):
        self.flag.stop()
        self.temp.cleanup()

    def stage_copy(self):
        work=Path(self.temp.name)/"inspection.db"
        with sqlite3.connect(self.source) as a,sqlite3.connect(work) as b:
            a.backup(b)
        inventory=migration_preflight.inspect_database(work)
        with shadow._conn(work) as con:
            summary=shadow._stage(con,self.key,inventory)
        return work,summary

    def test_typed_summaries_from_verified_source_references_only(self):
        before=hashlib.sha256(self.source.read_bytes()).hexdigest()
        work,result=self.stage_copy()
        ref=result["tenantHistoricalReferences"]
        typed=result["tenantHistoricalSummaries"]
        self.assertEqual(ref["referencesStaged"],10)
        self.assertEqual(result["historicalReconciliation"]["quarantinedRows"],5)
        self.assertEqual(typed["transactionSummaries"],1)
        self.assertEqual(typed["brokerActivitySummaries"],3)
        self.assertEqual(typed["auditSummaries"],4)
        self.assertEqual(typed["supportedSummariesStaged"],8)
        self.assertEqual(typed["referenceOnlyOrUnsupportedRows"],2)
        self.assertEqual(typed["totalReferencesPreserved"],10)
        self.assertTrue(typed["allReferencedRowsAccountMatched"])
        self.assertFalse(typed["fullHistoryPayloadMigrated"])
        self.assertFalse(typed["rawBrokerJsonCopied"])
        self.assertTrue(typed["sourceOnlyNotBrokerVerified"])
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(),before)
        with sqlite3.connect(work) as c:
            self.assertFalse(c.execute("PRAGMA foreign_key_check").fetchall())
            tx=c.execute("""SELECT occurred_at,symbol,side_label,type_label,
                identifier_sha256,validation_state FROM tenant_history_transaction_details""").fetchone()
            self.assertEqual(tx[0],NOW)
            self.assertEqual(tx[1:4],("SPY","BUY","TRADE"))
            self.assertEqual(len(tx[4]),64)
            self.assertEqual(tx[5],"SOURCE_ONLY_UNVERIFIED")
            fill=c.execute("""SELECT quantity_label,price_label,fee_label,
                status_label,validation_state FROM tenant_history_broker_details
                WHERE activity_kind='broker_fills'""").fetchone()
            self.assertEqual(fill,("2.1","123.25","0.01","SOURCE_LABEL_EXTERNAL",
                                   "SOURCE_ONLY_UNVERIFIED"))
            self.assertEqual(c.execute("SELECT COUNT(*) FROM tenant_history_references").fetchone()[0],10)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM tenant_history_audit_details").fetchone()[0],4)
            text=" ".join(str(v) for table in (
                "tenant_history_transaction_details","tenant_history_broker_details",
                "tenant_history_audit_details") for row in c.execute(
                "SELECT * FROM "+table) for v in row)
            for private in ("VERY_SECRET_RAW_PROVIDER_DATA","FAKE-PUBLIC-ACCOUNT",
                            "private run","private broker notes","tx-1","fill-1"):
                self.assertNotIn(private,text)

    def test_full_tmpfs_rehearsal_keeps_original_and_reports_blockers(self):
        before=hashlib.sha256(self.source.read_bytes()).hexdigest()
        result=shadow.rehearse_owner_shadow(
            self.source,credential_key=self.key,phrase=shadow.APPROVAL_PHRASE)
        self.assertEqual(result["tenantHistoricalSummaries"]["supportedSummariesStaged"],8)
        self.assertFalse(result["tenantHistoricalSummaries"]["cutoverReady"])
        self.assertFalse(result["routeAndWorkerBoundaryAudit"]["crossAccountProductionCutoverAllowed"])
        self.assertTrue(result["routeAndWorkerBoundaryAudit"]["fullRouteAndWorkerRefactorRequired"])
        self.assertTrue(result["temporaryStorageVerifiedMemoryBacked"])
        self.assertTrue(result["disposableWorkingCopyRemoved"])
        self.assertTrue(result["sourceContentsUnchanged"])
        self.assertFalse(result["productionDatabaseChanged"])
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(),before)

    def test_fail_closed_if_source_row_data_mutates_without_count_change(self):
        work,result=self.stage_copy()
        with shadow._conn(work) as con:
            ref=con.execute("""SELECT reference_id,user_id,account_id FROM
                tenant_history_references WHERE source_table='sync_transactions'
                ORDER BY reference_id LIMIT 1""").fetchone()
            con.execute("""UPDATE sync_transactions SET raw_json='{"after":"tampered"}'
                 WHERE tx_id='tx-1'""")
            with self.assertRaisesRegex(details.DetailSafetyError,"provenance mismatch"):
                details.stage(con,user_id=ref["user_id"],account_id=ref["account_id"],
                              expected_references=10)

    def test_injected_failed_stage_keeps_source_and_removes_copy(self):
        before=hashlib.sha256(self.source.read_bytes()).hexdigest()
        existing={p.name for p in Path("/dev/shm").glob("edgepilot-shadow-rehearsal-*")}
        with patch.object(details,"stage",side_effect=details.DetailSafetyError(
                "Typed history reconciliation mismatch")):
            with self.assertRaisesRegex(shadow.ShadowMigrationError,
                                        "Typed history reconciliation mismatch"):
                shadow.rehearse_owner_shadow(
                    self.source,credential_key=self.key,phrase=shadow.APPROVAL_PHRASE)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(),before)
        self.assertEqual(existing,{p.name for p in Path("/dev/shm").glob(
            "edgepilot-shadow-rehearsal-*")})

    def test_cross_tenant_foreign_key_and_locked_status(self):
        work,_=self.stage_copy()
        with shadow._conn(work) as c:
            ref=c.execute("SELECT reference_id,user_id,account_id FROM tenant_history_references LIMIT 1").fetchone()
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute("""INSERT INTO tenant_history_transaction_details(
                    reference_id,user_id,account_id,occurred_at,identifier_sha256)
                    VALUES(?,?,?,?,?)""",
                    (ref["reference_id"],"OTHER",ref["account_id"],NOW,"a"*64))
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute("""UPDATE tenant_history_transaction_details SET
                    validation_state='BROKER_CONFIRMED'""")
        with shadow._conn(work,readonly=True) as c:
            self.assertFalse(c.execute("PRAGMA foreign_key_check").fetchall())

    def test_two_users_multiple_accounts_and_revocation_at_read(self):
        work,_=self.stage_copy()
        tenant_foundation.setup(str(work))
        identity_auth.setup(str(work))
        with shadow._conn(work) as con:
            owner=con.execute("SELECT user_id,account_id,connection_id FROM tenant_accounts").fetchone()
        identity=identity_auth.IdentityStore(str(work))
        identity.provision(owner["user_id"],"staging_owner","really-long-fake-staging-owner-password")
        token=identity.authenticate("staging_owner","really-long-fake-staging-owner-password",
                                    "synthetic-phone")["token"]
        reader=details.DormantDetailsReader(work,identity)
        a=reader.summary(token,owner["account_id"])
        self.assertEqual(a["counts"],{"transactions":1,"brokerActivity":3,"audits":4})
        self.assertFalse(a["canTrade"])
        self.assertFalse(a["transfersEnabled"])
        tenants=tenant_foundation.TenantStore(work,credential_key=self.key)
        another=tenants.provision_user("Other owner","owner")
        identity.provision(another,"other_account_owner","really-long-fake-other-owner-password")
        second=identity.authenticate("other_account_owner","really-long-fake-other-owner-password",
                                    "other-fake-phone")["token"]
        with self.assertRaises(tenant_foundation.TenantAccessError):
            reader.summary(second,owner["account_id"])
        with self.assertRaises(tenant_foundation.TenantAccessError):
            reader.summary(token,"guess-a-foreign-account")
        another_connection=tenants.add_connection(owner["user_id"],
            "FAKE-OTHER-PUBLIC-CREDENTIAL-ONLY-00000001")
        another_account=tenants.link_account(owner["user_id"],another_connection,
                                             "SECOND-SYNTHETIC-ACCOUNT","Second")
        self.assertEqual(reader.summary(token,another_account)["counts"],
                         {"transactions":0,"brokerActivity":0,"audits":0})
        with shadow._conn(work) as con:
            con.execute("UPDATE tenant_connections SET revoked_at=? WHERE connection_id=?",
                        (NOW,owner["connection_id"]))
        with self.assertRaises(tenant_foundation.TenantAccessError):
            reader.summary(token,owner["account_id"])
        self.assertEqual(reader.summary(token,another_account)["counts"],
                         {"transactions":0,"brokerActivity":0,"audits":0})
        identity.revoke(token)
        with self.assertRaises(tenant_foundation.TenantAccessError):
            reader.summary(token,another_account)


if __name__=="__main__":
    unittest.main()
