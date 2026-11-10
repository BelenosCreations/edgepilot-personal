"""v0.2.26: per-user encrypted Public vault; fake keys, two app sessions.

Tests exercise opt-in Flask routes only with disposable SQLite and synthetic
credentials. Never send an actual Public API key into tests or logs.
"""
import importlib
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from engine import identity_auth, tenant_foundation, tenant_public_vault, tenant_route_audit

HOST="https://edgepilot.example.test"
ORIGIN={"Origin":HOST}
KEY_A="synthetic-Public-key-owner-A-000000000001"
KEY_A_NEW="synthetic-Public-key-owner-A-ROTATED-002"
KEY_B="synthetic-Public-key-owner-B-000000000002"


class TenantPublicVaultUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="edgepilot-vault-")
        self.path=self.tmp.name+"/tenants.db"
        tenant_foundation.setup(self.path)
        identity_auth.setup(self.path)
        tenant_public_vault.setup(self.path)
        self.tenant_store=tenant_foundation.TenantStore(
            self.path,credential_key=Fernet.generate_key().decode())
        self.owner=self.tenant_store.provision_user("Owner A","owner")
        self.other=self.tenant_store.provision_user("Owner B","member")
        self.identities=identity_auth.IdentityStore(self.path)
        self.identities.provision(self.owner,"first_login","some-safe-long-password-A")
        self.identities.provision(self.other,"second_login","some-safe-long-password-B")
        self.a=self.identities.authenticate("first_login","some-safe-long-password-A","phone-a")
        self.b=self.identities.authenticate("second_login","some-safe-long-password-B","phone-b")
        self.vault=tenant_public_vault.TenantPublicVault(
            self.path,self.identities,credential_key=self.tenant_store.credential_key)

    def tearDown(self):
        self.tmp.cleanup()

    def test_encrypted_independent_credentials_and_zero_legacy_leakage(self):
        conn_a=self.vault.save(self.a["token"],self.a["csrf"],KEY_A)["connectionId"]
        conn_b=self.vault.save(self.b["token"],self.b["csrf"],KEY_B)["connectionId"]
        rows=self.vault.list_connections(self.a["token"])["connections"]
        self.assertEqual([r["connectionId"] for r in rows],[conn_a])
        self.assertEqual(rows[0]["status"],"stored_unverified")
        self.assertEqual(self.vault.list_connections(self.b["token"])["connections"][0]["connectionId"],conn_b)
        self.assertNotIn(KEY_A,str(self.vault.list_connections(self.a["token"])))
        with sqlite3.connect(self.path) as db:
            saved=db.execute("SELECT credential_ciphertext FROM tenant_connections").fetchall()
        self.assertEqual(len(saved),2)
        self.assertNotIn(KEY_A.encode(),b"".join(r[0] for r in saved))
        self.assertNotIn(KEY_B.encode(),b"".join(r[0] for r in saved))
        self.assertEqual(self.vault._credential_for_provider_only(self.a["token"],conn_a),KEY_A)
        self.assertEqual(self.vault._credential_for_provider_only(self.b["token"],conn_b),KEY_B)
        for token,other in ((self.a["token"],conn_b),(self.b["token"],conn_a)):
            with self.assertRaises(tenant_public_vault.TenantVaultDenied):
                self.vault._credential_for_provider_only(token,other)

    def test_cross_owner_rotation_revoke_and_linked_account_disable(self):
        conn_a=self.vault.save(self.a["token"],self.a["csrf"],KEY_A)["connectionId"]
        conn_b=self.vault.save(self.b["token"],self.b["csrf"],KEY_B)["connectionId"]
        acc_a=self.tenant_store.link_account(self.owner,conn_a,"SYNTHETIC-A","Owner A")
        acc_b=self.tenant_store.link_account(self.other,conn_b,"SYNTHETIC-B","Owner B")
        for action in (
            lambda:self.vault.rotate(self.b["token"],self.b["csrf"],conn_a,KEY_B),
            lambda:self.vault.disconnect(self.b["token"],self.b["csrf"],conn_a),
            lambda:self.vault.rotate(self.a["token"],self.b["csrf"],conn_a,KEY_A_NEW),
        ):
            with self.assertRaises(tenant_public_vault.TenantVaultDenied):
                action()
        with self.assertRaises(tenant_public_vault.TenantVaultDenied):
            self.vault.rotate(self.a["token"],self.a["csrf"],conn_a,None)
        self.assertEqual(self.vault._credential_for_provider_only(self.a["token"],conn_a),KEY_A)
        rotated=self.vault.rotate(self.a["token"],self.a["csrf"],conn_a,KEY_A_NEW)
        self.assertEqual(rotated["status"],"stored_unverified")
        self.assertEqual(self.vault._credential_for_provider_only(self.a["token"],conn_a),KEY_A_NEW)
        with sqlite3.connect(self.path) as db:
            rows=db.execute("SELECT account_id,disabled_at FROM tenant_accounts").fetchall()
        results={a:b for a,b in rows}
        self.assertIsNotNone(results[acc_a])
        self.assertIsNone(results[acc_b])
        self.assertEqual(self.tenant_store.list_accounts(self.other)[0]["account_id"],acc_b)
        removed=self.vault.disconnect(self.a["token"],self.a["csrf"],conn_a)
        self.assertEqual(removed["status"],"revoked")
        with self.assertRaises(tenant_public_vault.TenantVaultDenied):
            self.vault._credential_for_provider_only(self.a["token"],conn_a)
        self.assertEqual(self.vault._credential_for_provider_only(self.b["token"],conn_b),KEY_B)
        with sqlite3.connect(self.path) as db:
            audits=db.execute("SELECT event,user_id FROM tenant_public_vault_events").fetchall()
            self.assertEqual(audits,[("ROTATE",self.owner),("REVOKE",self.owner)])
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM tenant_public_vault_events")
        with self.assertRaises(tenant_public_vault.TenantVaultDenied):
            self.vault.disconnect(self.a["token"],self.a["csrf"],conn_a)

    def test_missing_or_wrong_key_never_overwrites_encrypted_credential(self):
        conn=self.vault.save(self.a["token"],self.a["csrf"],KEY_A)["connectionId"]
        vault_without_key=tenant_public_vault.TenantPublicVault(self.path,self.identities,
                                                               credential_key="")
        with patch.dict(os.environ,{"EDGE_CREDENTIAL_KEY":""}):
            with self.assertRaises(tenant_public_vault.TenantVaultDenied):
                vault_without_key.rotate(self.a["token"],self.a["csrf"],conn,KEY_A_NEW)
        self.assertEqual(self.vault._credential_for_provider_only(self.a["token"],conn),KEY_A)

    def test_revoked_sessions_or_disabled_identity_denied(self):
        with self.assertRaises(tenant_public_vault.TenantVaultDenied):
            self.vault.save(self.a["token"],self.b["csrf"],KEY_A)
        self.identities.revoke(self.a["token"])
        with self.assertRaises(tenant_public_vault.TenantVaultDenied):
            self.vault.save(self.a["token"],self.a["csrf"],KEY_A)
        self.assertEqual(self.vault.list_connections(self.b["token"])["connections"],[])


class TenantPublicVaultHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="edgepilot-http-vault-")
        self.path=self.tmp.name+"/edge.db"
        self.key=Fernet.generate_key().decode()
        self.env=patch.dict(os.environ,{
            "EDGE_DB_PATH":self.path,
            "EDGE_TENANT_SCHEMA_PREPARE":"true",
            "EDGE_IDENTITY_AUTH_ENABLED":"true",
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED":"true",
            "EDGE_TENANT_ACCOUNT_READS_ENABLED":"false",
            "EDGE_CREDENTIAL_KEY":self.key,
            "EDGE_APP_TOKEN":"legacy-shared-token-not-used-by-tenants-9999",
            "PUBLIC_API_SECRET":"",
            "EDGE_AUTOMATION_WORKER_ENABLED":"false",
        })
        self.env.start()
        import app
        self.appmod=importlib.reload(app)
        self.users=[
            self.appmod.tenant_foundation.TenantStore(self.path).provision_user("User A"),
            self.appmod.tenant_foundation.TenantStore(self.path).provision_user("User B"),
        ]
        self.appmod.identity_store.provision(self.users[0],"user_a","password-is-long-enough-a")
        self.appmod.identity_store.provision(self.users[1],"user_b","password-is-long-enough-b")
        self.clients=[self.appmod.app.test_client(),self.appmod.app.test_client()]
        self.csrf=[]
        for client,username,password in (
            (self.clients[0],"user_a","password-is-long-enough-a"),
            (self.clients[1],"user_b","password-is-long-enough-b"),
        ):
            login=client.post("/api/identity/login",base_url=HOST,headers=ORIGIN,
                              json={"username":username,"password":password})
            self.assertEqual(login.status_code,200)
            self.csrf.append(login.get_json()["csrf"])

    def tearDown(self):
        self.env.stop()
        import app
        importlib.reload(app)
        self.tmp.cleanup()

    def post(self,ix,path,body,csrf=None):
        return self.clients[ix].post(path,base_url=HOST,json=body,headers={
            **ORIGIN,"X-Edge-Identity-CSRF":self.csrf[ix] if csrf is None else csrf})

    def delete(self,ix,path):
        return self.clients[ix].delete(path,base_url=HOST,headers={
            **ORIGIN,"X-Edge-Identity-CSRF":self.csrf[ix]})

    def test_two_devices_own_different_keys_no_legacy_access(self):
        target="/api/identity/public/connections"
        self.assertEqual(self.clients[0].get("/api/dashboard",base_url=HOST).status_code,401)
        self.assertEqual(self.clients[0].get("/api/broker/credentials/status",base_url=HOST).status_code,401)
        with self.appmod.app.test_client() as anonymous:
            self.assertEqual(anonymous.get(target,base_url=HOST).status_code,401)
        self.assertEqual(self.clients[0].post(target,base_url=HOST,headers=ORIGIN,
                                              json={"secret":KEY_A}).status_code,403)
        a=self.post(0,target,{"secret":KEY_A})
        b=self.post(1,target,{"secret":KEY_B})
        self.assertEqual(a.status_code,201,a.get_data(as_text=True))
        self.assertEqual(b.status_code,201,b.get_data(as_text=True))
        conn_a=a.get_json()["connectionId"]
        conn_b=b.get_json()["connectionId"]
        status_a=self.clients[0].get(target,base_url=HOST).get_json()
        status_b=self.clients[1].get(target,base_url=HOST).get_json()
        self.assertEqual([v["connectionId"] for v in status_a["connections"]],[conn_a])
        self.assertEqual([v["connectionId"] for v in status_b["connections"]],[conn_b])
        for data in (a.get_data(as_text=True),b.get_data(as_text=True),
                     str(status_a),str(status_b)):
            self.assertNotIn(KEY_A,data)
            self.assertNotIn(KEY_B,data)
        self.assertEqual(self.post(1,target+"/"+conn_a+"/rotate",{"secret":KEY_B}).status_code,404)
        self.assertEqual(self.delete(1,target+"/"+conn_a).status_code,404)
        self.assertEqual(self.post(0,target+"/"+conn_a+"/rotate",{"secret":KEY_A_NEW}).status_code,200)
        self.assertEqual(self.post(0,target+"/"+conn_a+"/rotate",{"secret":None}).status_code,404)
        self.assertEqual(self.delete(0,target+"/"+conn_a).status_code,200)
        self.assertEqual(self.delete(0,target+"/"+conn_a).status_code,404)
        self.assertEqual(self.clients[1].get(target,base_url=HOST).get_json()["connections"][0]["status"],
                         "stored_unverified")
        with sqlite3.connect(self.path) as db:
            legacy=db.execute("SELECT COUNT(*) FROM broker_credentials").fetchone()[0]
            self.assertEqual(legacy,0)

    def test_cross_origin_and_overposting_denied(self):
        target="/api/identity/public/connections"
        self.assertEqual(self.post(0,target,{"secret":KEY_A,"user_id":self.users[1]}).status_code,400)
        self.assertEqual(self.clients[0].post(target,base_url=HOST,
          headers={"Origin":"https://evil.example","X-Edge-Identity-CSRF":self.csrf[0]},
          json={"secret":KEY_A}).status_code,403)
        self.assertEqual(self.clients[0].get(target,base_url=HOST).get_json()["connections"],[])

    def test_feature_flag_default_off_has_no_access(self):
        self.assertTrue(self.appmod.tenant_public_vault_enabled)
        with self.appmod.app.test_client() as stranger:
            self.assertEqual(stranger.get("/api/identity/public/connections",base_url=HOST).status_code,401)
        root=(__import__("pathlib").Path(__file__).resolve().parents[2])
        app=(root/"backend/app.py").read_text()
        worker=(root/"backend/engine/automation_worker.py").read_text()
        result=tenant_route_audit.inspect_sources(app,worker)
        self.assertFalse(result["crossAccountProductionCutoverAllowed"])
        with self.assertRaises(tenant_route_audit.ApiBoundaryError):
            tenant_route_audit.inspect_sources(app+"\n_credential_for_provider_only()\n",worker)


if __name__=="__main__":
    unittest.main()
