"""v0.2.78: isolated, invite-only family cohabitation (synthetic HTTP only).

Production users, Public calls, live orders and payment transfers are NEVER
used. This runs a disposable paired SQLite fixture in a subprocess to exercise
real app middleware without contaminating other test imports or environment.
"""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from cryptography.fernet import Fernet

from engine import identity_auth, shared_storage_cutover as storage
from engine import tenant_foundation


ORIGIN = "https://edgepilot.example.test"
OWNER_PASS = "SYNTHETIC-OWNER-LONG-PASSWORD-2026"
MEMBER_PASS = "SYNTHETIC-MEMBER-LONG-PASSWORD-2026"
OWNER_PUBLIC = "SYNTHETIC-OWNER-PUBLIC-SECRET-0000000001"
MEMBER_PUBLIC = "SYNTHETIC-MEMBER-PUBLIC-SECRET-000000002"
OWNER_PROVIDER_ID = "SYNTHETIC-OWNER-BROKERAGE-1"
MEMBER_PROVIDER_ID = "SYNTHETIC-MEMBER-BROKERAGE-2"

PROBE = r"""
import json
import os
import sqlite3
import sys
from pathlib import Path

from engine import shared_storage_cutover as storage
from engine import tenant_public_live_readonly as provider

root=Path(sys.argv[1])
storage.PERSISTENT_ROOT=root
import app

assert app.DB == root/'edgepilot.db'
assert app.TENANT_DB == root/'edgepilot-tenants.db'
assert not app.TENANT_POLICY['tenant_only']
assert app.family_invite_coexistence_enabled
assert app.tenant_signup_enabled and app.permanent_admin_invites_enabled
assert app.tenant_public_discovery_only
assert not app.tenant_passkeys_enabled
assert not app.tenant_monitor_preview_enabled
assert not app.tenant_watchlist_edit_enabled

origin='https://edgepilot.example.test'
owner=app.app.test_client()
member=app.app.test_client()
legacy=app.app.test_client()
anon=app.app.test_client()
def post(client,path,body=None,csrf=None,other_origin=None):
    headers={'Origin':origin if other_origin is None else other_origin}
    if csrf is not None:
        headers['X-Edge-Identity-CSRF']=csrf
    return client.post(path,base_url=origin,headers=headers,json=body if body is not None else {})
def get(client,path):
    return client.get(path,base_url=origin)

owner_login=post(owner,'/api/identity/login',{
    'username':'family-owner',
    'password':'SYNTHETIC-OWNER-LONG-PASSWORD-2026'})
assert owner_login.status_code == 200,owner_login.status_code
owner_csrf=owner_login.json['csrf']
legacy_login=post(legacy,'/api/login',{'accessToken':os.environ['EDGE_APP_TOKEN']})
assert legacy_login.status_code == 200,legacy_login.status_code
assert get(legacy,'/api/session').status_code == 200
assert get(legacy,'/api/identity/session').status_code == 401
assert get(owner,'/api/session').status_code == 401

# Public signup is still forbidden: registration is single-use-token only.
assert post(anon,'/api/identity/register',{
    'invitation':'bogus','username':'stranger','password':'SYNTHETIC-TEST-PASSWORD',
    'displayName':'Stranger'}).status_code == 400
assert post(anon,'/api/identity/admin/invitations').status_code == 401
assert post(owner,'/api/identity/admin/invitations').status_code == 403
assert post(owner,'/api/identity/admin/invitations',csrf=owner_csrf,
            other_origin='https://forged.example.test').status_code == 403
response=post(owner,'/api/identity/admin/invitations',csrf=owner_csrf)
assert response.status_code == 201,(response.status_code,response.get_data(as_text=True))
invite=response.json['invitation']
assert len(invite)==43 and response.json['newUserRole']=='member'
assert response.json['tradingEnabled'] is False
assert response.json['fundTransfersEnabled'] is False

registered=post(member,'/api/identity/register',{
    'invitation':invite,'username':'family-member',
    'password':'SYNTHETIC-MEMBER-LONG-PASSWORD-2026',
    'displayName':'Member Test'})
assert registered.status_code == 201,(registered.status_code,registered.get_data(as_text=True))
assert registered.json['role']=='member'
assert registered.json['tradingEnabled'] is False
assert post(anon,'/api/identity/register',{
    'invitation':invite,'username':'reused',
    'password':'SYNTHETIC-MEMBER-LONG-PASSWORD-2026',
    'displayName':'Reused'}).status_code == 400
member_login=post(member,'/api/identity/login',{
    'username':'family-member',
    'password':'SYNTHETIC-MEMBER-LONG-PASSWORD-2026'})
assert member_login.status_code == 200,member_login.status_code
member_csrf=member_login.json['csrf']
assert post(member,'/api/identity/admin/invitations',csrf=member_csrf).status_code == 403
assert get(member,'/api/session').status_code == 401
assert get(member,'/api/dashboard').status_code == 401

KEY_A='SYNTHETIC-OWNER-PUBLIC-SECRET-0000000001'
KEY_B='SYNTHETIC-MEMBER-PUBLIC-SECRET-000000002'
TOKEN_A='SYNTHETIC-OWNER-PUBLIC-TOKEN-AAAAAAAAA'
TOKEN_B='SYNTHETIC-MEMBER-PUBLIC-TOKEN-BBBBBBB'
BROKER_A='SYNTHETIC-OWNER-BROKERAGE-1'
BROKER_B='SYNTHETIC-MEMBER-BROKERAGE-2'
tokens={KEY_A:(TOKEN_A,BROKER_A),KEY_B:(TOKEN_B,BROKER_B)}
bearers={value[0]:value[1] for value in tokens.values()}
class FakePublic:
    def __init__(self): self.calls=[]
    @staticmethod
    def reply(data):
        class Reply:
            status_code=200
            def json(self): return data
        return Reply()
    def post(self,url,*,json,timeout):
        self.calls.append(('POST',url))
        assert url==provider.BASE+provider.AUTH_PATH
        assert set(json)=={'secret','validityInMinutes'}
        assert json['validityInMinutes']==5
        return self.reply({'accessToken':tokens[json['secret']][0]})
    def get(self,url,*,headers,timeout):
        self.calls.append(('GET',url))
        assert url==provider.BASE+provider.LIST_PATH
        bearer=headers.get('Authorization','').removeprefix('Bearer ')
        assert bearer in bearers
        return self.reply({'accounts':[{
            'accountId':bearers[bearer],'accountType':'BROKERAGE'}]})
fake=FakePublic()
app.tenant_public_reader.http=fake

links=[]
for client,csrf,secret,provider_id in (
        (owner,owner_csrf,KEY_A,BROKER_A),
        (member,member_csrf,KEY_B,BROKER_B)):
    saved=post(client,'/api/identity/public/connections',
               {'secret':secret},csrf)
    assert saved.status_code==201,(saved.status_code,saved.get_data(as_text=True))
    connection=saved.json['connectionId']
    assert secret not in saved.get_data(as_text=True)
    discovered=get(client,'/api/identity/public/read/connections/'+connection+'/accounts')
    assert discovered.status_code==200,(discovered.status_code,discovered.get_data(as_text=True))
    assert discovered.json['accounts'][0]['accountId']==provider_id
    link=post(client,'/api/identity/public/read/connections/'+connection+'/accounts',
              {'accountId':provider_id,'label':'My verified brokerage'},csrf)
    assert link.status_code==200,(link.status_code,link.get_data(as_text=True))
    assert link.json['verifiedByPublic']
    links.append((connection,link.json['accountId']))
assert links[0]!=links[1]

for client,other_connection,other_account in (
        (owner,links[1][0],links[1][1]),
        (member,links[0][0],links[0][1])):
    assert get(client,'/api/identity/public/read/connections/'+other_connection+'/accounts').status_code==404
    assert get(client,'/api/identity/public/read/accounts/'+other_account+'/portfolio').status_code==404
    assert get(client,'/api/identity/accounts').status_code==200
    assert get(client,'/api/identity/public/connections').status_code==200
    assert get(client,'/api/dashboard').status_code==401
    assert get(client,'/api/automation/status').status_code==401
    assert get(client,'/api/identity/passkeys').status_code==404
    assert get(client,'/api/identity/accounts/'+other_account+'/monitor/preview').status_code==404
    for own_account in (links[0][1],links[1][1]):
        assert get(client,'/api/identity/public/read/accounts/'+own_account+'/portfolio').status_code==404
assert get(legacy,'/api/identity/accounts').status_code==401
assert get(legacy,'/api/identity/public/connections').status_code==401
assert get(legacy,'/api/identity/admin/invitations').status_code==401
assert get(legacy,'/api/session').status_code==200
assert all(
    (method=='POST' and url==provider.BASE+provider.AUTH_PATH) or
    (method=='GET' and url==provider.BASE+provider.LIST_PATH)
    for method,url in fake.calls)
assert fake.calls

with sqlite3.connect(app.DB) as db:
    assert db.execute(
        "SELECT ciphertext FROM broker_credentials WHERE provider='public'"
    ).fetchone()[0]==b'SYNTHETIC-LEGACY-BROKER-CIPHERTEXT'
    assert db.execute(
        "SELECT name FROM sqlite_master WHERE name='tenant_users'"
    ).fetchone() is None
with sqlite3.connect(app.TENANT_DB) as db:
    assert db.execute(
        "SELECT COUNT(*) FROM tenant_users"
    ).fetchone()[0]==2
    assert db.execute(
        "SELECT COUNT(*) FROM tenant_users WHERE role='owner'"
    ).fetchone()[0]==1
    assert db.execute(
        "SELECT COUNT(*) FROM tenant_users WHERE role='member'"
    ).fetchone()[0]==1
    assert db.execute(
        "SELECT COUNT(*) FROM permanent_invitation_issues"
    ).fetchone()[0]==1
    tokens_in_db=[row[0] for row in db.execute(
        "SELECT credential_ciphertext FROM tenant_connections")]
    assert len(tokens_in_db)==2 and all(
        KEY_A.encode() not in cipher and KEY_B.encode() not in cipher
        for cipher in tokens_in_db)
    assert not db.execute(
        "SELECT 1 FROM tenant_signup_invites WHERE token_hash=?",
        (invite,)).fetchone()
print(json.dumps({
    'privateOwnerInvited':True,
    'oneTimeInvitation':True,
    'legacyUnchanged':True,
    'isolatedPublicLinks':True,
    'memberCannotInvite':True,
    'noOrderOrTransfer':True,
    'noPublicNetwork':True,
    'enabledInProduction':False
}))
"""

