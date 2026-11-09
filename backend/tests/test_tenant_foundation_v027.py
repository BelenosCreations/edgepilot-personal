"""Phase 1: tenant schema is additive, opt-in, encrypted, and fail-closed.

No Public credentials or second person's identity are activated by these tests.
All account access must eventually derive principal from a trusted session.
"""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from engine import tenant_foundation

BASE=Path(__file__).resolve().parents[2]


class TenantFoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=str(Path(self.temp.name)/'tenancy.db')
        self.key=Fernet.generate_key().decode('ascii')
        self.store=tenant_foundation.TenantStore(self.path,credential_key=self.key)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT NOT NULL)")
            db.execute("INSERT INTO settings VALUES('account_id','LEGACY-ACCOUNT')")
            db.execute("""CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY,
                       ciphertext BLOB, updated_at TEXT)""")
            db.execute("INSERT INTO broker_credentials VALUES('public',?,?)",
                       (b'legacy-encrypted-blob','existing-timestamp'))
            db.execute("CREATE TABLE activity(id INTEGER PRIMARY KEY,message TEXT)")
            db.execute("INSERT INTO activity VALUES(42,'Keep old activity')")
        tenant_foundation.setup(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_additive_schema_keeps_existing_owner_records_intact(self):
        tenant_foundation.setup(self.path)  # safe repeated startup
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT v FROM settings WHERE k='account_id'").fetchone()[0],
                             'LEGACY-ACCOUNT')
            self.assertEqual(db.execute("SELECT ciphertext FROM broker_credentials WHERE provider='public'").fetchone()[0],
                             b'legacy-encrypted-blob')
            self.assertEqual(db.execute("SELECT message FROM activity WHERE id=42").fetchone()[0],
                             'Keep old activity')
            self.assertEqual(db.execute("SELECT count(*) FROM tenant_users").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM tenant_accounts").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT schema_version FROM tenant_schema_meta").fetchone()[0],1)

    def test_credentials_are_encrypted_and_user_scoped(self):
        alice=self.store.provision_user('Owner',role='owner')
        bob=self.store.provision_user('Another user',role='member')
        secret="Public-Test-Secret-For-Tenant-Only-01234567"
        connection=self.store.add_connection(alice,secret)
        with sqlite3.connect(self.path) as db:
            row=db.execute("""SELECT user_id,credential_ciphertext
                FROM tenant_connections WHERE connection_id=?""",(connection,)).fetchone()
        self.assertEqual(row[0],alice)
        self.assertNotIn(secret.encode(),row[1])
        self.assertEqual(Fernet(self.key).decrypt(row[1]),secret.encode())
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.store.link_account(bob,connection,'SECOND-PUBLIC-ACCOUNT','Unauthorized')
        self.assertEqual(self.store.list_accounts(bob),[])

    def test_multiple_accounts_for_one_user_and_isolation_across_users(self):
        alice=self.store.provision_user('First user')
        bob=self.store.provision_user('Second user')
        conn_a=self.store.add_connection(alice,'Credential-A-12345678901234567890')
        conn_b=self.store.add_connection(bob,'Credential-B-12345678901234567890')
        a1=self.store.link_account(alice,conn_a,'BROKER-A1','Long-term')
        a2=self.store.link_account(alice,conn_a,'BROKER-A2','Trading')
        b1=self.store.link_account(bob,conn_b,'BROKER-B1','Private')
        self.assertEqual({x['account_id'] for x in self.store.list_accounts(alice)},{a1,a2})
        self.assertEqual({x['account_id'] for x in self.store.list_accounts(bob)},{b1})
        self.store.account_setting(alice,a1,'research_mode','watchlist')
        self.store.account_setting(alice,a2,'research_mode','automatic')
        self.store.account_setting(bob,b1,'research_mode','hybrid')
        self.assertEqual(self.store.account_setting(alice,a1,'research_mode'),'watchlist')
        self.assertEqual(self.store.account_setting(alice,a2,'research_mode'),'automatic')
        self.assertEqual(self.store.account_setting(bob,b1,'research_mode'),'hybrid')
        for action in (
            lambda:self.store.account_setting(bob,a1,'research_mode'),
            lambda:self.store.account_setting(bob,a1,'research_mode','forbidden'),
            lambda:self.store.account_setting(alice,b1,'paper_risk_profile','aggressive')
        ):
            with self.assertRaises(tenant_foundation.TenantAccessError):
                action()
        self.assertEqual(self.store.account_setting(alice,a1,'research_mode'),'watchlist')
        self.assertEqual(self.store.account_setting(bob,b1,'research_mode'),'hybrid')

    def test_duplicate_cross_tenant_broker_account_rejected(self):
        alice=self.store.provision_user('First')
        bob=self.store.provision_user('Second')
        c1=self.store.add_connection(alice,'Credential-A-12345678901234567890')
        c2=self.store.add_connection(bob,'Credential-B-12345678901234567890')
        self.store.link_account(alice,c1,'SAME-BROKER-ID','A')
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.link_account(bob,c2,'SAME-BROKER-ID','B')

    def test_fail_closed_on_invalid_settings_and_unavailable_encryption(self):
        user=self.store.provision_user('User')
        with self.assertRaises(ValueError):
            self.store.account_setting(user,'missing','any_secret','bad')
        with self.assertRaises(ValueError):
            self.store.provision_user('invalid',role='superadmin')
        without_key=tenant_foundation.TenantStore(self.path,credential_key='')
        with patch.dict(os.environ,{'EDGE_CREDENTIAL_KEY':''}):
            with self.assertRaisesRegex(RuntimeError,'encryption is unavailable'):
                without_key.add_connection(user,'Credential-A-12345678901234567890')
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.store.add_connection('not-a-user','Credential-A-12345678901234567890')

    def test_schema_version_mismatch_prevents_unsafe_migration(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE tenant_schema_meta SET schema_version=2")
        with self.assertRaisesRegex(RuntimeError,'stop and migrate offline'):
            tenant_foundation.setup(self.path)

    def test_inactive_until_independent_explicit_activation(self):
        source=(BASE/'backend/app.py').read_text()
        self.assertIn("EDGE_TENANT_SCHEMA_PREPARE",source)
        self.assertIn("os.getenv('EDGE_TENANT_SCHEMA_PREPARE','false').lower()=='true'",source)
        self.assertNotIn("@app.post('/api/tenant",source)
        self.assertNotIn("@app.get('/api/tenant",source)
        self.assertIn("'liveTradingAvailable':False",source)


if __name__=='__main__':
    unittest.main()
