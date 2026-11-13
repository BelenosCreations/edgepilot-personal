"""v0.2.90 owner-only market-quote read, synthetic HTTP exclusively."""
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet
from engine import (
    identity_auth, tenant_foundation, tenant_public_vault,
    tenant_public_live_readonly as public, owner_market_quotes as market,
)

NOW = datetime(2026, 11, 12, 20, 0, 0, tzinfo=timezone.utc)
KEY_OWNER = "SYNTHETIC-OWNER-PUBLIC-KEY-1234567890"
KEY_OTHER = "SYNTHETIC-OTHER-PUBLIC-KEY-1234567890"
ACCOUNT_OWNER = "SYNTHETIC-PUBLIC-OWNER"
ACCOUNT_OTHER = "SYNTHETIC-PUBLIC-OTHER"
TOKENS = {KEY_OWNER:"SYNTHETIC-BEARER-OWNER-123456789012345",
          KEY_OTHER:"SYNTHETIC-BEARER-OTHER-123456789012345"}


class FakeReply:
    def __init__(self, data, status=200):
        self.value = data
        self.status_code = status

    def json(self):
        return self.value


class FakeOnly:
    def __init__(self):
        self.calls = []
        self.mutate = None
        self.outcome = "SUCCESS"
        self.instrument_override = None
        self.last_time = "2026-11-12T19:59:55Z"
        self.omit_bid = False
        self.missing_last_time = False
        self.crossed_book = False
        self.omit_side_timestamps = False

    def post(self, url, *, json, timeout, headers=None):
        self.calls.append(("POST",url))
        if url == public.BASE+public.AUTH_PATH:
            self_key = json["secret"]
            return FakeReply({"accessToken":TOKENS[self_key]})
        if "/marketdata/" not in url or not url.endswith("/quotes"):
            raise AssertionError("Unexpected synthetic network call")
        if headers is None or not headers["Authorization"].startswith("Bearer "):
            raise AssertionError("Missing provider session token")
        if timeout != public.TIMEOUT or set(json)!={"instruments"}:
            raise AssertionError("Unexpected provider request")
        instrument = json["instruments"][0]
        if len(json["instruments"])!=1 or set(instrument)!={"symbol","type"}:
            raise AssertionError("Only one evidence-backed instrument allowed")
        account=ACCOUNT_OWNER if ACCOUNT_OWNER in url else ACCOUNT_OTHER
        if account not in url:
            raise AssertionError("Mismatched fake account")
        if self.mutate:
            action=self.mutate
            self.mutate=None
            action()
        requested=self.instrument_override or dict(instrument)
        q = {
            "instrument": requested, "outcome": self.outcome,
            "last": "2.01",
            "lastTimestamp": self.last_time,
            "bid": "2.00", "bidTimestamp": "2026-11-12T19:59:54Z",
            "ask": "2.02", "askTimestamp": "2026-11-12T19:59:56Z",
        }
        if self.omit_bid:
            q["bid"]=None
            q.pop("bidTimestamp")
        if self.crossed_book:
            q["bid"]="2.50"
        if self.missing_last_time:
            q.pop("lastTimestamp")
        if self.omit_side_timestamps:
            q.pop("bidTimestamp", None)
            q.pop("askTimestamp", None)
        return FakeReply({"quotes":[q]})

    def get(self, url, *, headers, timeout):
        self.calls.append(("GET",url))
        if url != public.BASE+public.LIST_PATH or timeout != public.TIMEOUT:
            raise AssertionError("Unlisted fake provider GET")
        token=headers["Authorization"].removeprefix("Bearer ")
        account=ACCOUNT_OWNER if token == TOKENS[KEY_OWNER] else (
            ACCOUNT_OTHER if token == TOKENS[KEY_OTHER] else None)
        if account is None:
            raise AssertionError("Unknown fake token")
        return FakeReply({"accounts":[{"accountId":account,"accountType":"BROKERAGE"}]})


class SyntheticOwnerQuotesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=self.tmp.name+"/tenant.db"
        tenant_foundation.setup(self.path)
        identity_auth.setup(self.path)
        tenant_public_vault.setup(self.path)
        public.setup(self.path)
        self.store=tenant_foundation.TenantStore(
            self.path,credential_key=Fernet.generate_key().decode())
        self.owner=self.store.provision_user("Owner","owner")
        self.member=self.store.provision_user("Member","member")
        self.identities=identity_auth.IdentityStore(self.path)
        self.identities.provision(self.owner,"owner_v090","test-owner-password-safe-v090")
        self.identities.provision(self.member,"member_v090","test-member-password-safe-v090")
        self.a=self.identities.authenticate(
            "owner_v090","test-owner-password-safe-v090","owner-phone")
        self.b=self.identities.authenticate(
            "member_v090","test-member-password-safe-v090","member-phone")
        self.vault=tenant_public_vault.TenantPublicVault(
            self.path,self.identities,credential_key=Fernet.generate_key().decode())
        self.fake=FakeOnly()
        self.adapter=public.TenantPublicReadOnly(
            self.path,self.identities,self.vault,http=self.fake,
            clock=lambda:1900000000)
        self.quotes=market.OwnerMarketQuotes(self.adapter,clock=lambda:NOW)
        self.connection_a=self.vault.save(
            self.a["token"],self.a["csrf"],KEY_OWNER)["connectionId"]
        self.connection_b=self.vault.save(
            self.b["token"],self.b["csrf"],KEY_OTHER)["connectionId"]
        self.account_a=self.adapter.link_verified(
            self.a["token"],self.a["csrf"],self.connection_a,
            ACCOUNT_OWNER,"Owner Public")["accountId"]
        self.account_b=self.adapter.link_verified(
            self.b["token"],self.b["csrf"],self.connection_b,
            ACCOUNT_OTHER,"Member Public")["accountId"]
        self.fake.calls.clear()

    def tearDown(self):
        self.tmp.cleanup()

    def lookup(self, *, token=None, account=None, symbol="AAPL", instrument="EQUITY"):
        return self.quotes.one(token or self.a["token"],
                               account or self.account_a,symbol=symbol,
                               instrument_type=instrument)

    def test_trustworthy_manual_one_quote_no_persistence_or_execution(self):
        v=self.lookup()
        self.assertEqual(v["provider"],"Public API")
        self.assertEqual(v["symbol"],"AAPL")
        self.assertEqual(v["last"],"2.01")
        self.assertEqual(v["bid"],"2.00")
        self.assertEqual(v["ask"],"2.02")
        self.assertTrue(v["lastFresh"])
        self.assertTrue(v["twoSidedFresh"])
        self.assertFalse(v["paperFillEligible"])
        self.assertFalse(v["cacheRightsVerified"])
        self.assertFalse(v["executable"])
        self.assertFalse(v["ordersEnabled"])
        self.assertFalse(v["transfersEnabled"])
        self.assertNotIn(TOKENS[KEY_OWNER],str(v))
        self.assertNotIn(ACCOUNT_OWNER,str(v))
        self.assertEqual(len(self.fake.calls),3)
        self.assertTrue(self.fake.calls[-1][1].endswith(
            "/marketdata/"+ACCOUNT_OWNER+"/quotes"))
        with sqlite3.connect(self.path) as db:
            tables={r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("tenant_paper_events",tables)
        self.assertNotIn("owner_market_quote_cache",tables)
        self.assertFalse(any("order" in url.lower() or "transfer" in url.lower()
                             for _,url in self.fake.calls))

    def test_different_user_and_account_cannot_be_cross_accessed(self):
        for token,account in ((self.b["token"],self.account_a),
                              (self.a["token"],self.account_b)):
            with self.subTest(token=token[:4]):
                with self.assertRaises(market.OwnerQuoteUnavailable):
                    self.lookup(token=token,account=account)
        m=self.lookup(token=self.b["token"],account=self.account_b)
        self.assertEqual(m["accountId"],self.account_b)
        self.assertEqual(m["provider"],"Public API")
        self.assertNotIn(ACCOUNT_OTHER,str(m))

    def test_bad_quote_provenance_missing_and_crossed_prices_fail_closed(self):
        for setting,value in (
            ("outcome","FAILURE"),
            ("instrument_override",{"symbol":"OTHER","type":"EQUITY"}),
            ("missing_last_time",True),
            ("crossed_book",True),
            ("last_time","2026-11-12T20:00:05Z"),
        ):
            previous=getattr(self.fake,setting)
            setattr(self.fake,setting,value)
            with self.subTest(setting=setting):
                with self.assertRaises(market.OwnerQuoteUnavailable):
                    self.lookup()
            setattr(self.fake,setting,previous)
        self.fake.omit_bid=True
        v=self.lookup()
        self.assertIsNone(v["bid"])
        self.assertFalse(v["twoSidedFresh"])
        self.assertEqual(v["ask"],"2.02")
        self.fake.omit_bid=False
        self.fake.last_time="2026-11-11T20:00:00Z"
        v=self.lookup()
        self.assertFalse(v["lastFresh"])
        self.assertTrue(v["sourceReportedOnly"])
        self.assertFalse(v["paperFillEligible"])

    def test_public_side_prices_without_optional_side_timestamps_remain_undated(self):
        # Public's documented equity example contains bid/ask prices but can
        # omit their timestamps. Do not discard an otherwise validated last
        # price or pretend such a book is fresh/executable.
        self.fake.omit_side_timestamps = True
        quote = self.lookup(symbol="MSFT")
        self.assertEqual(quote["symbol"], "MSFT")
        self.assertEqual(quote["last"], "2.01")
        self.assertEqual(quote["bid"], "2.00")
        self.assertEqual(quote["ask"], "2.02")
        self.assertIsNone(quote["bidTimestamp"])
        self.assertIsNone(quote["askTimestamp"])
        self.assertTrue(quote["lastFresh"])
        self.assertFalse(quote["twoSidedFresh"])
        self.assertFalse(quote["paperFillEligible"])
        self.assertFalse(quote["executable"])

    def test_invalid_symbol_type_and_unknown_account_never_contact_marketdata(self):
        for symbol,kind in (("","EQUITY"),("../orders","EQUITY"),
                            ("AAPL","OPTION"),("AAPL","EVENTCONTRACT"),
                            (3,"EQUITY"),("AAPL","equity")):
            with self.subTest(symbol=symbol,kind=kind):
                with self.assertRaises(market.OwnerQuoteUnavailable):
                    self.lookup(symbol=symbol,instrument=kind)
        self.assertFalse(any("/marketdata/" in url for _,url in self.fake.calls))
        with self.assertRaises(market.OwnerQuoteUnavailable):
            self.lookup(account="00000000-0000-0000-0000-000000000000")
        self.assertFalse(any("/marketdata/" in url for _,url in self.fake.calls))

    def test_revocation_or_logout_while_request_is_in_flight_refused(self):
        self.fake.mutate=lambda: self._revoke_connection()
        with self.assertRaises(market.OwnerQuoteUnavailable):
            self.lookup()
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE tenant_connections SET revoked_at=NULL WHERE connection_id=?",
                       (self.connection_a,))
        self.fake.mutate=lambda: self.identities.revoke(self.a["token"])
        with self.assertRaises(market.OwnerQuoteUnavailable):
            self.lookup()

    def _revoke_connection(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE tenant_connections SET revoked_at=? WHERE connection_id=?",
                       ("2026-11-12T20:00:00Z",self.connection_a))

    def test_only_manual_identity_protected_ui_and_no_paper_or_live_orders(self):
        root=Path(__file__).resolve().parents[1]
        app=(root/"app.py").read_text()
        js=(root/"static/assets/owner-dashboard.js").read_text()
        page=(root/"static/owner-dashboard.html").read_text()
        self.assertIn("@app.post('/api/identity/public/read/accounts/<account_id>/quote')",app)
        self.assertIn("solo_owner_portfolio.active_for_owner(TENANT_DB,g.edge_identity)",app)
        self.assertIn("request.headers.get('X-Edge-Identity-CSRF','')",app)
        self.assertIn("same_origin_request()",app)
        self.assertIn('el("loadQuote").addEventListener("click"',js)
        self.assertIn("paperFillEligible !== false",js)
        self.assertIn("cacheRightsVerified !== false",js)
        self.assertIn("Public API",page)
        self.assertNotIn("tenant_paper_ledger",app)
        self.assertNotIn("localStorage",js)
        self.assertNotIn("sessionStorage",js)
        self.assertNotIn("setInterval(",js)
        self.assertNotIn("innerHTML",js)


if __name__ == "__main__":
    unittest.main()
