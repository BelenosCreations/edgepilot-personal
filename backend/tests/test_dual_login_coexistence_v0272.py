"""v0.2.72: exact live-flags dual-login isolation on disposable twin SQLite files.

No real service, API key, provider request or trading permission is used.
The explicit production-like profile keeps tenant-only and all broker
feature flags off; only new identity authentication is on.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROBE = r"""
import json
import os
from pathlib import Path
import sqlite3
import sys

from engine import shared_storage_cutover, tenant_foundation, identity_auth

root=Path(sys.argv[1])
shared_storage_cutover.PERSISTENT_ROOT=root
owner_db=root/'edgepilot.db'
tenant_db=root/'edgepilot-tenants.db'

with sqlite3.connect(owner_db) as db:
    db.execute('CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT NOT NULL)')
    db.execute("INSERT INTO settings VALUES('account_id','FAKE-LEGACY-ACCOUNT')")
    db.execute('CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY, ciphertext BLOB)')
    db.execute("INSERT INTO broker_credentials VALUES('public',?)",
               (b'SYNTHETIC-CIPHERTEXT-NEVER-PUBLIC',))
os.chmod(owner_db,0o600)

tenant_foundation.setup(str(tenant_db))
identity_auth.setup(str(tenant_db))
users=tenant_foundation.TenantStore(str(tenant_db))
owner_id=users.provision_user('Synthetic Owner A','owner')
other_id=users.provision_user('Synthetic Member B','member')
ids=identity_auth.IdentityStore(str(tenant_db))
ids.provision(owner_id,'owner_a','temporary-owner-pass-2026')
ids.provision(other_id,'member_b','temporary-member-pass-2026')
os.chmod(tenant_db,0o600)

import app

assert app.DB==owner_db and app.TENANT_DB==tenant_db
assert app.identity_auth_enabled
assert app.TENANT_POLICY == {'tenant_only':False,'android_signer_sha256':None}
assert not app.tenant_public_vault_enabled
assert not app.tenant_public_read_enabled
assert not app.tenant_read_enabled
assert not app.tenant_signup_enabled
assert not app.tenant_passkeys_enabled
assert app.tenant_connection_vault is None
assert app.tenant_public_reader is None
assert app.tenant_account_store is None

BASE='https://edgepilot.example.test'
ORIGIN={'Origin':BASE}
a=app.app.test_client()
b=app.app.test_client()
old=app.app.test_client()

def post(client,path,payload=None,headers=None):
    return client.post(path,base_url=BASE,
                       headers=ORIGIN if headers is None else headers,
                       json={} if payload is None else payload)
def get(client,path):
    return client.get(path,base_url=BASE)

assert get(a,'/account').status_code==200
assert get(old,'/').status_code==200
pa=post(a,'/api/identity/login',{'username':'owner_a','password':'temporary-owner-pass-2026'})
pb=post(b,'/api/identity/login',{'username':'member_b','password':'temporary-member-pass-2026'})
pl=post(old,'/api/login',{'accessToken':os.environ['EDGE_APP_TOKEN']})
assert pa.status_code==200 and pb.status_code==200 and pl.status_code==200, (
    pa.status_code,pb.status_code,pl.status_code)
assert '__Host-edgepilot_identity' in pa.headers['Set-Cookie']
assert '__Host-edgepilot_identity' in pb.headers['Set-Cookie']
assert '__Host-edgepilot_session' in pl.headers['Set-Cookie']

sa=get(a,'/api/identity/session')
sb=get(b,'/api/identity/session')
assert sa.status_code==200 and sb.status_code==200
assert sa.json['user']['userId']==owner_id
assert sb.json['user']['userId']==other_id
assert sa.json['scope']=='identity_only_no_broker_access'
assert sb.json['scope']=='identity_only_no_broker_access'

# Tenant cookie must not authenticate the existing legacy dashboard/API.
for user_client in (a,b):
    assert get(user_client,'/api/session').status_code==401
    assert get(user_client,'/api/dashboard').status_code==401
    assert get(user_client,'/api/automation/status').status_code==401
    assert get(user_client,'/api/broker/credentials/status').status_code==401
    for scoped in ('/api/identity/public/connections',
                   '/api/identity/public/read/accounts',
                   '/api/identity/accounts'):
        assert get(user_client,scoped).status_code==404,scoped

# Legacy token session is NOT an identity user and cannot access owner tenant.
assert get(old,'/api/session').status_code==200
assert get(old,'/api/identity/session').status_code==401

# Disallow self-registration, passkeys, cross-origin login while pilot dormant.
assert post(a,'/api/identity/register',{'username':'any','password':'nothing'}).status_code==404
assert get(a,'/api/identity/passkeys').status_code==404
attacker=app.app.test_client()
assert post(attacker,'/api/identity/login',{'username':'owner_a',
       'password':'temporary-owner-pass-2026'},
       headers={'Origin':'https://attacker.example.test'}).status_code==403

