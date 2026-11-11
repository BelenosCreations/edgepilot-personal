"""v0.2.53: staging-only synthetic member bootstrap and account landing.

No network, real owner keys, live Public calls, trades or real biometrics.
"""
import hashlib
import importlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engine import staging_operator

ROOT=Path(__file__).resolve().parents[2]
STAGE="staging-edgepilot.belenoscreations.biz"
OWNER="edgepilot.belenoscreations.biz"
KEY="Q"*43  # Dummy fixture only, never a real operator credential.
DIGEST=hashlib.sha256(KEY.encode()).hexdigest()


class StagingOperatorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="edge-stage-operator-")
        self.db=self.temp.name+"/staging.db"
        self.env=patch.dict(os.environ,{
            "EDGE_DB_PATH":self.db,
            "EDGE_ISOLATED_STAGING":"true",
            "EDGE_WEBAUTHN_RP_ID":STAGE,
            "EDGE_WEBAUTHN_ORIGIN":"https://"+STAGE,
            "EDGE_ANDROID_ASSOCIATION_PACKAGE":"com.edgepilot.mobile.staging",
            "EDGE_ANDROID_CERT_SHA256":":".join(["AA"]*32),
            "EDGE_STAGING_OPERATOR_SHA256":DIGEST,
            "EDGE_APP_TOKEN":"",
            "PUBLIC_API_SECRET":"",
            "EDGE_CREDENTIAL_KEY":"",
            "EDGE_AUTOMATION_WORKER_ENABLED":"false",
            "ENABLE_LIVE_ORDERS":"false",
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED":"false",
            "EDGE_TENANT_PUBLIC_READONLY_ENABLED":"false",
            "EDGE_TENANT_ACCOUNT_READS_ENABLED":"false",
            "EDGE_TENANT_MONITOR_PREVIEW_ENABLED":"false",
            "EDGE_TENANT_WATCHLIST_EDIT_ENABLED":"false",
            "EDGE_TENANT_SCHEMA_PREPARE":"true",
            "EDGE_IDENTITY_AUTH_ENABLED":"true",
            "EDGE_TENANT_SIGNUP_ENABLED":"true",
            "EDGE_TENANT_PASSKEYS_ENABLED":"true",
        })
        self.env.start()
        import app
        self.app=importlib.reload(app)
        self.client=self.app.app.test_client()

    def tearDown(self):
        self.env.stop()
        import app
        importlib.reload(app)
        self.temp.cleanup()

    def post(self,key=KEY,host=STAGE,origin=None,body=None):
        site="https://"+host
        return self.client.post(
            "/api/staging/invitations",base_url=site,
            headers={"Origin":site if origin is None else origin,
                     "X-Edge-Staging-Operator":key},
            json={} if body is None else body)

    def test_staging_root_opens_identity_without_owner_login(self):
        r=self.client.get("/",base_url="https://"+STAGE)
        self.assertEqual(r.status_code,302)
        self.assertEqual(r.headers["Location"],"/account")
        a=self.client.get("/account",base_url="https://"+STAGE)
        self.assertEqual(a.status_code,200)
        self.assertIn(b"Use passkey",a.data)
        operator=self.client.get("/staging-operator",
                                 base_url="https://"+STAGE)
        self.assertEqual(operator.status_code,200)
        self.assertIn(b"two one-use test invitations",operator.data)
        self.assertNotIn(KEY.encode(),operator.data)
        js=self.client.get("/assets/staging-operator.js",
                           base_url="https://"+STAGE)
        self.assertEqual(js.status_code,200)
        self.assertIn(b"cache: 'no-store'",js.data)
        for forbidden in (b"localStorage",b"sessionStorage",b"document.cookie",
                          b"console.log",b"innerHTML"):
            self.assertNotIn(forbidden,js.data)

    def test_valid_secret_only_mints_two_single_use_invites(self):
        r=self.post()
        self.assertEqual(r.status_code,200,r.get_data(as_text=True))
        data=r.get_json()
        self.assertEqual(data["maxTestUsers"],2)
        self.assertTrue(data["syntheticOnly"])
        self.assertFalse(data["publicBrokerageEnabled"])
        self.assertFalse(data["tradingEnabled"])
        invites=data["invitations"]
        self.assertEqual(len(invites),2)
        self.assertNotEqual(invites[0],invites[1])
        self.assertTrue(all(len(i)==43 for i in invites))
        self.assertEqual(self.post().status_code,403)
        self.assertEqual(self.post(key="W"*43).status_code,403)
        with self.app.database() as db:
            count=db.execute(
                "SELECT COUNT(*) FROM tenant_signup_invites").fetchone()[0]
            self.assertEqual(count,2)

    def test_cross_origin_cross_host_and_unknown_auth_are_refused(self):
        self.assertEqual(self.post(host=OWNER).status_code,404)
        self.assertEqual(self.post(origin="https://malicious.example").status_code,403)
        self.assertEqual(self.post(body={"more":True}).status_code,404)
        self.assertEqual(self.post(key="BadKey").status_code,403)
        self.assertEqual(self.post(key="B"*43).status_code,403)
        self.assertEqual(self.client.get("/staging-operator",
                         base_url="https://"+OWNER).status_code,404)
        self.assertEqual(self.client.get(
            "/.well-known/assetlinks.json",base_url="https://"+STAGE
            ).get_json()[0]["target"]["package_name"],
            "com.edgepilot.mobile.staging")

    def test_production_mode_never_opens_operator_endpoint(self):
        with patch.dict(os.environ,{"EDGE_ISOLATED_STAGING":"false"}):
            index=self.client.get("/",base_url="https://"+OWNER)
            self.assertEqual(index.status_code,200)
            self.assertIn(b"EdgePilot",index.data)
            self.assertEqual(self.client.get("/staging-operator",
                         base_url="https://"+OWNER).status_code,404)
            self.assertEqual(self.post().status_code,404)

    def test_missing_or_malformed_operator_digest_refuses(self):
        for value in ("","zzzz", "A"*64, "0"*63):
            with self.subTest(value=value), patch.dict(
                    os.environ,{"EDGE_STAGING_OPERATOR_SHA256":value}):
                self.assertEqual(self.post().status_code,403)
                self.assertEqual(self.client.get("/staging-operator",
                    base_url="https://"+STAGE).status_code,404)

    def test_rate_limit_invalid_auth_never_enables_brokerage(self):
        for _ in range(6):
            self.assertEqual(self.post(key="B"*43).status_code,403)
        self.assertEqual(self.post().status_code,403)
        result=staging_operator.issue_two(
            self.db,KEY,DIGEST,source="independent-caller")
        self.assertEqual(len(result["invitations"]),2)
        self.assertFalse(result["tradingEnabled"])

    def test_two_parallel_issuers_cannot_mint_more_than_two(self):
        from concurrent.futures import ThreadPoolExecutor
        def attempt(n):
            try:
                return staging_operator.issue_two(
                    self.db,KEY,DIGEST,source="independent-"+str(n))
            except staging_operator.StagingOperatorDenied:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(attempt,range(2)))
        self.assertEqual(sum(x is not None for x in results),1)
        self.assertEqual(sum(len(x["invitations"]) if x else 0
                             for x in results),2)


if __name__=="__main__":
    unittest.main()
