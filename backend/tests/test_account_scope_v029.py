"""Phase 3: independently scoped tenant account reads, portfolio and workers.

No live market calls, legacy worker replacement, new-user enrollment or trading.
"""
import importlib
import os
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from engine import tenant_foundation, identity_auth, account_scope

ROOT=Path(__file__).resolve().parents[2]
STAMP=datetime.now(timezone.utc).isoformat()
W1="test-worker-owner-0123456789"
W2="test-worker-other-9876543210"
W3="test-worker-second-abc12345"


class TenantAccountScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=self.temp.name+"/scoped.db"
        with sqlite3.connect(self.path) as con:
            con.execute("CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT NOT NULL)")
            con.execute("INSERT INTO settings VALUES('account_id','LEGACY-DO-NOT-TOUCH')")
            con.execute("CREATE TABLE observation_cycles(id INTEGER PRIMARY KEY,note TEXT)")
            con.execute("INSERT INTO observation_cycles VALUES(7,'LEGACY-CYCLE')")
        tenant_foundation.setup(self.path)
        identity_auth.setup(self.path)
        account_scope.setup(self.path)
        self.tenant=tenant_foundation.TenantStore(self.path,credential_key=None)
        self.auth=identity_auth.IdentityStore(self.path)
        self.viewer=account_scope.AccountScopeStore(self.path,self.auth)
        self.worker=account_scope.DormantAccountWorkerStore(self.path)
        self.alice=self.tenant.provision_user("Alice","owner")
        self.bob=self.tenant.provision_user("Bob","member")
        self.auth.provision(self.alice,"alice_isolated","a-valid-test-password-1111")
        self.auth.provision(self.bob,"bob_isolated","a-valid-test-password-2222")
        self.alice_token=self.auth.authenticate("alice_isolated","a-valid-test-password-1111","a.example")["token"]
        self.bob_token=self.auth.authenticate("bob_isolated","a-valid-test-password-2222","b.example")["token"]
        from cryptography.fernet import Fernet
        self.fernet=Fernet.generate_key().decode()
        self.tenant=tenant_foundation.TenantStore(self.path,credential_key=self.fernet)
        self.alice_conn=self.tenant.add_connection(self.alice,"test-public-secret-for-Alice-01234567")
        self.bob_conn=self.tenant.add_connection(self.bob,"test-public-secret-for-Bob-0123456789")
        self.a1=self.tenant.link_account(self.alice,self.alice_conn,"PUBLIC-A1","Personal")
        self.a2=self.tenant.link_account(self.alice,self.alice_conn,"PUBLIC-A2","Second account")
        self.b1=self.tenant.link_account(self.bob,self.bob_conn,"PUBLIC-B1","Private")

    def tearDown(self):
        self.temp.cleanup()

    def test_all_accounts_lists_only_active_owned_accounts_without_broker_refs(self):
        a=self.viewer.list_accounts(self.alice_token)
        b=self.viewer.list_accounts(self.bob_token)
        self.assertEqual({x["account_id"] for x in a},{self.a1,self.a2})
        self.assertEqual({x["account_id"] for x in b},{self.b1})
        self.assertTrue(all("provider_account_ref" not in x and
                            "credential_ciphertext" not in x for x in a+b))
        self.assertNotIn("PUBLIC-A1",str(a))
        with self.assertRaises(account_scope.TenantAccessError):
            self.viewer.list_accounts("forged_identity_cookie")

    def test_scoped_portfolio_and_observation_independent_across_accounts(self):
        now=int(time.time())
        self.assertTrue(self.worker.claim_lease(self.alice,self.a1,W1,now=now))
        self.assertTrue(self.worker.claim_lease(self.alice,self.a2,W2,now=now))
        self.assertTrue(self.worker.claim_lease(self.bob,self.b1,W3,now=now))
        for uid,account,worker,total,symbol,accepted in (
            (self.alice,self.a1,W1,"111.01","SPY",1),
            (self.alice,self.a2,W2,"222.02","QQQ",2),
            (self.bob,self.b1,W3,"333.03","MSFT",3),
        ):
            self.worker.record_portfolio_snapshot(uid,account,worker,total_value=total,
                buying_power="50.00",provider_timestamp=STAMP,now=now)
            self.worker.record_observation(uid,account,worker,mode="observe",
                state="OK",symbols=[symbol],accepted=accepted,now=now)
        alice1=self.viewer.account_summary(self.alice_token,self.a1)
        alice2=self.viewer.account_summary(self.alice_token,self.a2)
        bob=self.viewer.account_summary(self.bob_token,self.b1)
        self.assertEqual(alice1["portfolio"]["account_value"],"111.01")
        self.assertEqual(alice2["portfolio"]["account_value"],"222.02")
        self.assertEqual(bob["portfolio"]["account_value"],"333.03")
        self.assertEqual(alice1["observation"]["symbols"],["SPY"])
        self.assertEqual(alice2["observation"]["symbols"],["QQQ"])
        self.assertEqual(bob["observation"]["symbols"],["MSFT"])
        self.assertEqual([alice1["last24h"]["accepted"],alice2["last24h"]["accepted"],
                          bob["last24h"]["accepted"]],[1,2,3])
        self.assertFalse(alice1["runtime"]["worker_enabled"])
        self.assertFalse(alice1["runtime"]["paper_enabled"])
        self.assertFalse(alice1["runtime"]["live_enabled"])
        self.assertTrue(alice1["readOnly"])
        self.assertFalse(alice1["providerRequestMade"])
        for uid,acct in ((self.bob_token,self.a1),(self.alice_token,self.b1),
                         (self.bob_token,"nonexistent")):
            with self.assertRaises(account_scope.TenantAccessError):
                self.viewer.account_summary(uid,acct)
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute("SELECT v FROM settings WHERE k='account_id'").fetchone()[0],
                            "LEGACY-DO-NOT-TOUCH")
            self.assertEqual(con.execute("SELECT note FROM observation_cycles WHERE id=7").fetchone()[0],
                            "LEGACY-CYCLE")

    def test_individual_account_lease_prevents_competing_worker_and_cross_write(self):
        now=int(time.time())
        self.assertTrue(self.worker.claim_lease(self.alice,self.a1,W1,now=now,ttl=120))
        self.assertFalse(self.worker.claim_lease(self.alice,self.a1,W2,now=now+10,ttl=120))
        self.assertTrue(self.worker.claim_lease(self.alice,self.a2,W2,now=now+10,ttl=120))
        self.assertTrue(self.worker.claim_lease(self.bob,self.b1,W3,now=now+10,ttl=120))
        with self.assertRaises(account_scope.TenantAccessError):
            self.worker.record_observation(self.alice,self.a1,W2,mode="observe",
                                           state="OK",symbols=["SPY"],now=now+10)
        with self.assertRaises(account_scope.TenantAccessError):
            self.worker.record_portfolio_snapshot(self.alice,self.a1,W3,total_value="1.00",
                    buying_power="1.00",provider_timestamp=STAMP,now=now+10)
        with self.assertRaises(account_scope.TenantAccessError):
            self.worker.record_observation(self.bob,self.a1,W3,mode="observe",
                                           state="OK",now=now+10)
        with self.assertRaises(account_scope.TenantAccessError):
            self.worker.claim_lease(self.bob,self.a1,W3,now=now+10)
        self.assertFalse(self.worker.release_lease(self.alice,self.a1,W2))
        self.assertTrue(self.worker.claim_lease(self.alice,self.a1,W2,now=now+121))
        self.assertTrue(self.worker.release_lease(self.alice,self.a1,W2))
        self.assertTrue(self.worker.claim_lease(self.alice,self.a1,W1,now=now+122))

    def test_revoked_connection_disabled_user_and_disabled_account_all_denied(self):
        with sqlite3.connect(self.path) as con:
            con.execute("UPDATE tenant_connections SET revoked_at=? WHERE connection_id=?",
                        (STAMP,self.alice_conn))
        self.assertEqual(self.viewer.list_accounts(self.alice_token),[])
        with self.assertRaises(account_scope.TenantAccessError):
            self.viewer.account_summary(self.alice_token,self.a1)
        with self.assertRaises(account_scope.TenantAccessError):
            self.worker.claim_lease(self.alice,self.a1,W1)
        with sqlite3.connect(self.path) as con:
            con.execute("UPDATE tenant_accounts SET disabled_at=? WHERE account_id=?",(STAMP,self.b1))
        self.assertEqual(self.viewer.list_accounts(self.bob_token),[])
        with self.assertRaises(account_scope.TenantAccessError):
            self.worker.claim_lease(self.bob,self.b1,W3)
        with sqlite3.connect(self.path) as con:
            con.execute("UPDATE tenant_users SET disabled_at=? WHERE user_id=?",(STAMP,self.bob))
        with self.assertRaises(account_scope.TenantAccessError):
            self.viewer.list_accounts(self.bob_token)

    def test_strict_validation_and_fail_closed(self):
        now=int(time.time())
        self.worker.claim_lease(self.alice,self.a1,W1,now=now)
        for bad in (True,-1,"NaN","Infinity","-0.50",None,"1e9999"):
            with self.assertRaises(ValueError):
                self.worker.record_portfolio_snapshot(self.alice,self.a1,W1,
                    total_value=bad,buying_power="1",provider_timestamp=STAMP,now=now)
        with self.assertRaises(ValueError):
            self.worker.record_portfolio_snapshot(self.alice,self.a1,W1,
                total_value=1,buying_power=1,provider_timestamp="not-a-date",now=now)
        with self.assertRaises(ValueError):
            self.worker.record_observation(self.alice,self.a1,W1,mode="live",
                                           state="OK",symbols=["SPY"],now=now)
        with self.assertRaises(ValueError):
            self.worker.record_observation(self.alice,self.a1,W1,mode="observe",
                                           state="OK",symbols=["SPY/INJECT"],now=now)
        with self.assertRaises(ValueError):
            self.worker.record_observation(self.alice,self.a1,W1,mode="observe",
                                           state="OK",accepted=True,now=now)
        with self.assertRaises(ValueError):
            self.worker.claim_lease(self.alice,self.a1,"weak-id",now=now,ttl=120)
        with self.assertRaises(account_scope.TenantAccessError):
            self.viewer.account_summary("invalid-cookie",self.a1)

    def test_schema_is_idempotent_and_does_not_initialize_worker(self):
        account_scope.setup(self.path)
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tenant_worker_leases").fetchone()[0],0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tenant_runtime_status").fetchone()[0],0)
        source=(ROOT/"backend/app.py").read_text()
        self.assertIn("EDGE_TENANT_ACCOUNT_READS_ENABLED",source)
        self.assertIn("os.getenv('EDGE_TENANT_ACCOUNT_READS_ENABLED','false').lower()=='true'",source)
        self.assertIn("'liveTradingAvailable':False",source)
        worker=(ROOT/"backend/engine/automation_worker.py").read_text()
        self.assertNotIn("DormantAccountWorkerStore",worker)


class ScopedHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{
            "EDGE_DB_PATH":self.temp.name+"/site.db",
            "EDGE_TENANT_SCHEMA_PREPARE":"true",
            "EDGE_IDENTITY_AUTH_ENABLED":"true",
            "EDGE_TENANT_ACCOUNT_READS_ENABLED":"true",
            "EDGE_APP_TOKEN":"legacy-owner-secret-0123456789-XYZ0123456",
            "PUBLIC_API_SECRET":"",
            "EDGE_AUTOMATION_WORKER_ENABLED":"false",
        })
        self.env.start()
        import app
        self.mod=importlib.reload(app)
        self.base="https://edgepilot.example.test"
        self.origin={"Origin":self.base}
        self.tenant=tenant_foundation.TenantStore(str(self.mod.DB),credential_key=
                 __import__("cryptography.fernet",fromlist=["Fernet"]).Fernet.generate_key().decode())
        self.a=self.tenant.provision_user("Alice")
        self.b=self.tenant.provision_user("Bob")
        self.mod.identity_store.provision(self.a,"phase3_alice","strong-password-for-alice-2026")
        self.mod.identity_store.provision(self.b,"phase3_bob","strong-password-for-bob-2026")
        con_a=self.tenant.add_connection(self.a,"alice-public-secret-01234567890")
        con_b=self.tenant.add_connection(self.b,"bob-public-secret-01234567890")
        self.a1=self.tenant.link_account(self.a,con_a,"BROKER-ID-A","First")
        self.a2=self.tenant.link_account(self.a,con_a,"BROKER-ID-A2","Second")
        self.b1=self.tenant.link_account(self.b,con_b,"BROKER-ID-B","Private")

    def tearDown(self):
        self.env.stop()
        import app
        importlib.reload(app)
        self.temp.cleanup()

    def login(self,name):
        client=self.mod.app.test_client()
        login=client.post("/api/identity/login",base_url=self.base,headers=self.origin,
            json={"username":name,"password":"strong-password-for-"+name.split("_")[1]+"-2026"})
        self.assertEqual(login.status_code,200)
        return client

    def test_account_reads_authorize_session_owner_and_never_call_public(self):
        a=self.login("phase3_alice")
        b=self.login("phase3_bob")
        a_list=a.get("/api/identity/accounts",base_url=self.base)
        b_list=b.get("/api/identity/accounts",base_url=self.base)
        self.assertEqual(a_list.status_code,200)
        self.assertEqual({x["account_id"] for x in a_list.get_json()["accounts"]},
                         {self.a1,self.a2})
        self.assertEqual({x["account_id"] for x in b_list.get_json()["accounts"]},
                         {self.b1})
        self.assertNotIn("BROKER-ID-A",a_list.get_data(as_text=True))
        self.assertEqual(a.get("/api/identity/accounts/"+self.a1+"/summary",
                               base_url=self.base).status_code,200)
        self.assertEqual(b.get("/api/identity/accounts/"+self.a1+"/summary",
                               base_url=self.base).status_code,404)
        self.assertEqual(a.get("/api/identity/accounts/"+self.b1+"/summary",
                               base_url=self.base).status_code,404)
        self.assertEqual(a.get("/api/identity/accounts/forged/summary",
                               base_url=self.base).status_code,404)
        self.assertEqual(a.get("/api/dashboard",base_url=self.base).status_code,401)
        self.assertEqual(a.get("/api/automation/status",base_url=self.base).status_code,401)

    def test_unowned_path_cannot_change_data_and_no_tenant_write_api(self):
        a=self.login("phase3_alice")
        self.assertEqual(a.post("/api/identity/accounts/"+self.b1+"/summary",base_url=self.base,
                headers=self.origin,json={"user_id":self.b,"worker_enabled":1}).status_code,403)
        self.assertEqual(a.get("/api/identity/accounts/"+self.b1+"/summary",
                               base_url=self.base).status_code,404)
        self.assertNotIn("BROKER-ID-B",a.get("/api/identity/accounts",base_url=self.base).get_data(as_text=True))
        self.assertEqual(a.get("/api/identity/accounts/"+self.a1+"/summary",
                               base_url=self.base).get_json()["runtime"]["live_enabled"],0)


class ScopedDefaultOffTests(unittest.TestCase):
    def test_disabled_independently_even_with_identity_enabled(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{
            "EDGE_DB_PATH":temp+"/disabled.db",
            "EDGE_TENANT_SCHEMA_PREPARE":"true",
            "EDGE_IDENTITY_AUTH_ENABLED":"true",
            "EDGE_TENANT_ACCOUNT_READS_ENABLED":"false",
            "EDGE_AUTOMATION_WORKER_ENABLED":"false",
        }):
            import app
            importlib.reload(app)
            client=app.app.test_client()
            for url in ("/api/identity/accounts","/api/identity/accounts/fake/summary"):
                self.assertEqual(client.get(url,base_url="https://edgepilot.example.test").status_code,404)
            with sqlite3.connect(temp+"/disabled.db") as con:
                self.assertFalse(con.execute("""SELECT name FROM sqlite_master
                    WHERE name='tenant_worker_leases' AND type='table'""").fetchone())
        import app
        importlib.reload(app)


if __name__=="__main__":
    unittest.main()
