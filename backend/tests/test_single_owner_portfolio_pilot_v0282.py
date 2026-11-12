"""v0.2.82 single-owner read-only Public pilot: synthetic, no real network.

The user may keep the multi-user enrollment architecture and existing flags.
Only an independently enabled ONE-owner research pilot may show holdings;
all members, the legacy login and real order/transfer routes stay denied.
"""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from cryptography.fernet import Fernet
from engine import identity_auth, tenant_foundation
from engine import solo_owner_portfolio as solo
from engine import shared_storage_cutover as storage


PROBE = r"""
import json
import os
from pathlib import Path
import sqlite3
import sys

from engine import shared_storage_cutover as storage
from engine import tenant_foundation, identity_auth
from engine import tenant_public_live_readonly as public

root=Path(sys.argv[1])
storage.PERSISTENT_ROOT=root
import app
assert app.DB==root/"edgepilot.db"
assert app.TENANT_DB==root/"edgepilot-tenants.db"
assert app.tenant_public_discovery_only is True
assert app.solo_owner_portfolio_enabled is True
assert app.family_invite_coexistence_enabled is True
assert app.permanent_admin_invites_enabled is True

KEY="SYNTHETIC-OWNER-KEY-A-0123456789-000000"
TOKEN="SYNTHETIC-TOKEN-FOR-OWNER-2026-AAAAAA"
BROKER="SYNTHETIC-OWNER-PUBLIC-ACCOUNT"
class FakePublic:
    def __init__(self): self.calls=[]
    @staticmethod
    def response(data):
        class Response:
            status_code=200
            def json(self): return data
        return Response()
    def post(self,url,*,json,timeout):
        assert url==public.BASE+public.AUTH_PATH
        assert json["secret"]==KEY
        assert json["validityInMinutes"]==5
        assert timeout==public.TIMEOUT
        self.calls.append(("POST","TOKEN"))
        return self.response({"accessToken":TOKEN})
    def get(self,url,*,headers,timeout):
        assert headers.get("Authorization")=="Bearer "+TOKEN
        assert timeout==public.TIMEOUT
        if url==public.BASE+public.LIST_PATH:
            self.calls.append(("GET","LIST"))
            return self.response({"accounts":[{
                "accountId":BROKER,"accountType":"BROKERAGE"}]})
        if url==public.BASE+"/userapigateway/trading/"+BROKER+"/portfolio/v2":
            self.calls.append(("GET","PORTFOLIO"))
            return self.response({
                "totalAccountValue":"210.35",
                "positions":[{
                    "instrument":{"symbol":"SPY"},
                    "quantity":"0.5",
                    "currentValue":"210.35"
                }]
            })
        raise AssertionError("Only allowed Public account/portfolio endpoints")
fake=FakePublic()
app.tenant_public_reader.http=fake

ORIGIN="https://edgepilot.example.test"
a=app.app.test_client()
legacy=app.app.test_client()
def post(client,path,payload,csrf=None):
    headers={"Origin":ORIGIN}
    if csrf is not None: headers["X-Edge-Identity-CSRF"]=csrf
    return client.post(path,headers=headers,base_url=ORIGIN,json=payload)
def get(client,path):
    return client.get(path,base_url=ORIGIN)

assert post(legacy,"/api/login",{"accessToken":os.environ["EDGE_APP_TOKEN"]}).status_code==200
assert get(legacy,"/api/session").status_code==200
assert get(legacy,"/api/identity/accounts").status_code==401
owner_login=post(a,"/api/identity/login",{
    "username":"single_owner",
    "password":"synthetic-owner-password-long-2026"})
assert owner_login.status_code==200,owner_login.get_data(as_text=True)
csrf=owner_login.json["csrf"]
saved=post(a,"/api/identity/public/connections",{"secret":KEY},csrf)
assert saved.status_code==201,saved.get_data(as_text=True)
cid=saved.json["connectionId"]
discovered=get(a,"/api/identity/public/read/connections/"+cid+"/accounts")
assert discovered.status_code==200,discovered.get_data(as_text=True)
assert discovered.json["accounts"][0]["accountId"]==BROKER
linked=post(a,"/api/identity/public/read/connections/"+cid+"/accounts",{
    "accountId":BROKER,"label":"Owner's Public account"},csrf)
assert linked.status_code==200,linked.get_data(as_text=True)
aid=linked.json["accountId"]
accounts=get(a,"/api/identity/accounts")
assert accounts.status_code==200
assert accounts.json["readOnly"] is True
assert accounts.json["discoveryOnlyPilot"] is True
assert accounts.json["soloOwnerPortfolioAvailable"] is True
assert accounts.json["accounts"][0]["account_id"]==aid
assert get(legacy,"/api/identity/public/read/accounts/"+aid+"/portfolio").status_code==401
portfolio=get(a,"/api/identity/public/read/accounts/"+aid+"/portfolio")
assert portfolio.status_code==200,portfolio.get_data(as_text=True)
assert portfolio.json=={
    "accountId":aid,"balance":"210.35",
    "holdings":[{"symbol":"SPY","quantity":"0.5","currentValue":"210.35"}],
    "readOnly":True,"ordersEnabled":False,"transfersEnabled":False}
assert all(route not in str(fake.calls) for route in ("ORDER","TRANSFER","EXECUTE"))
assert get(a,"/api/identity/accounts/"+aid+"/monitor/preview").status_code==404
assert a.put("/api/identity/accounts/"+aid+"/monitor/watchlist",
    base_url=ORIGIN,headers={"Origin":ORIGIN,
        "X-Edge-Identity-CSRF":csrf},json={"symbols":["SPY"]}).status_code==404
assert get(a,"/api/automation/status").status_code==401

# Newly registered members revoke the TEMPORARY solo pilot immediately.
# They do not lose their enrollment or interfere with original login.
members=tenant_foundation.TenantStore(str(app.TENANT_DB))
member_id=members.provision_user("Future family member","member")
identity_auth.IdentityStore(str(app.TENANT_DB)).provision(
    member_id,"future_member","synthetic-future-member-password-2026")
post_count=len(fake.calls)
after=get(a,"/api/identity/accounts")
assert after.status_code==200
assert after.json["soloOwnerPortfolioAvailable"] is False
assert get(a,"/api/identity/public/read/accounts/"+aid+"/portfolio").status_code==404
assert len(fake.calls)==post_count
assert get(legacy,"/api/session").status_code==200
with sqlite3.connect(app.DB) as db:
    legacy_secret=db.execute(
        "SELECT ciphertext FROM broker_credentials WHERE provider='public'").fetchone()[0]
    assert legacy_secret==b"SYNTHETIC-LEGACY-CIPHERTEXT"
    assert db.execute(
        "SELECT name FROM sqlite_master WHERE name='tenant_users'").fetchone() is None
with sqlite3.connect(app.TENANT_DB) as db:
    assert db.execute("SELECT COUNT(*) FROM tenant_users").fetchone()[0]==2
    stored=db.execute(
        "SELECT credential_ciphertext FROM tenant_connections").fetchone()[0]
    assert KEY.encode() not in stored

print(json.dumps({
    "owner_readonly_portfolio_verified":True,
    "owner_account_scoped":True,
    "legacy_login_preserved":True,
    "additional_member_disables_solo_pilot":True,
    "no_real_provider_network":True,
    "live_orders_allowed":False,
    "autonomous_orders_allowed":False,
    "bank_transfers_allowed":False,
    "real_production_activation":False
}))
"""

class SingleOwnerPortfolioPilotTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="edgepilot-solo-owner-")
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.legacy=self.root/"edgepilot.db"
        self.tenant=self.root/"edgepilot-tenants.db"
        with sqlite3.connect(self.legacy) as db:
            db.execute("CREATE TABLE settings(k TEXT PRIMARY KEY, v TEXT)")
            db.execute("CREATE TABLE broker_credentials(provider TEXT PRIMARY KEY,ciphertext BLOB)")
            db.execute("CREATE TABLE orders(id TEXT)")
            db.execute("CREATE TABLE activity(id INTEGER)")
            db.execute("INSERT INTO broker_credentials VALUES('public',?)",
                       (b"SYNTHETIC-LEGACY-CIPHERTEXT",))
        tenant_foundation.setup(str(self.tenant))
        identity_auth.setup(str(self.tenant))
        owner=tenant_foundation.TenantStore(str(self.tenant)).provision_user(
            "Owner test","owner")
        identity_auth.IdentityStore(str(self.tenant)).provision(
            owner,"single_owner","synthetic-owner-password-long-2026")
        self.owner=owner
        os.chmod(self.legacy,0o600)
        os.chmod(self.tenant,0o600)
        self.env={
            **{name:"true" for name in solo.REQUIRED},
            **{name:"false" for name in solo.FORBIDDEN},
            "EDGE_FAMILY_INVITE_COEXISTENCE_ENABLED":"true",
            "EDGE_TENANT_SIGNUP_ENABLED":"true",
            "EDGE_PERMANENT_OWNER_INVITES_ENABLED":"true",
            solo.FLAG:"true",
            "EDGE_DB_PATH":str(self.legacy),
            "EDGE_TENANT_DB_PATH":str(self.tenant),
            "EDGE_CREDENTIAL_KEY":Fernet.generate_key().decode(),
            "EDGE_APP_TOKEN":"SYNTHETIC-LEGACY-TOKEN-2026-0123456789",
        }

    def test_owner_readonly_portfolio_only_with_one_identity(self):
        self.assertTrue(solo.validate_pilot(
            self.env,self.legacy,self.tenant))
        self.assertTrue(solo.active_for_owner(
            self.tenant,{"user_id":self.owner,"role":"owner"}))
        env={**os.environ,**self.env}
        child=subprocess.run(
            [sys.executable,"-c",PROBE,str(self.root)],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env,capture_output=True,text=True,timeout=75)
        self.assertEqual(child.returncode,0,child.stderr[-1800:]+child.stdout[-400:])
        response=json.loads(child.stdout.strip().splitlines()[-1])
        self.assertTrue(all(response[key] for key in (
            "owner_readonly_portfolio_verified","owner_account_scoped",
            "legacy_login_preserved","additional_member_disables_solo_pilot",
            "no_real_provider_network")))
        for flag in ("live_orders_allowed","autonomous_orders_allowed",
                     "bank_transfers_allowed","real_production_activation"):
            self.assertFalse(response[flag])
        self.assertNotIn("SYNTHETIC-OWNER-KEY",child.stdout)

    def test_default_off_and_all_forbidden_configurations_fail_closed(self):
        self.assertFalse(solo.validate_pilot(
            {**self.env,solo.FLAG:"false"},self.legacy,self.tenant))
        self.assertFalse(solo.validate_pilot(
            {k:v for k,v in self.env.items() if k!=solo.FLAG},
            self.legacy,self.tenant))
        for flag in solo.REQUIRED:
            with self.subTest(missing=flag):
                with self.assertRaises(solo.SoloOwnerPortfolioDenied):
                    solo.validate_pilot(
                        {**self.env,flag:"false"},self.legacy,self.tenant)
        for flag in solo.FORBIDDEN:
            with self.subTest(unsafe=flag):
                with self.assertRaises(solo.SoloOwnerPortfolioDenied):
                    solo.validate_pilot(
                        {**self.env,flag:"true"},self.legacy,self.tenant)
        with self.assertRaises(solo.SoloOwnerPortfolioDenied):
            solo.validate_pilot(
                {**self.env,"EDGE_TENANT_SIGNUP_ENABLED":"false"},
                self.legacy,self.tenant)

    def test_members_and_malformed_identity_never_gain_solo_access(self):
        for principal in (
            {"user_id":self.owner,"role":"member"},
            {"user_id":self.owner,"role":"admin"},
            {"user_id":"someone_else","role":"owner"},
            {"role":"owner"},
            None,{},False
        ):
            with self.subTest(principal=principal):
                self.assertFalse(solo.active_for_owner(self.tenant,principal))
        member=tenant_foundation.TenantStore(str(self.tenant)).provision_user(
            "Other user","member")
        identity_auth.IdentityStore(str(self.tenant)).provision(
            member,"other_user","synthetic-other-password-long-2026")
        self.assertFalse(solo.active_for_owner(
            self.tenant,{"user_id":self.owner,"role":"owner"}))


if __name__=="__main__":
    unittest.main()
