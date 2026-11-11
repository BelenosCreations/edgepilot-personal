"""v0.2.67: gated owner-scoped Public pilot on existing paid separate DB.

Real Public HTTPS is NEVER used. All keys and account references in
this test are synthetic; HTTP isolation uses two distinct sessions.
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet
from engine import identity_auth, tenant_foundation
from engine import shared_storage_cutover as storage


OWNER_KEY = "SYNTHETIC-PUBLIC-KEY-OWNER-123456789012345"
MEMBER_KEY = "SYNTHETIC-PUBLIC-KEY-MEMBER-12345678901234"


class PermanentReadOnlyPilotTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.legacy=self.root/"edgepilot.db"
        self.tenant=self.root/"edgepilot-tenants.db"
        self.fernet=Fernet.generate_key().decode()
        with sqlite3.connect(self.legacy) as db:
            db.execute("CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT NOT NULL)")
            db.execute("CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY,ciphertext BLOB)")
            db.execute("INSERT INTO broker_credentials VALUES ('public',?)", (b'SYNTHETIC-ENCRYPTED-OWNER',))
        tenant_foundation.setup(str(self.tenant))
        identity_auth.setup(str(self.tenant))
        os.chmod(self.tenant,0o600)
        store=tenant_foundation.TenantStore(str(self.tenant))
        self.owner=store.provision_user("Private Owner",role="owner")
        self.member=store.provision_user("Private Member",role="member")
        auth=identity_auth.IdentityStore(str(self.tenant))
        auth.provision(self.owner,"private-owner","long-synthetic-password-2026")
        auth.provision(self.member,"private-member","long-synthetic-password-2026")
        self.env={
            "EDGE_DB_PATH":str(self.legacy),
            "EDGE_TENANT_DB_PATH":str(self.tenant),
            "EDGE_SHARED_TENANT_DB_PREPARE":"true",
            "EDGE_TENANT_SCHEMA_PREPARE":"true",
            "EDGE_IDENTITY_AUTH_ENABLED":"true",
            "EDGE_PERMANENT_READONLY_PILOT_ENABLED":"true",
            "EDGE_PERMANENT_TENANTS_ONLY":"false",
            "EDGE_TENANT_ACCOUNT_READS_ENABLED":"true",
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED":"true",
            "EDGE_TENANT_PUBLIC_READONLY_ENABLED":"true",
            "EDGE_CREDENTIAL_KEY":self.fernet,
            "EDGE_AUTOMATION_WORKER_ENABLED":"false",
            "ENABLE_LIVE_ORDERS":"false",
            "EDGE_ISOLATED_STAGING":"false",
            "EDGE_TENANT_SIGNUP_ENABLED":"false",
        }

    def select(self,env=None):
        return storage.select_tenant_database(
            self.env if env is None else env,self.legacy,persistent_root=self.root)

    def test_scoped_pilot_requires_opt_in_and_first_owner(self):
        before=self.legacy.read_bytes()
        self.assertEqual(self.select(),self.tenant)
        with self.assertRaises(storage.SharedStorageDenied):
            self.select({**self.env,"EDGE_PERMANENT_READONLY_PILOT_ENABLED":"false"})
        self.assertEqual(self.legacy.read_bytes(),before)

    def test_unconfigured_pilot_cannot_fall_back_into_legacy_owner_database(self):
        with self.assertRaises(storage.SharedStorageDenied):
            self.select({**self.env, "EDGE_TENANT_DB_PATH": "",
                         "EDGE_SHARED_TENANT_DB_PREPARE": "false"})
        self.assertFalse((self.root/"unexpected-tenant.db").exists())

    def test_pilot_flag_alone_without_user_features_never_creates_account(self):
        env={**self.env,
             "EDGE_TENANT_ACCOUNT_READS_ENABLED":"false",
             "EDGE_TENANT_PUBLIC_VAULT_ENABLED":"false",
             "EDGE_TENANT_PUBLIC_READONLY_ENABLED":"false"}
        before=self.tenant.read_bytes()
        self.assertEqual(self.select(env),self.tenant)
        self.assertEqual(self.tenant.read_bytes(),before)

    def test_missing_owner_or_bad_vault_key_or_bad_dependent_flag_denied(self):
        self.tenant.unlink()
        with self.assertRaises(storage.SharedStorageDenied):
            self.select()
        # A fresh empty DB cannot silently enroll or masquerade as the owner.
        tenant_foundation.setup(str(self.tenant))
        identity_auth.setup(str(self.tenant))
        os.chmod(self.tenant,0o600)
        with self.assertRaises(storage.SharedStorageDenied):
            self.select()
        with self.assertRaises(storage.SharedStorageDenied):
            self.select({**self.env,"EDGE_CREDENTIAL_KEY":""})
        with self.assertRaises(storage.SharedStorageDenied):
            self.select({**self.env,"EDGE_TENANT_PUBLIC_VAULT_ENABLED":"false"})
        with self.assertRaises(storage.SharedStorageDenied):
            self.select({**self.env,"EDGE_TENANT_ACCOUNT_READS_ENABLED":"false"})

    def test_development_and_unsafe_runtime_controls_refused(self):
        for key in ("EDGE_AUTOMATION_WORKER_ENABLED","ENABLE_LIVE_ORDERS",
                    "EDGE_ISOLATED_STAGING","EDGE_TENANT_SIGNUP_ENABLED",
                    "EDGE_PERMANENT_OWNER_INVITES_ENABLED"):
            with self.subTest(key=key):
                with self.assertRaises(storage.SharedStorageDenied):
                    self.select({**self.env,key:"true"})
        with self.assertRaises(storage.SharedStorageDenied):
            self.select({**self.env,"EDGE_TENANT_DB_PATH":str(self.legacy)})

    def test_two_independent_identity_http_sessions_save_separate_secrets_without_public_network(self):
        # New app import deliberately uses a local two-file fixture and
        # fake secrets; no real Public adapter method is ever invoked.
        script = """