# Sign out member B; owner A and legacy session remain valid.
out_b=post(b,'/api/identity/logout',
           headers={**ORIGIN,'X-Edge-Identity-CSRF':sb.json['csrf']})
assert out_b.status_code==200,out_b.status_code
assert get(b,'/api/identity/session').status_code==401
assert get(a,'/api/identity/session').status_code==200
assert get(old,'/api/session').status_code==200

# Log out the legacy token user; owner's independent session remains valid.
assert post(old,'/api/logout',headers={**ORIGIN,
   'X-Edge-CSRF':get(old,'/api/session').json['csrf']}).status_code==200
assert get(old,'/api/session').status_code==401
assert get(a,'/api/identity/session').status_code==200

# Confirm original broker ciphertext is NOT present in tenant DB and no
# identity table was silently created in the legacy DB.
with sqlite3.connect(owner_db) as db:
    assert db.execute("SELECT ciphertext FROM broker_credentials WHERE provider='public'").fetchone()[0] == b'SYNTHETIC-CIPHERTEXT-NEVER-PUBLIC'
    assert db.execute("SELECT name FROM sqlite_master WHERE name='tenant_users'").fetchone() is None
with sqlite3.connect(tenant_db) as db:
    assert db.execute("SELECT name FROM sqlite_master WHERE name='broker_credentials'").fetchone() is None
    assert db.execute("SELECT COUNT(*) FROM tenant_identity_sessions").fetchone()[0] == 1
print(json.dumps({'separate_databases':True,
                  'identity_owner_and_member_isolated':True,
                  'old_login_preserved':True,
                  'independent_logout_confirmed':True,
                  'tenant_broker_features_dormant':True,
                  'live_orders_disabled':True}))
"""


class DualLoginProductionFlagRegression(unittest.TestCase):
    def test_separate_database_https_login_legacy_coexistence(self):
        with tempfile.TemporaryDirectory(prefix='edgepilot-dual-login-') as temp:
            env=os.environ.copy()
            env.update({
                'EDGE_DB_PATH':str(Path(temp)/'edgepilot.db'),
                'EDGE_TENANT_DB_PATH':str(Path(temp)/'edgepilot-tenants.db'),
                'EDGE_SHARED_TENANT_DB_PREPARE':'true',
                'EDGE_TENANT_SCHEMA_PREPARE':'true',
                'EDGE_IDENTITY_AUTH_ENABLED':'true',
                'EDGE_PERMANENT_TENANTS_ONLY':'false',
                'EDGE_PERMANENT_READONLY_PILOT_ENABLED':'false',
                'EDGE_AUTOMATION_WORKER_ENABLED':'false',
                'ENABLE_LIVE_ORDERS':'false',
                'EDGE_ISOLATED_STAGING':'false',
                'EDGE_TENANT_SIGNUP_ENABLED':'false',
                'EDGE_PERMANENT_OWNER_INVITES_ENABLED':'false',
                'EDGE_TENANT_PASSKEYS_ENABLED':'false',
                'EDGE_PERMANENT_ANDROID_PASSKEY_ORIGIN_ENABLED':'false',
                'EDGE_TENANT_PUBLIC_VAULT_ENABLED':'false',
                'EDGE_TENANT_PUBLIC_READONLY_ENABLED':'false',
                'EDGE_TENANT_ACCOUNT_READS_ENABLED':'false',
                'EDGE_TENANT_MONITOR_PREVIEW_ENABLED':'false',
                'EDGE_TENANT_WATCHLIST_EDIT_ENABLED':'false',
                'EDGE_TENANT_PASSWORD_CHANGE_ENABLED':'false',
                'EDGE_TENANT_SESSION_CONTROLS_ENABLED':'false',
                'EDGE_APP_TOKEN':'synthetic-owner-token-only-0123456789ABCDEFGHIJKLMNOP',
                'PUBLIC_API_SECRET':'',
                'EDGE_CREDENTIAL_KEY':'',
            })
            run=subprocess.run(
                [sys.executable,'-c',PROBE,temp],
                env=env,
                cwd=str(Path(__file__).resolve().parents[1]),
                capture_output=True,text=True,timeout=45)
            self.assertEqual(run.returncode,0,run.stderr[-1400:]+run.stdout[-500:])
            result=json.loads(run.stdout.strip().splitlines()[-1])
            self.assertEqual(set(result),{
                'separate_databases','identity_owner_and_member_isolated',
                'old_login_preserved','independent_logout_confirmed',
                'tenant_broker_features_dormant','live_orders_disabled'})
            self.assertTrue(all(result.values()))
            self.assertNotIn('synthetic-owner-token-only',run.stdout)
            self.assertNotIn('temporary-owner-pass-2026',run.stdout)
            self.assertNotIn('SYNTHETIC-CIPHERTEXT-NEVER-PUBLIC',run.stdout)


if __name__=='__main__':
    unittest.main()
