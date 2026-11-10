"""v0.2.21: hardened dormant HTTPS Public adapter, synthetic sockets only.

All account refs and credentials are synthetic. No Public network calls,
production database changes, user enrollment, broker operations or trades.
"""
from __future__ import annotations

import json
import sqlite3
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from engine import (
    account_scope, identity_auth, tenant_api_gateway, tenant_foundation,
    tenant_history, tenant_history_details,
    tenant_public_https_wire as wire, tenant_public_access_controller as budget,
    tenant_public_https_account_adapter as adapter, tenant_route_audit,
)

ROOT=Path(__file__).resolve().parents[2]


class FakeReply:
    def __init__(self,payload,status=200,*,content_type="application/json",
                 encoding="identity",declared_length=None):
        self.status=status
        self._raw=(payload if isinstance(payload,bytes)
                   else json.dumps(payload).encode("utf-8"))
        self._headers={"Content-Type":content_type,"Content-Encoding":encoding}
        if declared_length is not None:
            self._headers["Content-Length"]=declared_length
    def getheader(self,name,default=None):
        return self._headers.get(name,default)
    def read(self,n):
        return self._raw[:n]


class FakeConnection:
    edgepilot_fake_public_connection=True
    def __init__(self,response,record):
        self.response=response
        self.record=record
        self.closed=False
    def request(self,method,path,body=None,headers=None):
        # Only synthetic bytes are stored in this private test fixture.
        self.record.append((method,path,body,dict(headers)))
    def getresponse(self):
        return self.response
    def close(self):
        self.closed=True


class FakeFactory:
    def __init__(self,token="SYNTHETIC-TOKEN-TEST",accounts=None):
        self.token=token
        self.accounts=accounts or ["PUBLIC-A-ONE","PUBLIC-A-TWO"]
        self.status={"POST":200,"GET":200}
        self.content_type={"POST":"application/json","GET":"application/json"}
        self.encoding={"POST":"identity","GET":"identity"}
        self.declared_length={}
        self.raw={}
        self.calls=[]
        self.hook=None
    def __call__(self,method):
        if self.hook:
            self.hook(method)
        payload=({"accessToken":self.token} if method=="POST" else {
            "accounts":[{"accountId":x,"tradePermissions":"BUY_AND_SELL"}
                        for x in self.accounts]})
        if method in self.raw:
            payload=self.raw[method]
        return FakeConnection(FakeReply(payload,self.status[method],
                content_type=self.content_type[method],
                encoding=self.encoding[method],
                declared_length=self.declared_length.get(method)),
            self.calls)


class PublicHTTPSWiringTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir="/dev/shm")
        self.path=Path(self.temp.name)/"synthetic-https-only.sqlite"
        tenant_foundation.setup(self.path)
        identity_auth.setup(self.path)
        account_scope.setup(self.path)
        tenant_api_gateway.setup(self.path)
        with account_scope._db(self.path) as con:
            tenant_history.prepare(con)
            tenant_history_details.prepare(con)
            con.execute("CREATE TABLE settings(k TEXT PRIMARY KEY,v TEXT)")
            con.execute("INSERT INTO settings VALUES('account_id','LEGACY-PUBLIC-UNTOUCHED')")
        self.key=Fernet.generate_key()
        self.store=tenant_foundation.TenantStore(self.path,credential_key=self.key)
        self.auser=self.store.provision_user("A","owner")
        self.buser=self.store.provision_user("B","owner")
        self.secret_a="SYNTHETIC-SECRET-OWNER-A-ONLY"
        self.secret_b="SYNTHETIC-SECRET-OWNER-B-ONLY"
        self.conn_a=self.store.add_connection(self.auser,self.secret_a)
        self.conn_b=self.store.add_connection(self.buser,self.secret_b)
        self.a=self.store.link_account(self.auser,self.conn_a,"PUBLIC-A-ONE","Alpha")
        self.a2=self.store.link_account(self.auser,self.conn_a,"PUBLIC-A-TWO","Alpha 2")
        self.b=self.store.link_account(self.buser,self.conn_b,"PUBLIC-B-ONE","Beta")
        self.time=[100.]
        self.control=budget.ReadOnlyAccessController(clock=lambda:self.time[0])
        self.factory=FakeFactory()
        self.client=wire.StrictPublicHTTPS()
        self.service=adapter.OfflinePublicHTTPSAccountVerifier(
            self.path,self.key,self.client,self.control,self.factory)

    def tearDown(self):
        self.temp.cleanup()

    def legacy(self):
        with sqlite3.connect(self.path) as con:
            return con.execute("SELECT v FROM settings WHERE k='account_id'").fetchone()[0]

    def test_two_fixed_endpoints_real_http_format_but_no_network(self):
        result=self.service.check_synthetic(self.auser,self.a)
        self.assertTrue(result.synthetic_credential_access_matched)
        self.assertFalse(result.provider_ownership_verified)
        self.assertFalse(result.real_credential_used)
        self.assertFalse(result.trading_enabled)
        self.assertFalse(result.funds_enabled)
        self.assertEqual(result.real_public_network_calls,0)
        self.assertEqual(len(self.factory.calls),2)
        post,listing=self.factory.calls
        self.assertEqual(post[:2],("POST",wire.TOKEN_PATH))
        self.assertEqual(listing[:2],("GET",wire.ACCOUNTS_PATH))
        self.assertEqual(json.loads(post[2]),{
            "secret":self.secret_a,"validityInMinutes":5})
        self.assertEqual(post[3]["Content-Type"],"application/json")
        self.assertEqual(listing[3]["Authorization"],"Bearer "+self.factory.token)
        self.assertNotIn("Authorization",post[3])
        self.assertNotIn("Cookie",listing[3])
        self.assertEqual(self.legacy(),"LEGACY-PUBLIC-UNTOUCHED")
        for secret in (self.secret_a,self.secret_b,self.factory.token):
            self.assertNotIn(secret,repr(result))
            self.assertNotIn(secret,repr(wire.prepare_token_request(self.secret_a)))

    def test_live_network_hard_disabled_without_env_bypass(self):
        self.assertFalse(wire.NETWORK_ENABLED)
        req=wire.prepare_accounts_request("SYNTHETIC-TOKEN-TEST")
        with patch.object(wire.http.client,"HTTPSConnection") as constructor:
            with patch.dict("os.environ",{"EDGE_TENANT_REAL_PUBLIC_READONLY_ENABLED":"true",
                                          "EDGE_PUBLIC_API_KEY":"synthetic-do-not-use"}):
                with self.assertRaises(wire.PublicWireDenied) as error:
                    self.client.send_live(req)
            self.assertEqual(error.exception.code,"NETWORK_DISABLED")
            constructor.assert_not_called()
        with self.assertRaises(adapter.OfflineHTTPSDenied):
            self.service.check_real(self.auser,self.a)
        for blocked in (self.service.submit_order,self.service.transfer_funds,
                        self.client.submit_order,self.client.transfer_funds):
            with self.assertRaises(Exception):
                blocked()
        self.assertEqual(self.factory.calls,[])

    def test_fixed_tls_hostname_ca_and_timeout_settings(self):
        with patch.object(wire.ssl,"create_default_context") as factory,patch.object(
                wire.http.client,"HTTPSConnection") as constructor:
            ctx=factory.return_value
            self.client._connection()
            self.assertTrue(ctx.check_hostname)
            self.assertEqual(ctx.verify_mode,ssl.CERT_REQUIRED)
            constructor.assert_called_once_with(
                "api.public.com",443,timeout=5,context=ctx)

    def test_methods_redirects_credentials_and_arbitrary_paths_denied(self):
        requests=(
            wire.WireRequest("POST","/userapigateway/trading/order",b"{}"),
            wire.WireRequest("DELETE",wire.ACCOUNTS_PATH,None,authorization="SYNTHETIC-TOKEN-TEST"),
            wire.WireRequest("GET","https://evil.invalid/capture",None,
                             authorization="SYNTHETIC-TOKEN-TEST"),
            wire.WireRequest("GET",wire.ACCOUNTS_PATH,b"{}",authorization="SYNTHETIC-TOKEN-TEST"),
        )
        for req in requests:
            with self.subTest(req=req):
                with self.assertRaises(wire.PublicWireDenied):
                    self.client.send_synthetic_on_fake(req,self.factory("GET"))
        with self.assertRaises(wire.PublicWireDenied):
            wire.prepare_accounts_request("token\r\nHost: evil.invalid")
        with self.assertRaises(wire.PublicWireDenied):
            wire.prepare_token_request(self.secret_a,validity_minutes=60)
        with self.assertRaises(wire.PublicWireDenied):
            self.client.send_synthetic_on_fake(
                wire.prepare_accounts_request("SYNTHETIC-TOKEN-TEST"),
                object())
        self.assertEqual(self.factory.calls,[])

    def test_invalid_provider_statuses_fail_closed_and_latch_account(self):
        for method,code,status in (
            ("POST","AUTH_REJECTED",401),("GET","AUTH_REJECTED",403),
            ("POST","RATE_LIMITED",429),("GET","PROVIDER_UNAVAILABLE",503),
            ("POST","PROVIDER_UNAVAILABLE",408),("GET","BAD_RESPONSE",302),
        ):
            with self.subTest(method=method,status=status):
                self.time[0]+=61
                self.control=budget.ReadOnlyAccessController(clock=lambda:self.time[0])
                self.factory=FakeFactory()
                self.factory.status[method]=status
                self.service=adapter.OfflinePublicHTTPSAccountVerifier(
                    self.path,self.key,self.client,self.control,self.factory)
                with self.assertRaises(adapter.OfflineHTTPSDenied) as captured:
                    self.service.check_synthetic(self.auser,self.a)
                self.assertEqual(captured.exception.code,code)
                self.assertTrue(self.control.paused(self.auser,self.a))
                self.assertFalse(self.control.paused(self.buser,self.b))
                with self.assertRaises(budget.PublicAccessDenied):
                    self.service.check_synthetic(self.auser,self.a)

    def test_bad_json_duplicate_keys_oversized_and_wrong_content_type(self):
        for which,raw,typ,encoding,declared in (
            ("GET",b'{"accounts":[{"accountId":"PUBLIC-A-ONE"}], "accounts":[]}',
             "application/json","identity",None),
            ("GET",b"not-json","application/json","identity",None),
            ("POST",b'{"accessToken":"SYNTHETIC-TOKEN-TEST"}',
             "text/html","identity",None),
            ("GET",b'{}',"application/json","gzip",None),
            ("GET",b'{}',"application/json","identity","9999999"),
            ("GET",b"x"*(wire.MAX_JSON_BYTES+1),"application/json","identity",None),
        ):
            with self.subTest(which=which,declared=declared):
                self.control=budget.ReadOnlyAccessController(clock=lambda:self.time[0])
                self.factory=FakeFactory()
                self.factory.raw[which]=raw
                self.factory.content_type[which]=typ
                self.factory.encoding[which]=encoding
                if declared is not None:
                    self.factory.declared_length[which]=declared
                self.service=adapter.OfflinePublicHTTPSAccountVerifier(
                    self.path,self.key,self.client,self.control,self.factory)
                with self.assertRaises(adapter.OfflineHTTPSDenied):
                    self.service.check_synthetic(self.auser,self.a)
                self.assertTrue(self.control.paused(self.auser,self.a))
                self.assertEqual(self.legacy(),"LEGACY-PUBLIC-UNTOUCHED")

    def test_account_authorization_rechecked_and_wrong_owner_denied_before_decryption(self):
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.service.check_synthetic(self.auser,self.b)
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.service.check_synthetic(self.buser,self.a)
        self.assertEqual(self.factory.calls,[])
        self.factory.accounts=["PUBLIC-B-ONE"]
        with self.assertRaises(adapter.OfflineHTTPSDenied):
            self.service.check_synthetic(self.auser,self.a)
        self.assertTrue(self.control.paused(self.auser,self.a))
        self.assertFalse(self.control.paused(self.buser,self.b))
        self.time[0]+=61
        self.factory=FakeFactory(accounts=["PUBLIC-B-ONE"])
        self.service=adapter.OfflinePublicHTTPSAccountVerifier(
            self.path,self.key,self.client,self.control,self.factory)
        result=self.service.check_synthetic(self.buser,self.b)
        self.assertTrue(result.account_scope_verified)

    def test_revoked_credentials_abort_between_token_and_account_list(self):
        def revoke(method):
            if method=="GET":
                with account_scope._db(self.path) as con:
                    con.execute("UPDATE tenant_connections SET revoked_at='2026-11-09' WHERE connection_id=?",
                                (self.conn_a,))
        self.factory.hook=revoke
        with self.assertRaises(tenant_foundation.TenantAccessError):
            self.service.check_synthetic(self.auser,self.a)
        # Only the token exchange was attempted; there was no list-account request.
        self.assertEqual([entry[0] for entry in self.factory.calls],["POST"])
        self.assertEqual(self.legacy(),"LEGACY-PUBLIC-UNTOUCHED")

    def test_encrypted_real_secret_and_wrong_decryption_key_cannot_be_sent(self):
        with account_scope._db(self.path) as con:
            con.execute("UPDATE tenant_connections SET credential_ciphertext=? WHERE connection_id=?",
                        (Fernet(self.key).encrypt(b"REAL-PUBLIC-SECRET-NOT-ALLOWED"),self.conn_a))
        with self.assertRaises(adapter.OfflineHTTPSDenied) as error:
            self.service.check_synthetic(self.auser,self.a)
        self.assertEqual(error.exception.code,"INVALID_FIXTURE")
        self.assertEqual(self.factory.calls,[])
        self.assertTrue(self.control.paused(self.auser,self.a))
        self.time[0]+=61
        new_controller=budget.ReadOnlyAccessController(clock=lambda:self.time[0])
        wrong=adapter.OfflinePublicHTTPSAccountVerifier(
            self.path,Fernet.generate_key(),self.client,new_controller,self.factory)
        with self.assertRaises(adapter.OfflineHTTPSDenied):
            wrong.check_synthetic(self.auser,self.a)
        self.assertEqual(self.factory.calls,[])

    def test_per_account_budgets_manual_review_and_global_emergency_stop(self):
        result=self.service.check_synthetic(self.auser,self.a)
        self.assertTrue(result.account_scope_verified)
        with self.assertRaises(budget.PublicAccessDenied) as caught:
            self.service.check_synthetic(self.auser,self.a)
        self.assertEqual(caught.exception.code,"REQUEST_BUDGET_EXHAUSTED")
        self.time[0]+=61
        self.assertTrue(self.service.check_synthetic(self.auser,self.a2).account_scope_verified)
        # An explicit failure latches only this account.
        self.control.block_account(self.auser,self.a)
        with self.assertRaises(budget.PublicAccessDenied):
            self.service.check_synthetic(self.auser,self.a)
        with self.assertRaises(budget.PublicAccessDenied):
            self.control.unpause_for_offline_test(
                self.auser,self.a,phrase="bad")
        self.control.unpause_for_offline_test(
            self.auser,self.a,phrase="REVIEW OFFLINE ACCESS ONLY")
        self.time[0]+=61
        self.assertTrue(self.service.check_synthetic(self.auser,self.a).account_scope_verified)
        self.control.emergency_stop()
        for account,user in ((self.a,self.auser),(self.b,self.buser)):
            with self.assertRaises(budget.PublicAccessDenied) as caught:
                self.service.check_synthetic(user,account)
            self.assertEqual(caught.exception.code,"EMERGENCY_STOP")
        with self.assertRaises(budget.PublicAccessDenied):
            self.control.unpause_for_offline_test(
                self.auser,self.a,phrase="REVIEW OFFLINE ACCESS ONLY")
        self.assertEqual(self.legacy(),"LEGACY-PUBLIC-UNTOUCHED")

    def test_production_disk_and_live_app_imports_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            path=Path(other)/"not-tmpfs.db"
            with sqlite3.connect(self.path) as source,sqlite3.connect(path) as target:
                source.backup(target)
            with self.assertRaises(Exception):
                adapter.OfflinePublicHTTPSAccountVerifier(
                    path,self.key,self.client,self.control,self.factory)
        app=(ROOT/"backend/app.py").read_text()
        worker=(ROOT/"backend/engine/automation_worker.py").read_text()
        audit=tenant_route_audit.inspect_sources(app,worker)
        self.assertFalse(audit["crossAccountProductionCutoverAllowed"])
        self.assertFalse(audit["publicHTTPSNetworkEnabled"])
        for module in ("tenant_public_https_wire","tenant_public_access_controller",
                       "tenant_public_https_account_adapter"):
            self.assertNotIn(module,app)
            self.assertNotIn(module,worker)
            with self.assertRaises(tenant_route_audit.ApiBoundaryError):
                tenant_route_audit.inspect_sources(
                    app+"\nfrom engine import "+module+"\n",worker)
            with self.assertRaises(tenant_route_audit.ApiBoundaryError):
                tenant_route_audit.inspect_sources(
                    app,worker+"\nfrom engine import "+module+"\n")


if __name__=="__main__":
    unittest.main()