import sqlite3,sys,json
from pathlib import Path
from engine import shared_storage_cutover
shared_storage_cutover.PERSISTENT_ROOT=Path(sys.argv[1])
import app
assert app.DB != app.TENANT_DB
assert app.tenant_connection_vault is not None
assert app.tenant_public_reader is not None
assert not app.TENANT_POLICY['tenant_only']
origin='https://edgepilot.example.test'
clients=[app.app.test_client(),app.app.test_client()]
sessions=[]
for client,username in zip(clients,('private-owner','private-member')):
  r=client.post('/api/identity/login',base_url=origin,
      headers={'Origin':origin},json={'username':username,
      'password':'long-synthetic-password-2026'})
  assert r.status_code==200,r.status_code
  sessions.append(r.json['csrf'])
secrets=('SYNTHETIC-PUBLIC-KEY-OWNER-123456789012345',
         'SYNTHETIC-PUBLIC-KEY-MEMBER-12345678901234')
connections=[]
for i in range(2):
  r=clients[i].post('/api/identity/public/connections',base_url=origin,
        headers={'Origin':origin,'X-Edge-Identity-CSRF':sessions[i]},
        json={'secret':secrets[i]})
  assert r.status_code==201,(i,r.status_code,r.get_data(as_text=True))
  connections.append(r.json['connectionId'])
  assert secrets[i] not in r.get_data(as_text=True)
for i in range(2):
  r=clients[i].get('/api/identity/public/connections',base_url=origin)
  assert r.status_code==200
  body=r.get_data(as_text=True)
  assert connections[i] in body
  assert connections[1-i] not in body
  assert secrets[0] not in body and secrets[1] not in body
assert clients[0].get('/api/settings',base_url=origin).status_code==401
with sqlite3.connect(app.DB) as db:
  assert db.execute('SELECT ciphertext FROM broker_credentials').fetchone()[0] == b'SYNTHETIC-ENCRYPTED-OWNER'
with sqlite3.connect(app.TENANT_DB) as db:
  items=db.execute('SELECT user_id,credential_ciphertext FROM tenant_connections').fetchall()
  assert len(items)==2 and items[0][0]!=items[1][0]
  assert all(secrets[0].encode() not in rec[1] and secrets[1].encode() not in rec[1] for rec in items)
print(json.dumps({'separate':True,'independentSessions':True,'noPublicNetwork':True}))
"""
        env=os.environ.copy()
        env.update(self.env)
        env.update({"EDGE_APP_TOKEN":"","PUBLIC_API_SECRET":"","EDGE_STAGING_OPERATOR_SHA256":""})
        proc=subprocess.run(
            [sys.executable,"-c",script,str(self.root)],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env,capture_output=True,text=True,timeout=45)
        self.assertEqual(proc.returncode,0,proc.stderr[-1700:])
        self.assertTrue(json.loads(proc.stdout.strip().splitlines()[-1])["independentSessions"])


if __name__=="__main__":
    unittest.main()
