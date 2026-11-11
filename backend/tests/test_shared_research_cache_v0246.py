"""v0.2.46: zero-paid-AI licensed shared feature cache, synthetic only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from engine import (account_scope, identity_auth, research_intelligence,
                    shared_research_cache, tenant_foundation)

R = research_intelligence


class SharedResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="edge-shared-research-")
        self.path = self.tmp.name + "/synthetic.db"
        tenant_foundation.setup(self.path)
        identity_auth.setup(self.path)
        account_scope.setup(self.path)
        shared_research_cache.setup(self.path)
        self.identities = identity_auth.IdentityStore(self.path)
        self.store = tenant_foundation.TenantStore(
            self.path, credential_key=Fernet.generate_key().decode())
        self.cache = shared_research_cache.SharedResearchCache(
            self.path, self.identities)
        self.people = [self.make_member(i) for i in range(2)]
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.no_network = patch("requests.sessions.Session.request",
                                side_effect=AssertionError("No network permitted"))
        self.no_network.start()

    def tearDown(self):
        self.no_network.stop()
        self.tmp.cleanup()

    def make_member(self, i):
        uid = self.store.provision_user("Local test member " + str(i))
        user = "research_synthetic_" + str(i)
        password = "synthetic-test-member-passphrase-" + str(i)
        self.identities.provision(uid, user, password)
        session = self.identities.authenticate(user, password, "sim_" + str(i))
        self.assertIsNotNone(session)
        connection = self.store.add_connection(
            uid, "fake-public-key-SYNTHETIC-NEVER-LIVE-" + str(i))
        account = self.store.link_account(uid, connection,
                                          "fake-public-" + str(i), "Test account")
        self.store.account_setting(uid, account, "watchlist_csv", "AAPL,MSFT")
        return {"uid": uid, "session": session, "account": account,
                "connection": connection}

    def rights(self, **values):
        r = {"provider": "synthetic-provider", "analysis": True,
             "cache": True, "redistribute": True, "coverageVerified": True}
        r.update(values)
        return r

    def sample(self, *, at=None, asset="stock", **change):
        at = self.now - timedelta(seconds=2) if at is None else at
        payload = {"assetClass": asset, "symbol": "AAPL",
                   "rights": self.rights(),
                   "observedAt": at.isoformat(), "receivedAt": at.isoformat(),
                   "bid": "99.9", "ask": "100.1", "last": "100",
                   "volume": "1200", "state": "open"}
        payload.update(change)
        return payload

    def read(self, i, *, rights=None, account=None, symbol="AAPL", now=None):
        p = self.people[i]
        return self.cache.for_account(
            p["session"]["token"], p["session"]["csrf"],
            p["account"] if account is None else account,
            asset_class="stock", symbol=symbol,
            rights=self.rights() if rights is None else rights,
            now=self.now if now is None else now)

    def test_shared_public_feature_but_no_personal_information_or_orders(self):
        self.cache.publish(self.sample(), now=self.now)
        a, b = self.read(0), self.read(1)
        self.assertEqual(a["signal"], b["signal"])
        self.assertEqual(a["signal"]["feature"], "quoted-spread-bps")
        self.assertEqual(a["signal"]["predictedProbability"], None)
        self.assertFalse(a["signal"]["orderAllowed"])
        self.assertFalse(a["signal"]["executableQuote"])
        self.assertEqual(a["aiCalls"], 0)
        self.assertFalse(a["brokerRequestMade"])
        blob = json.dumps(a)
        for p in self.people:
            self.assertNotIn(p["uid"], blob)
            self.assertNotIn(p["account"], blob)
            self.assertNotIn(p["session"]["token"], blob)
        with sqlite3.connect(self.path) as con:
            stored = con.execute("SELECT payload_json FROM shared_research_signals").fetchone()[0]
        self.assertNotIn("fake-public-key", stored)
        self.assertNotIn("portfolio", stored)
        self.assertEqual(a["signal"]["symbol"], "AAPL")

    def test_unverified_or_unlicensed_observations_are_never_cached(self):
        for rights in (self.rights(redistribute=False), self.rights(cache=False),
                       self.rights(analysis=False), self.rights(coverageVerified=False)):
            with self.subTest(rights=rights), self.assertRaises(R.ResearchUnavailable):
                self.cache.publish(self.sample(rights=rights), now=self.now)
        for extra in ({"userId": "someone"}, {"accountId": "private"},
                      {"holdings": ["secret"]}):
            with self.subTest(extra=extra), self.assertRaises(R.ResearchUnavailable):
                self.cache.publish(self.sample(**extra), now=self.now)
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM shared_research_signals").fetchone()[0], 0)

    def test_expired_stale_crossed_closed_and_future_data_are_denied(self):
        inputs = (
            self.sample(at=self.now - timedelta(minutes=10)),
            self.sample(at=self.now + timedelta(seconds=5)),
            self.sample(bid="102", ask="101"),
            self.sample(state="halted"),
            self.sample(receivedAt=(self.now + timedelta(seconds=1)).isoformat()),
        )
        for item in inputs:
            with self.assertRaises(R.ResearchUnavailable):
                self.cache.publish(item, now=self.now)
        self.cache.publish(self.sample(), now=self.now)
        with self.assertRaises(shared_research_cache.SharedResearchDenied):
            self.read(0, now=self.now + timedelta(minutes=3))

    def test_cross_user_account_access_and_bad_session_fail_closed(self):
        self.cache.publish(self.sample(), now=self.now)
        with self.assertRaises(shared_research_cache.SharedResearchDenied):
            self.read(0, account=self.people[1]["account"])
        self.store.account_setting(self.people[1]["uid"], self.people[1]["account"],
                                   "watchlist_csv", "MSFT")
        with self.assertRaises(shared_research_cache.SharedResearchDenied):
            self.read(1)
        with self.assertRaises(shared_research_cache.SharedResearchDenied):
            self.cache.for_account(
                self.people[0]["session"]["token"],
                self.people[1]["session"]["csrf"],
                self.people[0]["account"], asset_class="stock", symbol="AAPL",
                rights=self.rights(), now=self.now)
        with self.assertRaises(shared_research_cache.SharedResearchDenied):
            self.read(0, rights=self.rights(redistribute=False))
        with self.assertRaises(shared_research_cache.SharedResearchDenied):
            self.read(0, rights=self.rights(provider="wrong-provider"))
        self.identities.revoke(self.people[0]["session"]["token"])
        with self.assertRaises(shared_research_cache.SharedResearchDenied):
            self.read(0)

    def test_newer_sample_wins_and_provider_invalidation_blocks_reads(self):
        first = self.sample(at=self.now - timedelta(seconds=3))
        second = self.sample(at=self.now - timedelta(seconds=1), bid="99", ask="101")
        self.cache.publish(second, now=self.now)
        self.cache.publish(first, now=self.now)
        current = self.read(0)["signal"]
        self.assertEqual(current["observedAt"], second["observedAt"])
        self.assertEqual(current["quotedSpreadBps"], str(
            (R.decimal("101", "a") - R.decimal("99", "b")) /
            R.decimal("101", "a") * 10000))
        self.assertEqual(self.cache.invalidate_provider("synthetic-provider"), 1)
        with self.assertRaises(shared_research_cache.SharedResearchDenied):
            self.read(0)

    def test_crypto_and_prediction_are_not_implied_account_entitlements(self):
        self.cache.publish(self.sample(asset="crypto"), now=self.now)
        p = self.people[0]
        for asset in ("crypto", "prediction"):
            with self.assertRaises(shared_research_cache.SharedResearchDenied):
                self.cache.for_account(
                    p["session"]["token"], p["session"]["csrf"], p["account"],
                    asset_class=asset, symbol="AAPL",
                    rights=self.rights(), now=self.now)

    def test_ten_synthetic_members_reuse_one_public_signal_no_ai(self):
        for i in range(2, 10):
            self.people.append(self.make_member(i))
        self.cache.publish(self.sample(), now=self.now)
        def one(i):
            return self.read(i)
        with ThreadPoolExecutor(max_workers=10) as pool:
            outputs = list(pool.map(one, range(10)))
        self.assertEqual(len(outputs), 10)
        self.assertTrue(all(out["signal"] == outputs[0]["signal"] for out in outputs))
        self.assertTrue(all(out["aiCalls"] == 0 for out in outputs))
        self.assertTrue(all(out["brokerRequestMade"] is False for out in outputs))
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM shared_research_signals").fetchone()[0], 1)

    def test_missing_schema_does_not_initialize_a_production_database(self):
        with self.assertRaises(RuntimeError):
            shared_research_cache.setup(str(Path(self.tmp.name) / "uninitialized.db"))


if __name__ == "__main__":
    unittest.main()
