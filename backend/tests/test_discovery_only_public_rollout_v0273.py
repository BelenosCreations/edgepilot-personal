"""v0.2.73: exactly scoped real-rollout flags with *synthetic* Public transport.

No production keys, network calls, live orders or database migrations.
Two separate identities + original legacy token on independent SQLite files.
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

from cryptography.fernet import Fernet
from engine import shared_storage_cutover, tenant_foundation, identity_auth
from engine import tenant_public_live_readonly as provider

root=Path(sys.argv[1])
shared_storage_cutover.PERSISTENT_ROOT=root
old=root/'edgepilot.db'
new=root/'edgepilot-tenants.db'
with sqlite3.connect(old) as db:
    db.execute('CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT NOT NULL)')
    db.execute("INSERT INTO settings VALUES('account_id','LEGACY-ONLY')")
    db.execute('CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY, ciphertext BLOB)')
    db.execute("INSERT INTO broker_credentials VALUES('public',?)",
               (b'SYNTHETIC-OLD-CREDENTIAL-NEVER-PUBLIC',))
os.chmod(old,0o600)
tenant_foundation.setup(str(new))
identity_auth.setup(str(new))
users=tenant_foundation.TenantStore(str(new))
owner=users.provision_user('Owner A','owner')
member=users.provision_user('Member B','member')
ids=identity_auth.IdentityStore(str(new))
ids.provision(owner,'owner_a','synthetic-owner-private-pass-2026')
ids.provision(member,'member_b','synthetic-member-private-pass-2026')
os.chmod(new,0o600)

import app
assert app.DB==old and app.TENANT_DB==new
assert app.tenant_public_discovery_only
assert app.identity_auth_enabled
assert app.tenant_public_vault_enabled
assert app.tenant_public_read_enabled
assert app.tenant_read_enabled
assert not app.tenant_monitor_preview_enabled
assert not app.tenant_signup_enabled
assert not app.tenant_passkeys_enabled
assert not app.TENANT_POLICY['tenant_only']
assert app.tenant_connection_vault is not None
assert app.tenant_public_reader is not None

KEY_A='SYNTHETIC-OWNER-PUBLIC-SECRET-A-000000001'
KEY_B='SYNTHETIC-MEMBER-PUBLIC-SECRET-B-000000002'
TOKEN_A='SYNTHETIC-BEARER-OWNER-AAAAAAAAAAAAA'
TOKEN_B='SYNTHETIC-BEARER-MEMBER-BBBBBBBBBBB'
ACCOUNT_A='SYNTHETIC-ACCOUNT-A'
ACCOUNT_B='SYNTHETIC-ACCOUNT-B'
token_map={KEY_A:(TOKEN_A,ACCOUNT_A),KEY_B:(TOKEN_B,ACCOUNT_B)}
bearer_map={v[0]:v[1] for v in token_map.values()}

class FakePublic:
    def __init__(self):
        self.calls=[]
    @staticmethod
    def response(data,status=200):
        class Reply:
            status_code=status
            def json(self):
                return data
        return Reply()
    def post(self,url,*,json,timeout):
        self.calls.append(('POST',url))
        assert url==provider.BASE+provider.AUTH_PATH and timeout==provider.TIMEOUT
        assert set(json)=={'secret','validityInMinutes'} and json['validityInMinutes']==5
        return self.response({'accessToken':token_map[json['secret']][0]})
    def get(self,url,*,headers,timeout):
        self.calls.append(('GET',url))
        assert timeout==provider.TIMEOUT and headers.get('Accept')=='application/json'
        assert url==provider.BASE+provider.LIST_PATH,'Only account-discovery GET allowed'
        bearer=headers.get('Authorization','').removeprefix('Bearer ')
        assert bearer in bearer_map
        return self.response({'accounts':[{'accountId':bearer_map[bearer],
                                          'accountType':'BROKERAGE'}]})

fake=FakePublic()
app.tenant_public_reader.http=fake
ORIGIN='https://edgepilot.example.test'
def post(client,path,data=None,csrf=''):
    headers={'Origin':ORIGIN}
    if csrf:
        headers['X-Edge-Identity-CSRF']=csrf
    return client.post(path,base_url=ORIGIN,headers=headers,
                       json={} if data is None else data)
def get(client,path):
    return client.get(path,base_url=ORIGIN)

a=app.app.test_client()
b=app.app.test_client()
oldclient=app.app.test_client()
login_a=post(a,'/api/identity/login',{'username':'owner_a',
              'password':'synthetic-owner-private-pass-2026'})
login_b=post(b,'/api/identity/login',{'username':'member_b',
              'password':'synthetic-member-private-pass-2026'})
oldlogin=post(oldclient,'/api/login',{'accessToken':os.environ['EDGE_APP_TOKEN']})
assert login_a.status_code==login_b.status_code==oldlogin.status_code==200
csrfa=login_a.json['csrf']
csrfb=login_b.json['csrf']

assert get(oldclient,'/api/identity/session').status_code==401
assert get(a,'/api/session').status_code==401
assert get(b,'/api/dashboard').status_code==401
assert get(a,'/api/automation/status').status_code==401

ca=post(a,'/api/identity/public/connections',{'secret':KEY_A},csrfa)
cb=post(b,'/api/identity/public/connections',{'secret':KEY_B},csrfb)
assert ca.status_code==cb.status_code==201,(ca.status_code,cb.status_code)
id_a=ca.json['connectionId']
id_b=cb.json['connectionId']
list_a=get(a,'/api/identity/public/connections')
list_b=get(b,'/api/identity/public/connections')
assert list_a.status_code==list_b.status_code==200
assert list_a.json['discoveryOnlyPilot'] is True
assert list_b.json['discoveryOnlyPilot'] is True
assert [c['connectionId'] for c in list_a.json['connections']]==[id_a]
assert [c['connectionId'] for c in list_b.json['connections']]==[id_b]
assert list_a.json['secretsReturned'] is False
assert KEY_A not in str(list_a.json) and KEY_B not in str(list_b.json)
assert KEY_B not in str(list_a.json) and KEY_A not in str(list_b.json)

da=get(a,'/api/identity/public/read/connections/'+id_a+'/accounts')
db=get(b,'/api/identity/public/read/connections/'+id_b+'/accounts')
assert da.status_code==db.status_code==200,(da.status_code,db.status_code)
assert da.json['accounts']==[{'accountId':ACCOUNT_A,'accountType':'BROKERAGE'}]
assert db.json['accounts']==[{'accountId':ACCOUNT_B,'accountType':'BROKERAGE'}]
assert get(b,'/api/identity/public/read/connections/'+id_a+'/accounts').status_code==404
assert get(a,'/api/identity/public/read/connections/'+id_b+'/accounts').status_code==404
assert get(oldclient,'/api/identity/public/connections').status_code==401

la=post(a,'/api/identity/public/read/connections/'+id_a+'/accounts',
        {'accountId':ACCOUNT_A,'label':'Owner linked account'},csrfa)
lb=post(b,'/api/identity/public/read/connections/'+id_b+'/accounts',
        {'accountId':ACCOUNT_B,'label':'Member linked account'},csrfb)
assert la.status_code==lb.status_code==200,(la.status_code,lb.status_code)
account_a=la.json['accountId']
account_b=lb.json['accountId']
get_a=get(a,'/api/identity/accounts')
get_b=get(b,'/api/identity/accounts')
assert get_a.status_code==get_b.status_code==200
assert get_a.json['discoveryOnlyPilot'] and get_b.json['discoveryOnlyPilot']
assert len(get_a.json['accounts'])==1 and len(get_b.json['accounts'])==1
assert account_b not in str(get_a.json) and account_a not in str(get_b.json)
for user_client in (a,b):
    for account in (account_a,account_b):
        assert get(user_client,'/api/identity/public/read/accounts/'+account+'/portfolio').status_code==404
    assert post(user_client,'/api/identity/register',{'username':'new'}).status_code==404
    assert get(user_client,'/api/identity/passkeys').status_code==404
    assert get(user_client,'/api/identity/accounts/'+account_a+'/monitor/preview').status_code==404

# Only Public account discovery, never portfolio, order, transfer or other HTTP.
assert all(method=='POST' and url==provider.BASE+provider.AUTH_PATH or
           method=='GET' and url==provider.BASE+provider.LIST_PATH
           for method,url in fake.calls)
assert len(fake.calls)>0
with sqlite3.connect(old) as db:
    val=db.execute("SELECT ciphertext FROM broker_credentials WHERE provider='public'").fetchone()[0]
    assert val==b'SYNTHETIC-OLD-CREDENTIAL-NEVER-PUBLIC'
    assert db.execute("SELECT name FROM sqlite_master WHERE name='tenant_users'").fetchone() is None
with sqlite3.connect(new) as db:
    assert db.execute("SELECT name FROM sqlite_master WHERE name='broker_credentials'").fetchone() is None
    rows=db.execute("SELECT credential_ciphertext FROM tenant_connections").fetchall()
    assert len(rows)==2
    assert KEY_A.encode() not in b''.join(x[0] for x in rows)
    assert KEY_B.encode() not in b''.join(x[0] for x in rows)

print(json.dumps({'discovery_only':True,'keys_encrypted':True,
    'two_independent_users':True,'no_legacy_migration':True,
    'no_portfolio_requests':True,'orders_and_transfers_disabled':True}))
"""