ROLLBACK_PROBE = r"""
import json,sys
from pathlib import Path
from engine import shared_storage_cutover as storage
root=Path(sys.argv[1])
storage.PERSISTENT_ROOT=root
import app
assert not app.family_invite_coexistence_enabled
assert not app.tenant_signup_enabled and not app.permanent_admin_invites_enabled
assert app.tenant_public_discovery_only
base='https://edgepilot.example.test'
a=app.app.test_client()
b=app.app.test_client()
legacy=app.app.test_client()
def login(client,username,password):
    return client.post('/api/identity/login',
        base_url=base,headers={'Origin':base},
        json={'username':username,'password':password})
assert login(a,'family-owner','SYNTHETIC-OWNER-LONG-PASSWORD-2026').status_code==200
assert login(b,'family-member','SYNTHETIC-MEMBER-LONG-PASSWORD-2026').status_code==200
assert a.post('/api/identity/admin/invitations',
    base_url=base,headers={'Origin':base},json={}).status_code==404
assert b.post('/api/identity/register',
    base_url=base,headers={'Origin':base},json={}).status_code==404
legacy_login=legacy.post('/api/login',base_url=base,
    headers={'Origin':base},json={'accessToken':'SYNTHETIC-LEGACY-TOKEN-2026-0123456789'})
assert legacy_login.status_code==200
print(json.dumps({'existingMembersRetained':True,'invitesDisabled':True,'legacyStillWorks':True}))
"""


class FamilyInvitationCoexistenceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="edgepilot-invite-family-")
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.legacy=self.root/"edgepilot.db"
        self.tenant=self.root/"edgepilot-tenants.db"
        with sqlite3.connect(self.legacy) as db:
            db.execute("CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT NOT NULL)")
            db.execute("INSERT INTO settings VALUES('account_id','SYNTHETIC-LEGACY')")
            db.execute(
                "CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY,ciphertext BLOB)")
            db.execute(
                "INSERT INTO broker_credentials VALUES('public',?)",
                (b'SYNTHETIC-LEGACY-BROKER-CIPHERTEXT',))
        tenant_foundation.setup(str(self.tenant))
        identity_auth.setup(str(self.tenant))
        user=tenant_foundation.TenantStore(str(self.tenant)).provision_user(
            "Synthetic family owner",role="owner")
        identity_auth.IdentityStore(str(self.tenant)).provision(
            user,"family-owner",OWNER_PASS)
        os.chmod(self.legacy,0o600)
        os.chmod(self.tenant,0o600)
        self.env={
            "EDGE_DB_PATH":str(self.legacy),
            "EDGE_TENANT_DB_PATH":str(self.tenant),
            **{name:"true" for name in storage.FAMILY_INVITE_REQUIRED},
            **{name:"false" for name in storage.FAMILY_INVITE_FORBIDDEN},
            storage.FAMILY_INVITE_COEXISTENCE_FLAG:"true",
            "EDGE_CREDENTIAL_KEY":Fernet.generate_key().decode(),
            "EDGE_APP_TOKEN":"SYNTHETIC-LEGACY-TOKEN-2026-0123456789",
            "PUBLIC_API_SECRET":"",
            "EDGE_STAGING_OPERATOR_SHA256":"",
        }

    def test_opted_in_synthetic_two_client_end_to_end(self):
        self.assertTrue(storage.family_invite_coexistence_policy(self.env))
        env=os.environ.copy()
        env.update(self.env)
        p=subprocess.run([sys.executable,"-c",PROBE,str(self.root)],
            env=env,cwd=str(Path(__file__).resolve().parents[1]),
            capture_output=True,text=True,timeout=70)
        self.assertEqual(p.returncode,0,p.stderr[-2400:]+p.stdout[-450:])
        result=json.loads(p.stdout.strip().splitlines()[-1])
        self.assertTrue(all(result[k] for k in (
            "privateOwnerInvited","oneTimeInvitation","legacyUnchanged",
            "isolatedPublicLinks","memberCannotInvite","noOrderOrTransfer",
            "noPublicNetwork")))
        self.assertFalse(result["enabledInProduction"])
        for secret in (OWNER_PUBLIC,MEMBER_PUBLIC,OWNER_PASS,MEMBER_PASS):
            self.assertNotIn(secret,p.stdout)

    def test_fail_closed_required_optins_and_unsafe_feature_flags(self):
        # This selector is read-only: never create or mutate either file.
        for flag in storage.FAMILY_INVITE_REQUIRED:
            with self.subTest(disabled=flag):
                bad={**self.env,flag:"false"}
                with self.assertRaises(storage.SharedStorageDenied):
                    storage.select_tenant_database(
                        bad,self.legacy,persistent_root=self.root)
        for flag in storage.FAMILY_INVITE_FORBIDDEN:
            with self.subTest(activated=flag):
                bad={**self.env,flag:"true"}
                with self.assertRaises(storage.SharedStorageDenied):
                    storage.select_tenant_database(
                        bad,self.legacy,persistent_root=self.root)
        for change in (
            {storage.FAMILY_INVITE_COEXISTENCE_FLAG:"false"},
            {"EDGE_TENANT_DB_PATH":str(self.legacy)},
            {"EDGE_CREDENTIAL_KEY":"invalid"},
            {"EDGE_TENANT_DB_PATH":""},
        ):
            with self.subTest(changes=list(change)):
                with self.assertRaises(storage.SharedStorageDenied):
                    storage.select_tenant_database(
                        {**self.env,**change},self.legacy,persistent_root=self.root)

    def test_disable_invitation_gates_without_locking_out_existing_members(self):
        self.test_opted_in_synthetic_two_client_end_to_end()
        rollback_env={**self.env,
            storage.FAMILY_INVITE_COEXISTENCE_FLAG:"false",
            "EDGE_TENANT_SIGNUP_ENABLED":"false",
            "EDGE_PERMANENT_OWNER_INVITES_ENABLED":"false"}
        self.assertFalse(storage.family_invite_coexistence_policy(rollback_env))
        self.assertEqual(storage.select_tenant_database(
            rollback_env,self.legacy,persistent_root=self.root),self.tenant)
        env=os.environ.copy()
        env.update(rollback_env)
        p=subprocess.run([sys.executable,"-c",ROLLBACK_PROBE,str(self.root)],
            env=env,cwd=str(Path(__file__).resolve().parents[1]),
            capture_output=True,text=True,timeout=40)
        self.assertEqual(p.returncode,0,p.stderr[-1800:]+p.stdout[-350:])
        self.assertTrue(all(json.loads(p.stdout.strip().splitlines()[-1]).values()))


if __name__=="__main__":
    unittest.main()
