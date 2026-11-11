"""v0.2.61: permanent owner invitation limits and two-user HTTP isolation."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from engine import identity_auth, permanent_admin_invitations as admins
from engine import tenant_foundation, tenant_registration

PASSWORD="long-synthetic-password-for-tests"


class PermanentPrivateInvitationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=str(Path(self.tmp.name)/"tenants.db")
        tenant_foundation.setup(self.path)
        identity_auth.setup(self.path)
        tenant_registration.setup(self.path)
        admins.setup(self.path)
        self.users=tenant_foundation.TenantStore(self.path)
        self.owner=self.users.provision_user("Private Owner",role="owner")
        self.member=self.users.provision_user("Existing Member",role="member")
        self.auth=identity_auth.IdentityStore(self.path)
        self.auth.provision(self.owner,"private-owner",PASSWORD)
        self.auth.provision(self.member,"private-member",PASSWORD)
        self.owner_session=self.auth.authenticate("private-owner",PASSWORD,source="owner")
        self.member_session=self.auth.authenticate("private-member",PASSWORD,source="member")
        self.issue=admins.PermanentAdminInvitations(self.path,self.auth)

    def test_only_real_owner_session_mints_invites_and_raw_token_is_not_stored(self):
        with self.assertRaises(admins.PermanentInvitationDenied):
            self.issue.issue(self.member_session["token"],self.member_session["csrf"])
        with self.assertRaises(admins.PermanentInvitationDenied):
            self.issue.issue(self.owner_session["token"],self.member_session["csrf"])
        with self.assertRaises(admins.PermanentInvitationDenied):
            self.issue.issue("bad",self.owner_session["csrf"])
        invitation=self.issue.issue(self.owner_session["token"],self.owner_session["csrf"])
        self.assertEqual(invitation["newUserRole"],"member")
        self.assertFalse(invitation["tradingEnabled"])
        self.assertEqual(len(invitation["invitation"]),43)
        with sqlite3.connect(self.path) as db:
            value=db.execute("SELECT token_hash FROM tenant_signup_invites").fetchone()[0]
            self.assertNotEqual(value,invitation["invitation"])
            self.assertEqual(len(value),64)
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM permanent_invitation_issues").fetchone()[0],1)

    def test_session_revoke_blocks_issuing_and_member_role_cannot_elevate(self):
        self.auth.revoke(self.owner_session["token"])
        with self.assertRaises(admins.PermanentInvitationDenied):
            self.issue.issue(self.owner_session["token"],self.owner_session["csrf"])
        with self.assertRaises(admins.PermanentInvitationDenied):
            self.issue.issue(self.member_session["token"],self.member_session["csrf"])

    def test_count_limits_ten_accounts_and_atomic_member_registration(self):
        # Already one owner and one member; only eight future invitations.
        invites=[self.issue.issue(self.owner_session["token"],self.owner_session["csrf"])
                 ["invitation"] for _ in range(8)]
        with self.assertRaises(admins.PermanentInvitationDenied):
            self.issue.issue(self.owner_session["token"],self.owner_session["csrf"])
        registration=tenant_registration.TenantRegistration(self.path,max_users=10)
        for idx,token in enumerate(invites):
            result=registration.register(token,f"family-{idx}",PASSWORD,
                                         f"Family member {idx}",source="private-test-"+str(idx))
            self.assertEqual(result["role"],"member")
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tenant_users").fetchone()[0],10)
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM tenant_users WHERE role='owner'").fetchone()[0],1)
        extra=tenant_registration.TenantRegistration(self.path).issue_invitation()["invitation"]
        with self.assertRaises(tenant_registration.RegistrationDenied):
            registration.register(extra,"extra-member",PASSWORD,"Extra",source="private-extra")
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tenant_users").fetchone()[0],10)

    def test_invitation_audit_cannot_be_deleted_or_rewritten(self):
        self.issue.issue(self.owner_session["token"],self.owner_session["csrf"])
        for sql in ("DELETE FROM permanent_invitation_issues",
                    "UPDATE permanent_invitation_issues SET issued_at=0"):
            with self.assertRaises(sqlite3.IntegrityError), sqlite3.connect(self.path) as db:
                db.execute(sql)

    def test_permanent_http_owner_and_csrf_boundaries(self):
        root=Path(self.tmp.name)
        legacy=root/"edgepilot.db"
        tenant=root/"edgepilot-tenants.db"
        with sqlite3.connect(legacy) as db:
            db.execute("CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT NOT NULL)")
            db.execute("INSERT INTO settings VALUES('account_id','UNMIGRATED-OWNER')")
            db.execute("""CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY,
                ciphertext BLOB,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            db.execute("INSERT INTO broker_credentials(provider,ciphertext) VALUES('public',?)",
                       (b'SYNTHETIC-LEGACY-BYTES',))
        script="""
import json,sqlite3,sys
from pathlib import Path
from engine import shared_storage_cutover
shared_storage_cutover.PERSISTENT_ROOT=Path(sys.argv[1])
import app
owner=app.tenant_foundation.TenantStore(str(app.TENANT_DB)).provision_user('Owner',role='owner')
member=app.tenant_foundation.TenantStore(str(app.TENANT_DB)).provision_user('Member',role='member')
app.identity_store.provision(owner,'owner-person','long-synthetic-password-for-tests')
app.identity_store.provision(member,'member-person','long-synthetic-password-for-tests')
client=app.app.test_client()
base='https://edgepilot.belenoscreations.biz'
def login(who):
  r=client.post('/api/identity/login',base_url=base,headers={'Origin':base},
                json={'username':who,'password':'long-synthetic-password-for-tests'})
  assert r.status_code==200,(who,r.status_code)
  return r.json['csrf']
owner_csrf=login('owner-person')
wrong=client.post('/api/identity/admin/invitations',base_url=base,headers={'Origin':base},
                  json={})
assert wrong.status_code==403
good=client.post('/api/identity/admin/invitations',base_url=base,
                 headers={'Origin':base,'X-Edge-Identity-CSRF':owner_csrf},json={})
assert good.status_code==201,(good.status_code,good.get_data(as_text=True))
token=good.json['invitation']
assert len(token)==43 and good.json['newUserRole']=='member'
member_csrf=login('member-person')
denied=client.post('/api/identity/admin/invitations',base_url=base,
        headers={'Origin':base,'X-Edge-Identity-CSRF':member_csrf},json={})
assert denied.status_code==403
assert client.get('/api/settings',base_url=base).status_code==404
assert client.get('/healthz',base_url=base).status_code==200
with sqlite3.connect(app.DB) as db:
  assert db.execute("SELECT ciphertext FROM broker_credentials").fetchone()[0]==b'SYNTHETIC-LEGACY-BYTES'
  assert db.execute("SELECT name FROM sqlite_master WHERE name='tenant_users'").fetchone() is None
with sqlite3.connect(app.TENANT_DB) as db:
  assert db.execute("SELECT COUNT(*) FROM permanent_invitation_issues").fetchone()[0]==1
print(json.dumps({'ownerOnly':True,'preservedLegacy':True}))
"""
        env=os.environ.copy()
        env.update({
            "EDGE_DB_PATH":str(legacy),
            "EDGE_TENANT_DB_PATH":str(tenant),
            "EDGE_SHARED_TENANT_DB_PREPARE":"true",
            "EDGE_TENANT_SCHEMA_PREPARE":"true",
            "EDGE_IDENTITY_AUTH_ENABLED":"true",
            "EDGE_TENANT_SIGNUP_ENABLED":"true",
            "EDGE_PERMANENT_TENANTS_ONLY":"true",
            "EDGE_PERMANENT_OWNER_INVITES_ENABLED":"true",
            "EDGE_ISOLATED_STAGING":"false",
            "EDGE_AUTOMATION_WORKER_ENABLED":"false",
            "ENABLE_LIVE_ORDERS":"false",
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED":"false",
            "EDGE_TENANT_PUBLIC_READONLY_ENABLED":"false",
            "EDGE_TENANT_ACCOUNT_READS_ENABLED":"false",
            "EDGE_APP_TOKEN":"",
            "PUBLIC_API_SECRET":"",
            "EDGE_CREDENTIAL_KEY":"",
        })
        run=subprocess.run([sys.executable,"-c",script,str(root)],
                           cwd=str(Path(__file__).resolve().parents[1]),
                           env=env,capture_output=True,text=True,timeout=45)
        self.assertEqual(run.returncode,0,run.stderr[-1500:])
        self.assertTrue(json.loads(run.stdout.strip().splitlines()[-1])["ownerOnly"])


if __name__=="__main__":
    unittest.main()
