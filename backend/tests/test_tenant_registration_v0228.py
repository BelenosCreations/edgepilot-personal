"""v0.2.28 invitation signup: two independent EdgePilot identities, no live Public.

Synthetic accounts, credentials and a temporary SQLite database only.
"""
import importlib
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from cryptography.fernet import Fernet
from engine import identity_auth, tenant_foundation, tenant_registration

HOST="https://edgepilot.example.test"
ORIGIN={"Origin":HOST}
A_PW="some-unique-very-long-test-password-A"
B_PW="some-unique-very-long-test-password-B"


class InvitationSignupUnitTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="edgepilot-signup-")
        self.path=self.temp.name+"/tenants.db"
        tenant_foundation.setup(self.path)
        identity_auth.setup(self.path)
        tenant_registration.setup(self.path)
        self.signups=tenant_registration.TenantRegistration(self.path)
        self.now=1900000000

    def tearDown(self):
        self.temp.cleanup()

    def invite(self,ttl_seconds=3600):
        return self.signups.issue_invitation(ttl_seconds=ttl_seconds,now=self.now)["invitation"]

    def signup(self,invitation,login,label,source="phone-a"):
        return self.signups.register(invitation,login,A_PW,label,source=source,now=self.now)

    def test_invite_redemption_creates_member_with_no_automatic_session_or_credentials(self):
        a=self.invite()
        b=self.invite()
        self.assertTrue(self.signup(a,"first_owner","First User")["loginRequired"])
        self.assertTrue(self.signup(b,"second_owner","Second User",source="phone-b")["registered"])
        with sqlite3.connect(self.path) as con:
            users=con.execute("SELECT role,label FROM tenant_users ORDER BY label").fetchall()
            self.assertEqual(users,[("member","First User"),("member","Second User")])
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tenant_identity_sessions").fetchone()[0],0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tenant_connections").fetchone()[0],0)
            hashes=con.execute("SELECT token_hash FROM tenant_signup_invites").fetchall()
            self.assertEqual(len(hashes),2)
            self.assertTrue(all(len(row[0])==64 for row in hashes))
            self.assertNotIn(a,str(hashes))
            self.assertNotIn(A_PW,str(con.execute("SELECT password_hash FROM tenant_identities").fetchall()))
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tenant_audit_events WHERE action='USER_PROVISIONED'").fetchone()[0],2)
        login=identity_auth.IdentityStore(self.path).authenticate("first_owner",A_PW,"phone-a",now=self.now)
        self.assertIsNotNone(login)

    def test_one_use_expiry_wrong_invite_and_atomic_duplicate_rollback(self):
        a=self.invite()
        self.signup(a,"first_owner","First User")
        with self.assertRaises(tenant_registration.RegistrationDenied):
            self.signup(a,"second_owner","Second User")
        b=self.invite()
        with self.assertRaises(tenant_registration.RegistrationDenied):
            self.signup(b,"first_owner","Duplicate Login",source="other")
        # Duplicate username rolled back without consuming the invitation.
        self.signup(b,"second_owner","Second User",source="another")
        with self.assertRaises(tenant_registration.RegistrationDenied):
            self.signup("not-a-real-invitation","third_owner","Third User")
        short=self.invite(ttl_seconds=60)
        with self.assertRaises(tenant_registration.RegistrationDenied):
            self.signups.register(short,"expired_user",A_PW,"Expired",
                                  source="fresh",now=self.now+60)
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tenant_users").fetchone()[0],2)

    def test_identity_validators_and_no_owner_role_selection(self):
        token=self.invite()
        for login,pwd,label in (
            ("a",A_PW,"User"),("validlogin","short","User"),
            ("validlogin",A_PW,""),("validlogin",A_PW,"x"*130),
            ("validlogin",A_PW,"Bad\x00Label")
        ):
            with self.assertRaises(tenant_registration.RegistrationDenied):
                self.signups.register(token,login,pwd,label,source="source")
        result=self.signups.register(token,"validlogin",A_PW,"Legit",source="source")
        self.assertEqual(result["role"],"member")
        self.assertFalse(result["tradingEnabled"])

    def test_per_source_attempt_limit_does_not_block_another_person(self):
        bad="A"*43
        for _ in range(tenant_registration.MAX_ATTEMPTS_PER_SOURCE):
            with self.assertRaises(tenant_registration.RegistrationDenied):
                self.signup(bad,"random_user","Random User")
        with self.assertRaises(tenant_registration.RegistrationRateLimited):
            self.signup(self.invite(),"not_allowed","Limit")
        self.signup(self.invite(),"newperson","New",source="other-device")

    def test_two_parallel_redemptions_one_invitation_only_one_account(self):
        token=self.invite()
        def attempt(i):
            try:
                return self.signup(token,"concurrent_"+str(i),"User "+str(i),
                                   source="distinct-"+str(i))["registered"]
            except tenant_registration.RegistrationDenied:
                return False
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes=list(executor.map(attempt,(1,2)))
        self.assertEqual(outcomes.count(True),1)
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tenant_users").fetchone()[0],1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tenant_identities").fetchone()[0],1)

    def test_explicit_invitation_policy_and_schema_preconditions(self):
        with self.assertRaises(ValueError):
            self.signups.issue_invitation(ttl_seconds=8,now=self.now)
        with self.assertRaises(ValueError):
            self.signups.issue_invitation(ttl_seconds=99999999,now=self.now)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(RuntimeError):
                tenant_registration.setup(temp+"/unprepared.db")


class InvitationSignupHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="edgepilot-signup-http-")
        self.env=patch.dict(os.environ,{
            "EDGE_DB_PATH":self.temp.name+"/edgepilot.db",
            "EDGE_TENANT_SCHEMA_PREPARE":"true",
            "EDGE_IDENTITY_AUTH_ENABLED":"true",
            "EDGE_TENANT_SIGNUP_ENABLED":"true",
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED":"true",
            "EDGE_TENANT_PUBLIC_READONLY_ENABLED":"false",
            "EDGE_TENANT_ACCOUNT_READS_ENABLED":"false",
            "EDGE_CREDENTIAL_KEY":Fernet.generate_key().decode(),
            "EDGE_APP_TOKEN":"legacy-owner-test-secret-only-0000000000000000",
            "PUBLIC_API_SECRET":"",
            "EDGE_AUTOMATION_WORKER_ENABLED":"false"
        })
        self.env.start()
        import app
        self.mod=importlib.reload(app)
        self.a=self.mod.app.test_client()
        self.b=self.mod.app.test_client()

    def tearDown(self):
        self.env.stop()
        import app
        importlib.reload(app)
        self.temp.cleanup()

    def invite(self):
        return self.mod.tenant_registration_store.issue_invitation()["invitation"]

    def register(self,client,invite,username,password,label):
        return client.post("/api/identity/register",base_url=HOST,headers=ORIGIN,
                           json={"invitation":invite,"username":username,
                                 "password":password,"displayName":label})

    def login(self,client,username,password):
        return client.post("/api/identity/login",base_url=HOST,headers=ORIGIN,
                           json={"username":username,"password":password})

    def test_two_devices_register_and_own_private_vaults_without_legacy_access(self):
        a=self.register(self.a,self.invite(),"alice_owner",A_PW,"Alice")
        b=self.register(self.b,self.invite(),"bob_owner",B_PW,"Bob")
        self.assertEqual((a.status_code,b.status_code),(201,201))
        self.assertNotIn("Set-Cookie",a.headers)
        self.assertEqual(self.a.get("/api/identity/session",base_url=HOST).status_code,401)
        la=self.login(self.a,"alice_owner",A_PW)
        lb=self.login(self.b,"bob_owner",B_PW)
        self.assertEqual((la.status_code,lb.status_code),(200,200))
        self.assertNotEqual(la.headers["Set-Cookie"],lb.headers["Set-Cookie"])
        sa=self.a.get("/api/identity/session",base_url=HOST).get_json()
        sb=self.b.get("/api/identity/session",base_url=HOST).get_json()
        self.assertNotEqual(sa["user"]["userId"],sb["user"]["userId"])
        self.assertEqual(sa["user"]["role"],"member")
        key_a="synthetic-Public-key-for-alice-owner-000001"
        key_b="synthetic-Public-key-for-bob-owner-000002"
        r1=self.a.post("/api/identity/public/connections",base_url=HOST,
                       headers={**ORIGIN,"X-Edge-Identity-CSRF":sa["csrf"]},
                       json={"secret":key_a})
        r2=self.b.post("/api/identity/public/connections",base_url=HOST,
                       headers={**ORIGIN,"X-Edge-Identity-CSRF":sb["csrf"]},
                       json={"secret":key_b})
        self.assertEqual((r1.status_code,r2.status_code),(201,201))
        own_a=self.a.get("/api/identity/public/connections",base_url=HOST).get_json()
        own_b=self.b.get("/api/identity/public/connections",base_url=HOST).get_json()
        self.assertEqual(len(own_a["connections"]),1)
        self.assertEqual(len(own_b["connections"]),1)
        self.assertNotEqual(own_a["connections"][0]["connectionId"],own_b["connections"][0]["connectionId"])
        self.assertNotIn(key_a,str(own_a))
        self.assertNotIn(key_b,str(own_b))
        self.assertEqual(self.a.get("/api/health",base_url=HOST).status_code,401)
        self.assertEqual(self.b.get("/api/dashboard",base_url=HOST).status_code,401)
        self.assertEqual(self.a.get("/api/identity/public/read/connections/not-real/accounts",base_url=HOST).status_code,404)

    def test_route_rejects_cross_origin_extra_fields_and_replayed_invite(self):
        invite=self.invite()
        payload={"invitation":invite,"username":"test_signup",
                 "password":A_PW,"displayName":"New"}
        bad=self.a.post("/api/identity/register",base_url=HOST,
                        headers={"Origin":"https://attacker.invalid"},json=payload)
        self.assertEqual(bad.status_code,403)
        extra=self.a.post("/api/identity/register",base_url=HOST,
                          headers=ORIGIN,json={**payload,"role":"owner"})
        self.assertEqual(extra.status_code,400)
        self.assertEqual(self.a.post("/api/identity/register",base_url=HOST,
                                    headers=ORIGIN,json=payload).status_code,201)
        self.assertEqual(self.a.post("/api/identity/register",base_url=HOST,
                                    headers=ORIGIN,json=payload).status_code,400)


class SignupDisabledDefaultTests(unittest.TestCase):
    def test_registration_route_not_available_without_signup_feature(self):
        with tempfile.TemporaryDirectory(prefix="edgepilot-signup-disabled-") as d:
            with patch.dict(os.environ,{
                "EDGE_DB_PATH":d+"/edgepilot.db",
                "EDGE_TENANT_SCHEMA_PREPARE":"true",
                "EDGE_IDENTITY_AUTH_ENABLED":"true",
                "EDGE_TENANT_SIGNUP_ENABLED":"false",
                "EDGE_AUTOMATION_WORKER_ENABLED":"false"
            }):
                import app
                mod=importlib.reload(app)
                response=mod.app.test_client().post("/api/identity/register",
                    base_url=HOST,headers=ORIGIN,json={})
                self.assertEqual(response.status_code,404)
                with sqlite3.connect(d+"/edgepilot.db") as con:
                    self.assertFalse(con.execute("""SELECT 1 FROM sqlite_master
                        WHERE type='table' AND name='tenant_signup_invites'""").fetchone())
        import app
        importlib.reload(app)


if __name__=="__main__":
    unittest.main()
