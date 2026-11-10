"""v0.2.18 real test-client HTTP and synthetic multi-account orchestration.

Real Flask handlers, but ONLY created from a verified /dev/shm fixture with an
explicit safety gate. Never run against a production database or server.
"""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

from engine import (
    account_scope,identity_auth,tenant_api_gateway,tenant_foundation,
    tenant_history,tenant_history_details,tenant_monitor_blueprint,
    tenant_worker_boundary,tenant_test_http,tenant_test_orchestrator,
    tenant_route_audit,
)

ORIGIN=tenant_test_http.TEST_ORIGIN
COOKIE=identity_auth.COOKIE_NAME
ROOT=Path(__file__).resolve().parents[2]


class IsolatedFlaskAndOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir="/dev/shm")
        self.path=Path(self.temp.name)/"synthetic-readonly.db"
        tenant_foundation.setup(str(self.path))
        identity_auth.setup(str(self.path))
        account_scope.setup(str(self.path))
        tenant_api_gateway.setup(str(self.path))
        with account_scope._db(self.path) as con:
            tenant_history.prepare(con)
            tenant_history_details.prepare(con)
            con.execute("CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT)")
            con.execute("INSERT INTO settings VALUES('account_id','KEEP-LEGACY-ALONE')")
        self.store=tenant_foundation.TenantStore(
            self.path,credential_key=Fernet.generate_key().decode())
        self.owner=self.store.provision_user("Owner A","owner")
        self.other=self.store.provision_user("Owner B","owner")
        self.conna=self.store.add_connection(
            self.owner,"SYNTHETIC-NO-REAL-PUBLIC-CREDENTIAL-OWNER-A")
        self.connb=self.store.add_connection(
            self.other,"SYNTHETIC-NO-REAL-PUBLIC-CREDENTIAL-OWNER-B")
        self.a1=self.store.link_account(self.owner,self.conna,"FAKE-A1","Alpha 1")
        self.a2=self.store.link_account(self.owner,self.conna,"FAKE-A2","Alpha 2")
        self.b1=self.store.link_account(self.other,self.connb,"FAKE-B1","Beta 1")
        self.auth=identity_auth.IdentityStore(str(self.path))
        self.auth.provision(self.owner,"alpha","alpha-test-passphrase-at-least-14")
        self.auth.provision(self.other,"beta","beta-test-passphrase-at-least-14")
        self.p1=self.auth.authenticate(
            "alpha","alpha-test-passphrase-at-least-14","synthetic-phone-1")
        self.p2=self.auth.authenticate(
            "alpha","alpha-test-passphrase-at-least-14","synthetic-phone-2")
        self.pb=self.auth.authenticate(
            "beta","beta-test-passphrase-at-least-14","synthetic-phone-b")
        self.gate=patch.dict(os.environ,{tenant_test_http.TEST_GATE:"true"})
        self.gate.start()
        self.app=tenant_test_http.create_isolated_test_app(self.path,self.auth)
        self.p1_client=self._client(self.p1)
        self.p2_client=self._client(self.p2)
        self.b_client=self._client(self.pb)
        self.anon=self.app.test_client()
        self.planner=tenant_monitor_blueprint.DormantAccountMonitorPlanner(self.path)
        self.worker=tenant_worker_boundary.DormantWorkerBoundary(self.planner)
        self.orchestrator=tenant_test_orchestrator.OfflineTenantOrchestrator(self.worker)

    def tearDown(self):
        self.gate.stop()
        self.temp.cleanup()

    def _client(self,session):
        client=self.app.test_client()
        client.set_cookie(COOKIE,session["token"],
                          domain="edgepilot-test.invalid",
                          secure=True,httponly=True,path="/",samesite="Strict")
        return client

    def get(self,client,path,**kwargs):
        return client.get(path,base_url=ORIGIN,**kwargs)

    def post(self,client,path,body,csrf,origin=ORIGIN,**kwargs):
        hdr={"Origin":origin,"X-Edge-Identity-CSRF":csrf,"Sec-Fetch-Site":"same-origin"}
        return client.post(path,base_url=ORIGIN,json=body,headers=hdr,**kwargs)

    def delete(self,client,path,csrf):
        return client.delete(path,base_url=ORIGIN,headers={
            "Origin":ORIGIN,"X-Edge-Identity-CSRF":csrf})

    def legacy(self):
        with sqlite3.connect(self.path) as conn:
            return conn.execute("SELECT v FROM settings WHERE k='account_id'").fetchone()[0]

    def test_factory_is_locked_to_memory_fixture_and_gate(self):
        self.gate.stop()
        with self.assertRaises(tenant_test_http.TestHttpUnavailable):
            tenant_test_http.create_isolated_test_app(self.path,self.auth)
        self.gate.start()
        with self.assertRaises(tenant_test_http.TestHttpUnavailable):
            tenant_test_http.create_isolated_test_app(
                self.path,self.auth,origin="https://wrong.invalid")
        with tempfile.TemporaryDirectory() as ordinary:
            p=Path(ordinary)/"normal.sqlite"
            p.write_bytes(self.path.read_bytes())
            with self.assertRaises(Exception):
                tenant_test_http.create_isolated_test_app(p,self.auth)

    def test_three_real_flask_clients_select_independent_accounts(self):
        for client,session,account in (
            (self.p1_client,self.p1,self.a1),
            (self.p2_client,self.p2,self.a2),
            (self.b_client,self.pb,self.b1)
        ):
            r=self.post(client,"/tenant/selected",
                        {"account_id":account},session["csrf"])
            self.assertEqual(r.status_code,200)
            self.assertEqual(r.json["selectedAccountId"],account)
        for client,account in (
            (self.p1_client,self.a1),(self.p2_client,self.a2),
            (self.b_client,self.b1)
        ):
            self.assertEqual(self.get(client,"/tenant/selected").json["selectedAccountId"],account)
            result=self.get(client,f"/tenant/accounts/{account}/summary")
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.json["account"]["id"],account)
            self.assertFalse(result.json["providerRequestMade"])
            for route in ("history","details","references"):
                resp=self.get(client,f"/tenant/accounts/{account}/{route}")
                self.assertEqual(resp.status_code,200,route)
                self.assertEqual(resp.headers["Cache-Control"],"no-store")
                self.assertNotIn("Access-Control-Allow-Origin",resp.headers)
                self.assertEqual(resp.headers["X-Frame-Options"],"DENY")
        self.assertEqual(self.legacy(),"KEEP-LEGACY-ALONE")

    def test_untrusted_http_does_not_get_broker_or_other_owner_data(self):
        self.assertEqual(self.get(self.anon,"/tenant/accounts").status_code,401)
        self.assertEqual(self.get(self.p1_client,"/tenant/accounts").status_code,200)
        bads=((self.p1_client,self.b1),(self.b_client,self.a1),(self.b_client,self.a2))
        for client,account in bads:
            for view in ("summary","history","details","references"):
                r=self.get(client,f"/tenant/accounts/{account}/{view}")
                self.assertEqual(r.status_code,404,(account,view))
                self.assertNotIn("Beta",r.get_data(as_text=True))
        self.assertEqual(self.get(self.anon,"/tenant/accounts",
            headers={"Authorization":"Bearer "+self.p1["token"]}).status_code,401)
        self.assertEqual(self.post(self.b_client,"/tenant/selected",
            {"account_id":self.a1},self.pb["csrf"]).status_code,404)
        for path in ("/tenant/orders","/api/order/submit","/tenant/funds",
                     "/tenant/engines/activate"):
            self.assertNotEqual(self.get(self.p1_client,path).status_code,200)

    def test_http_origin_csrf_cookie_and_payload_restrictions(self):
        self.assertEqual(self.get(self.p1_client,"/tenant/accounts",
            base_url="http://edgepilot-test.invalid").status_code,403)
        self.assertEqual(self.get(self.p1_client,"/tenant/accounts",
            base_url="https://other.invalid").status_code,403)
        self.assertEqual(self.post(self.p1_client,"/tenant/selected",
            {"account_id":self.a1},self.p1["csrf"],origin="https://evil.invalid").status_code,403)
        self.assertEqual(self.post(self.p1_client,"/tenant/selected",
            {"account_id":self.a1},"wrong-csrf").status_code,404)
        self.assertEqual(self.post(self.p1_client,"/tenant/selected",
            {"account_id":self.a1,"user_id":self.other},
            self.p1["csrf"]).status_code,400)
        self.assertEqual(self.post(self.p1_client,"/tenant/selected",
            {"account_id":self.a1,"can_trade":True},
            self.p1["csrf"]).status_code,400)
        invalid=self.p1_client.post("/tenant/selected",base_url=ORIGIN,
            data="a"*5000,headers={"Origin":ORIGIN,"X-Edge-Identity-CSRF":self.p1["csrf"],
                                   "Content-Type":"application/json"})
        self.assertEqual(invalid.status_code,413)
        self.assertEqual(self.get(self.p1_client,"/tenant/selected").json["selectedAccountId"],None)
        self.post(self.p1_client,"/tenant/selected",{"account_id":self.a1},self.p1["csrf"])
        self.post(self.p2_client,"/tenant/selected",{"account_id":self.a2},self.p2["csrf"])
        self.assertEqual(self.delete(self.p1_client,"/tenant/selected",self.p1["csrf"]).status_code,200)
        self.assertIsNone(self.get(self.p1_client,"/tenant/selected").json["selectedAccountId"])
        self.assertEqual(self.get(self.p2_client,"/tenant/selected").json["selectedAccountId"],self.a2)

    def test_http_denies_encoded_paths_duplicate_query_and_stale_session(self):
        for p in (
            f"/tenant/accounts/{self.a1}/summary?user_id={self.other}",
            f"/tenant/accounts/{self.a1}/references?limit=5&limit=10",
            f"/tenant/accounts/{self.a1}/%73ummary",
            f"/tenant/accounts/{self.a1.upper()}/summary",
            f"/tenant/accounts/{self.a1}/references?before_id=not-a-number",
            f"/tenant/accounts/{self.a1}/references?limit=-1"
        ):
            self.assertNotEqual(self.get(self.p1_client,p).status_code,200,p)
        self.auth.revoke(self.p1["token"])
        self.assertEqual(self.get(self.p1_client,"/tenant/accounts").status_code,401)
        self.assertEqual(self.get(self.p2_client,"/tenant/accounts").status_code,200)

    def test_synthetic_batch_fairness_and_stale_account_failure_isolation(self):
        self.store.account_setting(self.owner,self.a1,"watchlist_csv","SPY,QQQ")
        self.store.account_setting(self.owner,self.a2,"watchlist_csv","IWM")
        self.store.account_setting(self.other,self.b1,"watchlist_csv","MSFT")
        plan=self.orchestrator.plan(account_cap=2,owner_cap=2)
        self.assertEqual(plan.total_accounts,3)
        self.assertEqual(plan.deferred_accounts,1)
        self.assertEqual({slot.blueprint.user_id for slot in plan.slots},
                         {self.owner,self.other})
        with self.assertRaises(tenant_test_orchestrator.OfflineOrchestrationDenied):
            self.orchestrator.replay_once(plan,approval="no")
        success=self.orchestrator.replay_once(plan,approval=tenant_test_orchestrator.APPROVAL)
        self.assertEqual((success.examined,success.completed,success.rejected,success.deferred),
                         (2,2,0,1))
        self.assertEqual(success.real_provider_calls,0)
        self.assertEqual(success.external_orders,0)
        self.assertFalse(success.worker_activated)
        with account_scope._db(self.path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tenant_observation_cycles").fetchone()[0],2)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tenant_worker_leases").fetchone()[0],0)
        plan2=self.orchestrator.plan(account_cap=3,owner_cap=2)
        # Revoke only owner A after planning; owner B still succeeds.
        with account_scope._db(self.path) as con:
            con.execute("UPDATE tenant_connections SET revoked_at='2026-11-09' WHERE connection_id=?",
                        (self.conna,))
        outcome=self.orchestrator.replay_once(plan2,approval=tenant_test_orchestrator.APPROVAL)
        self.assertEqual((outcome.examined,outcome.completed,outcome.rejected),(3,1,2))
        self.assertEqual(self.legacy(),"KEEP-LEGACY-ALONE")

    def test_live_http_and_worker_imports_remain_absent(self):
        app=(ROOT/"backend/app.py").read_text()
        worker=(ROOT/"backend/engine/automation_worker.py").read_text()
        for module in ("tenant_test_http","tenant_test_orchestrator"):
            self.assertNotIn(module,app)
            self.assertNotIn(module,worker)
        report=tenant_route_audit.inspect_sources(app,worker)
        self.assertFalse(report["crossAccountProductionCutoverAllowed"])
        self.assertFalse(report["tenantTestHttpMountedOnProduction"])
        self.assertFalse(report["tenantBatchOrchestratorActivated"])


if __name__=="__main__":
    unittest.main()