class DiscoveryOnlyRolloutTests(unittest.TestCase):
    def test_two_realistic_auth_users_fake_public_transport(self):
        with tempfile.TemporaryDirectory(prefix='edgepilot-discovery-only-') as temp:
            env=os.environ.copy()
            env.update({
                'EDGE_DB_PATH':str(Path(temp)/'edgepilot.db'),
                'EDGE_TENANT_DB_PATH':str(Path(temp)/'edgepilot-tenants.db'),
                'EDGE_SHARED_TENANT_DB_PREPARE':'true',
                'EDGE_TENANT_SCHEMA_PREPARE':'true',
                'EDGE_IDENTITY_AUTH_ENABLED':'true',
                'EDGE_PERMANENT_TENANTS_ONLY':'false',
                'EDGE_PERMANENT_READONLY_PILOT_ENABLED':'true',
                'EDGE_TENANT_ACCOUNT_READS_ENABLED':'true',
                'EDGE_TENANT_PUBLIC_VAULT_ENABLED':'true',
                'EDGE_TENANT_PUBLIC_READONLY_ENABLED':'true',
                'EDGE_TENANT_PUBLIC_DISCOVERY_ONLY':'true',
                'EDGE_TENANT_SIGNUP_ENABLED':'false',
                'EDGE_TENANT_PASSKEYS_ENABLED':'false',
                'EDGE_PERMANENT_OWNER_INVITES_ENABLED':'false',
                'EDGE_TENANT_MONITOR_PREVIEW_ENABLED':'false',
                'EDGE_TENANT_WATCHLIST_EDIT_ENABLED':'false',
                'EDGE_AUTOMATION_WORKER_ENABLED':'false',
                'ENABLE_LIVE_ORDERS':'false',
                'EDGE_ISOLATED_STAGING':'false',
                'EDGE_APP_TOKEN':'synthetic-legacy-token-0123456789-ABCDEFGHIJKLMNOP',
                'EDGE_CREDENTIAL_KEY': 'SYNTHETIC_WILL_BE_REPLACED',
            })
            # One global encrypted Fernet key is shared by both isolated
            # identities, never duplicated as a Public credential.
            from cryptography.fernet import Fernet
            env['EDGE_CREDENTIAL_KEY']=Fernet.generate_key().decode()
            run=subprocess.run([sys.executable,'-c',PROBE,temp],
                env=env,cwd=str(Path(__file__).resolve().parents[1]),
                capture_output=True,text=True,timeout=45)
            self.assertEqual(run.returncode,0,run.stderr[-2500:]+run.stdout[-300:])
            result=json.loads(run.stdout.strip().splitlines()[-1])
            self.assertTrue(all(result.values()))
            self.assertNotIn('synthetic-owner-private-pass',run.stdout)
            self.assertNotIn('SYNTHETIC-OWNER-PUBLIC-SECRET',run.stdout)

    def test_opt_in_flag_has_strict_necessary_gates(self):
        # These source-level checks supplement the real app subprocess
        # controls and ensure new discovery-only does not silently open
        # while worker/trading/tenant-only mode is on.
        from pathlib import Path
        src=(Path(__file__).resolve().parents[1]/'app.py').read_text()
        self.assertIn('if tenant_public_discovery_only and (not tenant_public_read_enabled',src)
        self.assertIn("return fail('Not found',404)",src)
        self.assertIn("'discoveryOnlyPilot':tenant_public_discovery_only",src)


if __name__=='__main__':
    unittest.main()
