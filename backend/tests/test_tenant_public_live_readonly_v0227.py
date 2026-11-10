"""v0.2.27 two-user read-only Public HTTPS tests with fake transport only.

ALL secrets/account IDs/response data are synthetic. Tests NEVER connect to
Public; the fake transport denies any unrecognized URL, method or token.
"""
from __future__ import annotations

import importlib
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet

from engine import (
    identity_auth, tenant_foundation, tenant_public_vault,
    tenant_public_live_readonly as ro, tenant_route_audit,
)

HOST="https://edgepilot.example.test"
ORIGIN={"Origin":HOST}
KEY_A="SYNTHETIC-PUBLIC-SECRET-OWNER-ALICE-000001"
KEY_B="SYNTHETIC-PUBLIC-SECRET-OWNER-BOB-000002"
ACCOUNT_A="ALICE-SYNTHETIC-BROKER"
ACCOUNT_B="BOB-SYNTHETIC-BROKER"
TOKENS={
    KEY_A:"SYNTHETIC-BEARER-ALICE-123456789012345",
    KEY_B:"SYNTHETIC-BEARER-BOB-123456789012345",
}


class FakePublic:
    def __init__(self):
        self.calls=[]
        self.after_list=None
        self.after_portfolio=None

    @staticmethod
    def reply(value,status=200):
        class Response:
            status_code=status
            def json(self):
                return value
        return Response()

    def post(self,url,*,json,timeout):
        self.calls.append(("POST",url,json.get("secret")))
        if url!=ro.BASE+ro.AUTH_PATH or timeout!=ro.TIMEOUT:
            raise AssertionError("Unexpected provider network call")
        if set(json)!={"secret","validityInMinutes"} or json["validityInMinutes"]!=5:
            raise AssertionError("Unexpected credential exchange")
        if json["secret"] not in TOKENS:
            return self.reply({},401)
        return self.reply({"accessToken":TOKENS[json["secret"]]})

    def get(self,url,*,headers,timeout):
        self.calls.append(("GET",url,headers.get("Authorization")))
        if timeout!=ro.TIMEOUT or headers.get("Accept")!="application/json":
            raise AssertionError("Unexpected HTTP parameters")
        authorized=headers.get("Authorization","")
        if authorized not in ("Bearer "+x for x in TOKENS.values()):
            return self.reply({},401)
        account=ACCOUNT_A if authorized=="Bearer "+TOKENS[KEY_A] else ACCOUNT_B
        if url==ro.BASE+ro.LIST_PATH:
            if self.after_list is not None:
                callback=self.after_list
                self.after_list=None
                callback()
            return self.reply({"accounts":[{"accountId":account,"accountType":"BROKERAGE"}]})
        if url==ro.BASE+"/userapigateway/trading/"+account+"/portfolio/v2":
            if self.after_portfolio is not None:
                callback=self.after_portfolio
                self.after_portfolio=None
                callback()
            return self.reply({
                "totalAccountValue":"1234.56" if account==ACCOUNT_A else "987.65",
                "positions":[{"instrument":{"symbol":"SPY" if account==ACCOUNT_A else "QQQ"},
                              "currentValue":"321.00","quantity":"2"}]})
        raise AssertionError("Unlisted endpoint: fake transport refuses it")


class UserPublicReadOnlyUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="edgepilot-public-ro-")
        self.path=self.tmp.name+"/db.sqlite"
        self.key=Fernet.generate_key().decode()
        tenant_foundation.setup(self.path)
        identity_auth.setup(self.path)
        tenant_public_vault.setup(self.path)
        ro.setup(self.path)
        self.tenants=tenant_foundation.TenantStore(self.path,credential_key=self.key)
        self.users=[self.tenants.provision_user("Alice"),self.tenants.provision_user("Bob")]
        self.identities=identity_auth.IdentityStore(self.path)
        self.identities.provision(self.users[0],"alice","alice-valid-password-2026")
        self.identities.provision(self.users[1],"bobby","bobby-valid-password-2026")
        self.sessions=[
            self.identities.authenticate("alice","alice-valid-password-2026","phone1"),
            self.identities.authenticate("bobby","bobby-valid-password-2026","phone2"),
        ]
        self.vault=tenant_public_vault.TenantPublicVault(self.path,self.identities,
                                                         credential_key=self.key)
        self.connections=[
            self.vault.save(self.sessions[0]["token"],self.sessions[0]["csrf"],KEY_A)["connectionId"],
            self.vault.save(self.sessions[1]["token"],self.sessions[1]["csrf"],KEY_B)["connectionId"],
        ]
        self.fake=FakePublic()
        self.now=[1900000000]
        self.adapter=ro.TenantPublicReadOnly(self.path,self.identities,self.vault,
                                             http=self.fake,clock=lambda:self.now[0])

    def tearDown(self):
        self.tmp.cleanup()

    def test_each_user_reads_only_own_provider_account(self):
        a=self.adapter.discover(self.sessions[0]["token"],self.connections[0])
        b=self.adapter.discover(self.sessions[1]["token"],self.connections[1])
        self.assertEqual(a["accounts"][0]["accountId"],ACCOUNT_A)
        self.assertEqual(b["accounts"][0]["accountId"],ACCOUNT_B)
        self.assertNotIn(KEY_A,str(a))
        self.assertNotIn(TOKENS[KEY_A],str(a))
        self.assertFalse(a["ordersEnabled"])
        with self.assertRaises(ro.PublicReadUnavailable):
            self.adapter.discover(self.sessions[0]["token"],self.connections[1])
        with self.assertRaises(ro.PublicReadUnavailable):
            self.adapter.link_verified(self.sessions[1]["token"],self.sessions[1]["csrf"],
                                       self.connections[1],ACCOUNT_A,"Wrong")
        links=[
            self.adapter.link_verified(s["token"],s["csrf"],connection,account,"Personal")
            for s,connection,account in zip(self.sessions,self.connections,[ACCOUNT_A,ACCOUNT_B])
        ]
        for i,record in enumerate(links):
            self.assertTrue(record["verifiedByPublic"])
            own=self.adapter.portfolio(self.sessions[i]["token"],record["accountId"])
            self.assertEqual(own["balance"],"1234.56" if i==0 else "987.65")
            self.assertEqual(own["holdings"][0]["symbol"],"SPY" if i==0 else "QQQ")
            self.assertTrue(own["readOnly"])
            self.assertFalse(own["transfersEnabled"])
            self.assertNotIn(TOKENS[KEY_A],str(own))
            self.assertNotIn(TOKENS[KEY_B],str(own))
            with self.assertRaises(ro.PublicReadUnavailable):
                self.adapter.portfolio(self.sessions[1-i]["token"],record["accountId"])
        self.assertTrue(all(
            path==ro.BASE+ro.AUTH_PATH or
            path==ro.BASE+ro.LIST_PATH or
            path.endswith("/portfolio/v2")
            for _,path,_ in self.fake.calls))
        self.assertFalse(any("/orders" in path or "/transfer" in path
                             for _,path,_ in self.fake.calls))

    def test_rotation_mid_discovery_blocks_stale_results(self):
        a=self.sessions[0]
        self.fake.after_list=lambda:self.vault.rotate(
            a["token"],a["csrf"],self.connections[0],KEY_A)
        with self.assertRaises(ro.PublicReadUnavailable):
            self.adapter.discover(a["token"],self.connections[0])
        self.assertEqual(self.adapter.discover(a["token"],self.connections[0])["accounts"][0]["accountId"],
                         ACCOUNT_A)

    def test_rotation_mid_portfolio_blocks_stale_result(self):
        a=self.sessions[0]
        linked=self.adapter.link_verified(a["token"],a["csrf"],
                                         self.connections[0],ACCOUNT_A,"A")
        self.fake.after_portfolio=lambda:self.vault.rotate(
            a["token"],a["csrf"],self.connections[0],KEY_A)
        with self.assertRaises(ro.PublicReadUnavailable):
            self.adapter.portfolio(a["token"],linked["accountId"])
        with sqlite3.connect(self.path) as db:
            disabled=db.execute("SELECT disabled_at FROM tenant_accounts WHERE account_id=?",
                                (linked["accountId"],)).fetchone()[0]
        self.assertIsNotNone(disabled)

    def test_disabling_user_or_disconnecting_blocks_provider_before_network(self):
        alice=self.sessions[0]
        bob=self.sessions[1]
        self.vault.disconnect(alice["token"],alice["csrf"],self.connections[0])
        before=len(self.fake.calls)
        with self.assertRaises(ro.PublicReadUnavailable):
            self.adapter.discover(alice["token"],self.connections[0])
        self.assertEqual(before,len(self.fake.calls))
        self.assertEqual(self.adapter.discover(bob["token"],self.connections[1])
                         ["accounts"][0]["accountId"],ACCOUNT_B)

    def test_request_rate_limit_is_per_user_and_fails_closed(self):
        with patch.object(ro,"PER_USER_PER_MINUTE",2):
            a=self.sessions[0]
            self.adapter.discover(a["token"],self.connections[0])
            self.adapter.discover(a["token"],self.connections[0])
            with self.assertRaisesRegex(ro.PublicReadUnavailable,"request limit"):
                self.adapter.discover(a["token"],self.connections[0])
            self.assertEqual(self.adapter.discover(
                self.sessions[1]["token"],self.connections[1])["accounts"][0]["accountId"],ACCOUNT_B)
        self.now[0]+=61
        self.assertEqual(self.adapter.discover(
            self.sessions[0]["token"],self.connections[0])["accounts"][0]["accountId"],ACCOUNT_A)
        self.now[0]-=2
        with self.assertRaises(ro.PublicReadUnavailable):
            self.adapter.discover(self.sessions[1]["token"],self.connections[1])

    def test_public_errors_never_include_secret_or_upstream_body(self):
        self.fake.post=lambda *args,**kwargs: FakePublic.reply({"error":KEY_A},401)
        with self.assertRaises(ro.PublicReadUnavailable) as caught:
            self.adapter.discover(self.sessions[0]["token"],self.connections[0])
        self.assertNotIn(KEY_A,str(caught.exception))

    def test_no_live_trade_endpoints_exposed_by_adapter(self):
        for name in ("submit_order","transfer_funds","place_order","withdraw"):
            self.assertFalse(hasattr(self.adapter,name))
        for invalid in ("../orders","something/../account","", "spaces id"):
            with self.assertRaises(ro.PublicReadUnavailable):
                self.adapter.link_verified(
                    self.sessions[0]["token"],self.sessions[0]["csrf"],
                    self.connections[0],invalid,"Bad")


class TenantPublicReadOnlyHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="edgepilot-http-ro-")
        self.path=self.tmp.name+"/backend.db"
        self.env=patch.dict(os.environ,{
            "EDGE_DB_PATH":self.path,
            "EDGE_TENANT_SCHEMA_PREPARE":"true",
            "EDGE_IDENTITY_AUTH_ENABLED":"true",
            "EDGE_TENANT_ACCOUNT_READS_ENABLED":"true",
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED":"true",
            "EDGE_TENANT_PUBLIC_READONLY_ENABLED":"true",
            "EDGE_CREDENTIAL_KEY":Fernet.generate_key().decode(),
            "EDGE_APP_TOKEN":"legacy-never-used-by-other-tenants-0123456789",
            "PUBLIC_API_SECRET":"",
            "EDGE_AUTOMATION_WORKER_ENABLED":"false",
        })
        self.env.start()
        import app
        self.appmod=importlib.reload(app)
        users=[
            self.appmod.tenant_foundation.TenantStore(self.path).provision_user("Alice"),
            self.appmod.tenant_foundation.TenantStore(self.path).provision_user("Bob"),
        ]
        self.appmod.identity_store.provision(users[0],"alice","alice-synthetic-password-2026")
        self.appmod.identity_store.provision(users[1],"bobby","bobby-synthetic-password-2026")
        self.clients=[self.appmod.app.test_client(),self.appmod.app.test_client()]
        self.csrf=[]
        for client,username,password in (
            (self.clients[0],"alice","alice-synthetic-password-2026"),
            (self.clients[1],"bobby","bobby-synthetic-password-2026"),
        ):
            login=client.post("/api/identity/login",base_url=HOST,headers=ORIGIN,
                              json={"username":username,"password":password})
            self.assertEqual(login.status_code,200)
            self.csrf.append(login.get_json()["csrf"])
        self.appmod.tenant_public_reader.http=FakePublic()
        self.appmod.tenant_public_reader.clock=lambda:1900000000

    def tearDown(self):
        self.env.stop()
        import app
        importlib.reload(app)
        self.tmp.cleanup()

    def post(self,i,path,payload):
        return self.clients[i].post(path,base_url=HOST,headers={
            **ORIGIN,"X-Edge-Identity-CSRF":self.csrf[i]},json=payload)

    def test_two_distinct_public_keys_and_portfolios_via_identity_http(self):
        vault="/api/identity/public/connections"
        ca=self.post(0,vault,{"secret":KEY_A}).get_json()["connectionId"]
        cb=self.post(1,vault,{"secret":KEY_B}).get_json()["connectionId"]
        path_a=f"/api/identity/public/read/connections/{ca}/accounts"
        path_b=f"/api/identity/public/read/connections/{cb}/accounts"
        a=self.clients[0].get(path_a,base_url=HOST)
        b=self.clients[1].get(path_b,base_url=HOST)
        self.assertEqual(a.status_code,200,a.get_data(as_text=True))
        self.assertEqual(b.status_code,200,b.get_data(as_text=True))
        self.assertEqual(a.get_json()["accounts"][0]["accountId"],ACCOUNT_A)
        self.assertEqual(b.get_json()["accounts"][0]["accountId"],ACCOUNT_B)
        self.assertEqual(self.clients[1].get(path_a,base_url=HOST).status_code,404)
        self.assertEqual(self.post(1,path_b,{"accountId":ACCOUNT_A,"label":"Stolen"}).status_code,404)
        linked_a=self.post(0,path_a,{"accountId":ACCOUNT_A,"label":"Mine"})
        linked_b=self.post(1,path_b,{"accountId":ACCOUNT_B,"label":"Mine"})
        self.assertEqual(linked_a.status_code,200,linked_a.get_data(as_text=True))
        self.assertEqual(linked_b.status_code,200,linked_b.get_data(as_text=True))
        a_id=linked_a.get_json()["accountId"]
        b_id=linked_b.get_json()["accountId"]
        pfx="/api/identity/public/read/accounts/"
        pa=self.clients[0].get(pfx+a_id+"/portfolio",base_url=HOST)
        pb=self.clients[1].get(pfx+b_id+"/portfolio",base_url=HOST)
        self.assertEqual(pa.get_json()["balance"],"1234.56")
        self.assertEqual(pb.get_json()["balance"],"987.65")
        self.assertEqual(self.clients[0].get(pfx+b_id+"/portfolio",base_url=HOST).status_code,404)
        self.assertEqual(self.clients[1].get(pfx+a_id+"/portfolio",base_url=HOST).status_code,404)
        self.assertEqual(self.clients[0].get("/api/dashboard",base_url=HOST).status_code,401)
        for payload in (str(a.get_json()),str(pa.get_json()),str(pb.get_json())):
            self.assertNotIn(KEY_A,payload)
            self.assertNotIn(KEY_B,payload)
            self.assertNotIn(TOKENS[KEY_A],payload)

    def test_same_origin_csrf_and_no_order_surface(self):
        vault="/api/identity/public/connections"
        connection=self.post(0,vault,{"secret":KEY_A}).get_json()["connectionId"]
        path=f"/api/identity/public/read/connections/{connection}/accounts"
        bad=self.clients[0].post(path,base_url=HOST,headers=ORIGIN,
                                 json={"accountId":ACCOUNT_A,"label":"Wrong"})
        self.assertEqual(bad.status_code,403)
        forged=self.clients[0].post(path,base_url=HOST,headers={
            "Origin":"https://evil.example","X-Edge-Identity-CSRF":self.csrf[0]},
            json={"accountId":ACCOUNT_A,"label":"Wrong"})
        self.assertEqual(forged.status_code,403)
        self.assertEqual(self.clients[0].get("/api/order/preview",base_url=HOST).status_code,401)
        audit=tenant_route_audit.inspect_repo()
        self.assertFalse(audit["crossAccountProductionCutoverAllowed"])
        self.assertFalse(audit["productionKillSwitchDeployed"])


if __name__=="__main__":
    unittest.main()
