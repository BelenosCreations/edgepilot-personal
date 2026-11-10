"""v0.2.40 synthetic two-device shared-backend end-to-end acceptance.

This is NOT physical Android biometric verification or a real Public API
integration. Two separate Flask cookie jars represent independent devices;
every Public HTTP request is intercepted by a deny-by-default fake transport.
Identity, onboarding, vault, read-only portfolio, watchlists, monitoring
preview, passkey availability, sessions and legacy separation are checked
through their real, gated server routes.
"""
import importlib
import os
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from engine import tenant_public_live_readonly as ro

HOST="https://edgepilot.example.test"
ORIGIN={"Origin":HOST}
SECRET_A="FAKE-PUBLIC-SECRET-ACCOUNT-ALICE-2026-ONLY"
SECRET_B="FAKE-PUBLIC-SECRET-ACCOUNT-BOB-2026-ONLY"
ACCESS_A="FAKE-ACCESS-TOKEN-ALICE-123456789012"
ACCESS_B="FAKE-ACCESS-TOKEN-BOB-123456789012"
ACCOUNT_A="FAKE-ALICE-BROKER"
ACCOUNT_B="FAKE-BOB-BROKER"


class DenyByDefaultPublic:
    def __init__(self):
        self.calls=[]

    @staticmethod
    def _reply(payload,status=200):
        class Response:
            status_code=status
            def json(self):
                return payload
        return Response()

    def post(self,url,*,json,timeout):
        self.calls.append(("POST",url))
        if url!=ro.BASE+ro.AUTH_PATH or timeout!=ro.TIMEOUT or set(json)!={
                "secret","validityInMinutes"} or json["validityInMinutes"]!=5:
            raise AssertionError("Unapproved Public operation")
        tokens={SECRET_A:ACCESS_A,SECRET_B:ACCESS_B}
        if json["secret"] not in tokens:
            return self._reply({},401)
        return self._reply({"accessToken":tokens[json["secret"]]})

    def get(self,url,*,headers,timeout):
        self.calls.append(("GET",url))
        if timeout!=ro.TIMEOUT or headers.get("Accept")!="application/json":
            raise AssertionError("Unapproved Public operation")
        bearer=headers.get("Authorization")
        if bearer=="Bearer "+ACCESS_A:
            ref=ACCOUNT_A
        elif bearer=="Bearer "+ACCESS_B:
            ref=ACCOUNT_B
        else:
            raise AssertionError("Unapproved identity token")
        if url==ro.BASE+ro.LIST_PATH:
            return self._reply({"accounts":[{"accountId":ref,"accountType":"BROKERAGE"}]})
        if url==ro.BASE+f"/userapigateway/trading/{ref}/portfolio/v2":
            return self._reply({
                "totalAccountValue":"101.00" if ref==ACCOUNT_A else "202.00",
                "positions":[{
                    "instrument":{"symbol":"SPY" if ref==ACCOUNT_A else "QQQ"},
                    "currentValue":"50.00","quantity":"1"}]})
        raise AssertionError("Unexpected provider endpoint, blocked")


class TwoDeviceSyntheticAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="edgepilot-v040-acceptance-")
        self.env=patch.dict(os.environ,{
            "EDGE_DB_PATH":self.tmp.name+"/two-user.db",
            "EDGE_TENANT_SCHEMA_PREPARE":"true",
            "EDGE_IDENTITY_AUTH_ENABLED":"true",
            "EDGE_TENANT_SIGNUP_ENABLED":"true",
            "EDGE_TENANT_PASSKEYS_ENABLED":"true",
            "EDGE_WEBAUTHN_RP_ID":"edgepilot.example.test",
            "EDGE_WEBAUTHN_ORIGIN":HOST,
            "EDGE_TENANT_SESSION_CONTROLS_ENABLED":"true",
            "EDGE_TENANT_ACCOUNT_READS_ENABLED":"true",
            "EDGE_TENANT_MONITOR_PREVIEW_ENABLED":"true",
            "EDGE_TENANT_WATCHLIST_EDIT_ENABLED":"true",
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED":"true",
            "EDGE_TENANT_PUBLIC_READONLY_ENABLED":"true",
            "EDGE_CREDENTIAL_KEY":Fernet.generate_key().decode(),
            "EDGE_APP_TOKEN":"fake-legacy-owner-access-token-for-tests-123456789",
            "PUBLIC_API_SECRET":"",
            "EDGE_AUTOMATION_WORKER_ENABLED":"false",
        })
        self.env.start()
        # Fail the test if any production-style requests transport tries to
        # leave the process. FakePublic is an in-memory fake, not requests.
        self.block_network=patch("requests.sessions.Session.request",
                                 side_effect=AssertionError("Real network prohibited in synthetic acceptance"))
        self.real_network=self.block_network.start()
        import app
        self.module=importlib.reload(app)
        self.http=DenyByDefaultPublic()
        self.module.tenant_public_reader.http=self.http
        self.module.tenant_public_reader.clock=lambda:1900000000
        self.a=self.module.app.test_client()
        self.b=self.module.app.test_client()
        self.extra_a=self.module.app.test_client()
        self.anon=self.module.app.test_client()
        self.creds={
            "a":("device_alice","Example-Alice-Password-2026",SECRET_A,ACCOUNT_A),
            "b":("device_bob","Example-Bob-Password-2026",SECRET_B,ACCOUNT_B),
        }
        self.csrf={}

    def tearDown(self):
        self.block_network.stop()
        self.env.stop()
        import app
        importlib.reload(app)
        self.tmp.cleanup()

    def post(self,client,route,payload,csrf=None):
        h=dict(ORIGIN)
        if csrf is not None:h["X-Edge-Identity-CSRF"]=csrf
        return client.post(route,base_url=HOST,headers=h,json=payload)

    def put(self,client,route,payload,csrf):
        return client.put(route,base_url=HOST,headers={
            **ORIGIN,"X-Edge-Identity-CSRF":csrf},json=payload)

    def get(self,client,route,csrf=None):
        headers={}
        if csrf is not None:headers["X-Edge-Identity-CSRF"]=csrf
        return client.get(route,base_url=HOST,headers=headers)

    def register_and_sign_in(self,label,client):
        name,password,secret,broker=self.creds[label]
        invitation=self.module.tenant_registration_store.issue_invitation()["invitation"]
        registered=self.post(client,"/api/identity/register",{
            "invitation":invitation,"username":name,"password":password,
            "displayName":"Alice device" if label=="a" else "Bob device"})
        self.assertEqual(registered.status_code,201,registered.get_data(as_text=True))
        self.assertNotIn("Set-Cookie",registered.headers)
        before=self.get(client,"/api/identity/session")
        self.assertEqual(before.status_code,401)
        login=self.post(client,"/api/identity/login",
                        {"username":name,"password":password})
        self.assertEqual(login.status_code,200,login.get_data(as_text=True))
        self.assertIn("Secure",login.headers["Set-Cookie"])
        self.assertIn("HttpOnly",login.headers["Set-Cookie"])
        self.csrf[label]=login.get_json()["csrf"]
        session=self.get(client,"/api/identity/session")
        self.assertEqual(session.status_code,200)
        self.csrf[label]=session.get_json()["csrf"]
        self.assertEqual(session.get_json()["scope"],"identity_only_no_broker_access")
        return session.get_json()["user"]["userId"]

    def test_two_independent_users_end_to_end_with_zero_real_broker_calls(self):
        id_a=self.register_and_sign_in("a",self.a)
        id_b=self.register_and_sign_in("b",self.b)
        self.assertNotEqual(id_a,id_b)
        self.assertEqual(self.get(self.anon,"/api/identity/accounts").status_code,401)
        self.assertEqual(self.get(self.a,"/api/dashboard").status_code,401)
        self.assertEqual(self.get(self.b,"/api/dashboard").status_code,401)

        # Both identities may enroll a passkey ONLY with their own session
        # and CSRF. The cryptographic registration finish is covered by
        # tenant_passkeys tests; no fake success or biometric claim here.
        for label,client in (("a",self.a),("b",self.b)):
            ready=self.post(client,"/api/identity/passkeys/register/options",
                            {},self.csrf[label])
            self.assertEqual(ready.status_code,200,ready.get_data(as_text=True))
            self.assertEqual(ready.get_json()["publicKey"]["rp"]["id"],
                             "edgepilot.example.test")
        self.assertEqual(self.post(self.anon,
            "/api/identity/passkeys/authenticate/finish",
            {"requestId":"forged","credential":{}}).status_code,400)

        # Different real EdgePilot user sessions on the SAME configured
        # HTTPS service store different fake Public secrets.
        connections={}
        linked={}
        for label,client in (("a",self.a),("b",self.b)):
            name,password,secret,broker=self.creds[label]
            added=self.post(client,"/api/identity/public/connections",
                            {"secret":secret},self.csrf[label])
            self.assertEqual(added.status_code,201,added.get_data(as_text=True))
            connections[label]=added.get_json()["connectionId"]
            self.assertNotIn(secret,added.get_data(as_text=True))
        self.assertNotEqual(connections["a"],connections["b"])
        for label,client in (("a",self.a),("b",self.b)):
            secret=self.creds[label][2]
            broker=self.creds[label][3]
            route="/api/identity/public/read/connections/"+connections[label]+"/accounts"
            discovered=self.get(client,route)
            self.assertEqual(discovered.status_code,200,discovered.get_data(as_text=True))
            self.assertEqual(discovered.get_json()["accounts"][0]["accountId"],broker)
            self.assertFalse(discovered.get_json()["ordersEnabled"])
            other=self.b if label=="a" else self.a
            self.assertEqual(self.get(other,route).status_code,404)
            linked_response=self.post(client,route,{"accountId":broker,"label":"My account"},self.csrf[label])
            self.assertEqual(linked_response.status_code,200,linked_response.get_data(as_text=True))
            self.assertTrue(linked_response.get_json()["verifiedByPublic"])
            linked[label]=linked_response.get_json()["accountId"]
        self.assertNotEqual(linked["a"],linked["b"])

        for label,client in (("a",self.a),("b",self.b)):
            account=linked[label]
            other=linked["b" if label=="a" else "a"]
            own=self.get(client,"/api/identity/public/read/accounts/"+account+"/portfolio")
            self.assertEqual(own.status_code,200,own.get_data(as_text=True))
            self.assertEqual(own.get_json()["balance"],"101.00" if label=="a" else "202.00")
            self.assertTrue(own.get_json()["readOnly"])
            self.assertFalse(own.get_json()["ordersEnabled"])
            self.assertFalse(own.get_json()["transfersEnabled"])
            self.assertEqual(self.get(client,
                "/api/identity/public/read/accounts/"+other+"/portfolio").status_code,404)
            watchlist=["SPY","QQQ"] if label=="a" else ["MSFT"]
            saved=self.put(client,"/api/identity/accounts/"+account+"/monitor/watchlist",
                           {"symbols":watchlist},self.csrf[label])
            self.assertEqual(saved.status_code,200,saved.get_data(as_text=True))
            plan=self.get(client,"/api/identity/accounts/"+account+"/monitor/preview")
            self.assertEqual(plan.status_code,200)
            self.assertEqual(plan.get_json()["watchlist"],watchlist)
            self.assertTrue(plan.get_json()["simulatedPlanOnly"])
            self.assertFalse(plan.get_json()["workerActive"])
            self.assertFalse(plan.get_json()["brokerRequestsAllowed"])
            self.assertEqual(self.get(client,
                "/api/identity/accounts/"+other+"/monitor/preview").status_code,404)

        # A second Alice device is authenticated separately, may be
        # signed out by Alice, and has no effect on Bob's session.
        second=self.post(self.extra_a,"/api/identity/login",
            {"username":self.creds["a"][0],"password":self.creds["a"][1]})
        self.assertEqual(second.status_code,200)
        sessions=self.get(self.a,"/api/identity/sessions",self.csrf["a"])
        self.assertEqual(sessions.status_code,200,sessions.get_data(as_text=True))
        self.assertEqual(sessions.get_json()["count"],2)
        target=next(x["sessionId"] for x in sessions.get_json()["sessions"]
                    if not x["current"])
        revoked=self.a.delete("/api/identity/sessions/"+target,base_url=HOST,
            headers={**ORIGIN,"X-Edge-Identity-CSRF":self.csrf["a"]})
        self.assertEqual(revoked.status_code,200)
        self.assertTrue(revoked.get_json()["otherSessionRevoked"])
        self.assertEqual(self.get(self.extra_a,"/api/identity/session").status_code,401)
        self.assertEqual(self.get(self.b,"/api/identity/session").status_code,200)

        # Fake transport is the ONLY provider source, and its allowlist
        # never includes orders, funds, deposits, withdrawals, or outside
        # provider URLs.
        self.assertGreater(len(self.http.calls),0)
        self.real_network.assert_not_called()
        self.assertTrue(all(url.startswith(ro.BASE+"/") for _,url in self.http.calls))
        self.assertFalse(any(("order" in url.lower() or
                              "transfer" in url.lower() or
                              "withdraw" in url.lower())
                             for _,url in self.http.calls))
        all_payloads=str(linked)+str(connections)
        for private in (SECRET_A,SECRET_B,ACCESS_A,ACCESS_B):
            self.assertNotIn(private,all_payloads)

    def test_independent_users_require_separate_secret_and_mutating_csrf(self):
        self.register_and_sign_in("a",self.a)
        self.register_and_sign_in("b",self.b)
        missing=self.post(self.a,"/api/identity/public/connections",{"secret":SECRET_A})
        self.assertEqual(missing.status_code,403)
        wrong=self.post(self.a,"/api/identity/public/connections",
                        {"secret":SECRET_A},self.csrf["b"])
        self.assertNotEqual(wrong.status_code,201)
        forged=self.a.post("/api/identity/public/connections",base_url=HOST,
            headers={"Origin":"https://evil.example","X-Edge-Identity-CSRF":self.csrf["a"]},
            json={"secret":SECRET_A})
        self.assertEqual(forged.status_code,403)
        self.assertEqual(self.get(self.a,"/api/identity/public/connections")
                         .get_json()["connections"],[])
        self.assertEqual(self.get(self.b,"/api/identity/public/connections")
                         .get_json()["connections"],[])

if __name__=="__main__":
    unittest.main()
