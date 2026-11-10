"""v0.2.17: explicit dormant API request and worker boundary regression tests."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet

from engine import (
    account_scope, identity_auth, tenant_api_gateway, tenant_foundation,
    tenant_history, tenant_history_details, tenant_monitor_blueprint,
    tenant_request_boundary, tenant_worker_boundary, tenant_route_audit,
)

ROOT=Path(__file__).resolve().parents[2]
REQ=tenant_request_boundary.DormantRequest


class DormantBoundariesTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir="/dev/shm")
        self.path=Path(self.temp.name)/"two-owner-fixture.db"
        tenant_foundation.setup(str(self.path))
        identity_auth.setup(str(self.path))
        account_scope.setup(str(self.path))
        tenant_api_gateway.setup(str(self.path))
        with account_scope._db(self.path) as con:
            tenant_history.prepare(con)
            tenant_history_details.prepare(con)
            con.execute("CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT)")
            con.execute("INSERT INTO settings VALUES('account_id','LEGACY-ORIGINAL')")
        self.store=tenant_foundation.TenantStore(self.path,
            credential_key=Fernet.generate_key().decode())
        self.owner=self.store.provision_user("Owner A","owner")
        self.other=self.store.provision_user("Owner B","owner")
        self.conn_a=self.store.add_connection(self.owner,
            "synthetic-fake-credential-owner-a-abcdef")
        self.conn_b=self.store.add_connection(self.other,
            "synthetic-fake-credential-owner-b-abcdef")
        self.a=self.store.link_account(self.owner,self.conn_a,"OWNER-A-ONE","A One")
        self.a2=self.store.link_account(self.owner,self.conn_a,"OWNER-A-TWO","A Two")
        self.b=self.store.link_account(self.other,self.conn_b,"OWNER-B-ONE","B One")
        self.auth=identity_auth.IdentityStore(str(self.path))
        self.auth.provision(self.owner,"owner_a","test-correct-horse-battery-staple-a")
        self.auth.provision(self.other,"owner_b","test-correct-horse-battery-staple-b")
        self.phone1=self.auth.authenticate(
            "owner_a","test-correct-horse-battery-staple-a","android-1")
        self.phone2=self.auth.authenticate(
            "owner_a","test-correct-horse-battery-staple-a","android-2")
        self.phoneb=self.auth.authenticate(
            "owner_b","test-correct-horse-battery-staple-b","android-3")
        self.gateway=tenant_api_gateway.DormantAccountGateway(self.path,self.auth)
        self.boundary=tenant_request_boundary.DormantRequestBoundary(self.gateway)
        self.planner=tenant_monitor_blueprint.DormantAccountMonitorPlanner(self.path)
        self.worker=tenant_worker_boundary.DormantWorkerBoundary(self.planner)

    def tearDown(self):
        self.temp.cleanup()

    def legacy(self):
        with sqlite3.connect(self.path) as con:
            return con.execute(
                "SELECT v FROM settings WHERE k='account_id'").fetchone()[0]

    def test_canonical_account_reads_no_owner_ids_and_two_phone_choices(self):
        p1,p2,pb=self.phone1,self.phone2,self.phoneb
        for session,account in ((p1,self.a),(p2,self.a2),(pb,self.b)):
            response=self.boundary.dispatch(REQ("POST","/tenant/selected",
                session["token"],csrf=session["csrf"],payload={"account_id":account}))
            self.assertTrue(response["selectionIsSessionOnly"])
        for session,expected in ((p1,self.a),(p2,self.a2),(pb,self.b)):
            current=self.boundary.dispatch(REQ("GET","/tenant/selected",session["token"]))
            self.assertEqual(current["selectedAccountId"],expected)
            summary=self.boundary.dispatch(REQ("GET",f"/tenant/accounts/{expected}/summary",
                                             session["token"]))
            self.assertEqual(summary["account"]["id"],expected)
            self.assertFalse(summary["providerRequestMade"])
            records=self.boundary.dispatch(REQ("GET",
                f"/tenant/accounts/{expected}/references",session["token"],
                params={"limit":5}))
            self.assertEqual(records["items"],[])
            self.assertFalse(records["canTrade"])
        accounts=self.boundary.dispatch(REQ("GET","/tenant/accounts",p1["token"]))
        self.assertEqual({r["account_id"] for r in accounts["accounts"]},
                         {self.a,self.a2})
        self.assertEqual(self.legacy(),"LEGACY-ORIGINAL")

    def test_cross_user_and_wrong_session_token_denied(self):
        for session,target in ((self.phone1,self.b),
                               (self.phoneb,self.a),
                               (self.phoneb,self.a2)):
            for route in ("summary","history","details","references"):
                with self.subTest(route=route,target=target):
                    with self.assertRaises(tenant_foundation.TenantAccessError):
                        self.boundary.dispatch(REQ("GET",
                            f"/tenant/accounts/{target}/{route}",session["token"]))
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.boundary.dispatch(REQ("POST","/tenant/selected",
                self.phoneb["token"],csrf=self.phoneb["csrf"],
                payload={"account_id":self.a}))
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.boundary.dispatch(REQ("GET","/tenant/accounts","not-a-real-token"))
        self.assertEqual(self.legacy(),"LEGACY-ORIGINAL")

    def test_strict_http_method_canonical_path_payload_and_query_contract(self):
        token=self.phone1["token"]
        invalid=[
            REQ("POST","/tenant/orders",token,payload={"side":"BUY"}),
            REQ("POST","/tenant/accounts",token),
            REQ("PUT","/tenant/selected",token),
            REQ("GET","/tenant/accounts/../summary",token),
            REQ("GET",f"/tenant/accounts/{self.a.upper()}/summary",token),
            REQ("GET",f"/tenant/accounts/{self.a}/summary?user_id=other",token),
            REQ("GET",f"/tenant/accounts/{self.a}/%73ummary",token),
            REQ("GET",f"/tenant/accounts/{self.a}//summary",token),
            REQ("POST","/tenant/selected",token,csrf=self.phone1["csrf"],
                payload={"account_id":self.a,"user_id":self.other}),
            REQ("POST","/tenant/selected",token,csrf=self.phone1["csrf"],
                payload={"account_id":self.a,"live":True}),
            REQ("GET",f"/tenant/accounts/{self.a}/references",token,
                params={"user_id":self.other}),
            REQ("GET",f"/tenant/accounts/{self.a}/summary",token,
                params={"limit":5}),
        ]
        for request in invalid:
            with self.subTest(route=request.path):
                with self.assertRaises(tenant_request_boundary.TenantRequestDenied):
                    self.boundary.dispatch(request)
        for method in (self.boundary.submit_order,self.boundary.transfer_funds):
            with self.assertRaises(tenant_request_boundary.TenantRequestDenied):
                method()
        self.assertEqual(self.legacy(),"LEGACY-ORIGINAL")

    def test_csrf_revocation_and_disabled_account_fail_closed(self):
        p1,p2=self.phone1,self.phone2
        for bad in (None,"fake",self.phoneb["csrf"]):
            with self.assertRaises(tenant_foundation.TenantAccessError):
                self.boundary.dispatch(REQ("POST","/tenant/selected",p1["token"],
                    csrf=bad,payload={"account_id":self.a}))
        self.boundary.dispatch(REQ("POST","/tenant/selected",p1["token"],
            csrf=p1["csrf"],payload={"account_id":self.a}))
        self.boundary.dispatch(REQ("POST","/tenant/selected",p2["token"],
            csrf=p2["csrf"],payload={"account_id":self.a2}))
        self.boundary.dispatch(REQ("DELETE","/tenant/selected",p1["token"],
            csrf=p1["csrf"]))
        self.assertIsNone(self.boundary.dispatch(REQ("GET","/tenant/selected",
            p1["token"]))["selectedAccountId"])
        self.assertEqual(self.boundary.dispatch(REQ("GET","/tenant/selected",
            p2["token"]))["selectedAccountId"],self.a2)
        with account_scope._db(self.path) as con:
            con.execute("UPDATE tenant_connections SET revoked_at='2026-11-09' WHERE connection_id=?",
                        (self.conn_a,))
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.boundary.dispatch(REQ("GET","/tenant/selected",p2["token"]))
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.boundary.dispatch(REQ("GET",f"/tenant/accounts/{self.a2}/summary",
                p2["token"]))
        self.auth.revoke(p2["token"])
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.boundary.dispatch(REQ("GET","/tenant/accounts",p2["token"]))

    def test_fair_worker_admission_caps_and_isolation(self):
        self.store.account_setting(self.owner,self.a,"watchlist_csv","SPY,QQQ")
        self.store.account_setting(self.owner,self.a2,"watchlist_csv","IWM")
        self.store.account_setting(self.other,self.b,"watchlist_csv","MSFT")
        admitted=self.worker.admission(maximum_accounts=2,per_owner_limit=2)
        self.assertEqual(admitted.total_accounts,3)
        self.assertEqual(admitted.deferred_accounts,1)
        self.assertEqual(len(admitted.slots),2)
        self.assertEqual({s.blueprint.user_id for s in admitted.slots},
                         {self.owner,self.other})
        self.assertFalse(admitted.can_activate)
        self.assertEqual(admitted.external_calls_permitted,0)
        for slot in admitted.slots:
            self.assertTrue(self.worker.revalidate(slot))
            self.assertFalse(slot.scheduled)
            self.assertFalse(slot.authorized_to_fetch_quotes)
            self.assertFalse(slot.allowed_to_trade)
        for invalid in ({"maximum_accounts":0},{"maximum_accounts":True},
                        {"per_owner_limit":0},{"per_owner_limit":100}):
            with self.assertRaises(tenant_worker_boundary.WorkerBoundaryDenied):
                self.worker.admission(**invalid)
        for op in (self.worker.enqueue,self.worker.start,
                   self.worker.submit_order):
            with self.assertRaises(tenant_worker_boundary.WorkerBoundaryDenied):
                op()
        self.assertEqual(self.legacy(),"LEGACY-ORIGINAL")

    def test_recheck_during_offline_replay_cannot_cross_account_or_revoked_connection(self):
        self.store.account_setting(self.owner,self.a,"watchlist_csv","SPY")
        slot=next(s for s in self.worker.admission().slots
                  if s.blueprint.account_id==self.a)
        with self.assertRaises(tenant_monitor_blueprint.MonitorPlanningError):
            self.worker.synthetic_replay(slot,"synthetic-worker-0001",approval="wrong")
        report=self.worker.synthetic_replay(slot,"synthetic-worker-0001",
            approval="SYNTHETIC ACCOUNT OBSERVATION ONLY")
        self.assertTrue(report["offlineSyntheticRecordCreated"])
        self.assertFalse(report["publicQuoteApiCalled"])
        summary=self.gateway.account_summary(self.phone1["token"],self.a)
        other=self.gateway.account_summary(self.phoneb["token"],self.b)
        self.assertEqual(summary["last24h"]["cycles"],1)
        self.assertEqual(other["last24h"]["cycles"],0)
        self.store.account_setting(self.owner,self.a,"watchlist_csv","AAPL")
        with self.assertRaises(tenant_worker_boundary.WorkerBoundaryDenied):
            self.worker.revalidate(slot)
        with account_scope._db(self.path) as con:
            con.execute("UPDATE tenant_connections SET revoked_at='2026-11-09' WHERE connection_id=?",
                        (self.conn_a,))
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.worker.revalidate(slot)
        self.assertEqual(self.legacy(),"LEGACY-ORIGINAL")

    def test_accidental_live_wiring_still_blocked(self):
        app=(ROOT/"backend/app.py").read_text()
        worker=(ROOT/"backend/engine/automation_worker.py").read_text()
        audit=tenant_route_audit.inspect_sources(app,worker)
        self.assertFalse(audit["crossAccountProductionCutoverAllowed"])
        for mod in ("tenant_request_boundary","tenant_worker_boundary"):
            self.assertNotIn(mod,app)
            self.assertNotIn(mod,worker)
            with self.assertRaises(tenant_route_audit.ApiBoundaryError):
                tenant_route_audit.inspect_sources(app+"\nfrom engine import "+mod+"\n",worker)
            with self.assertRaises(tenant_route_audit.ApiBoundaryError):
                tenant_route_audit.inspect_sources(app,worker+"\nfrom engine import "+mod+"\n")


if __name__=="__main__":
    unittest.main()
