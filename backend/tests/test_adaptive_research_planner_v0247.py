"""v0.2.47 offline provider quota and adaptive research planning tests."""
from datetime import datetime, timedelta, timezone
import unittest
import uuid

from engine import adaptive_research_planner as planner

NOW = datetime.now(timezone.utc).replace(microsecond=0)


class AdaptivePlanTests(unittest.TestCase):
    def setUp(self):
        self.users = [str(uuid.uuid4()) for _ in range(10)]
        self.rights = {
            "provider": "licensed-synthetic-provider",
            "analysis": True, "cache": True, "redistribute": True,
            "coverageVerified": True,
        }
        self.policy = {
            "rights": self.rights.copy(),
            "centralFetchVerified": True,
            "perMemberFetchVerified": False,
            "centralRequestsRemaining": 25,
            "memberRequestsRemaining": {},
            "cycleRequestLimit": 25,
            "quotaObservedAt": NOW.isoformat(),
            "backoffUntil": None,
        }

    def demand(self, i, *, asset="stock", symbol="AAPL", **other):
        result = {
            "memberRef": self.users[i],
            "provider": self.rights["provider"],
            "assetClass": asset, "symbol": symbol,
            "session": "continuous" if asset == "crypto" else "open",
            "entitlementVerified": True,
            "lastObservedAt": None, "expiresAt": None,
            "settlementVerified": False,
        }
        if asset == "prediction":
            result.update({
                "expiresAt": (NOW + timedelta(minutes=15)).isoformat(),
                "settlementVerified": True})
        result.update(other)
        return result

    def plan(self, ds, policy=None, now=None):
        return planner.propose_cycle(ds, policy=self.policy if policy is None else policy,
                                     now=NOW if now is None else now)

    def test_ten_members_one_licensed_shared_fetch_not_ten_calls(self):
        ds = [self.demand(i) for i in range(10)]
        plan = self.plan(ds)
        self.assertEqual(plan["proposedProviderCalls"], 1)
        self.assertEqual(plan["proposedTasks"][0]["scope"], "licensed-public-shared")
        self.assertEqual(set(plan["proposedTasks"][0]["internalMemberRefs"]), set(self.users))
        self.assertTrue(plan["nonAI"])
        self.assertEqual(plan["actualProviderCalls"], 0)
        self.assertFalse(plan["accountCredentialsAccessed"])
        self.assertFalse(plan["tradingAllowed"])
        self.assertFalse(plan["bankTransfersAllowed"])

    def test_no_redistribution_requires_individual_authorized_quotas(self):
        policy = dict(self.policy)
        policy["rights"] = dict(self.rights, redistribute=False)
        policy["perMemberFetchVerified"] = True
        policy["memberRequestsRemaining"] = {u: 1 for u in self.users}
        p = self.plan([self.demand(i) for i in range(10)], policy)
        self.assertEqual(p["proposedProviderCalls"], 10)
        self.assertTrue(all(t["scope"] == "member-isolated" for t in p["proposedTasks"]))
        self.assertTrue(all(len(t["internalMemberRefs"]) == 1 for t in p["proposedTasks"]))
        self.assertEqual(set(x["internalMemberRefs"][0] for x in p["proposedTasks"]),
                         set(self.users))
        policy["perMemberFetchVerified"] = False
        blocked = self.plan([self.demand(i) for i in range(10)], policy)
        self.assertEqual(blocked["proposedProviderCalls"], 0)
        self.assertEqual(blocked["skippedReasonCounts"]["fetch_authorization_unavailable"], 10)

    def test_session_entitlement_freshness_and_prediction_settlement(self):
        demands = [self.demand(0, symbol="AAPL"),
                   self.demand(1, symbol="MSFT", entitlementVerified=False),
                   self.demand(2, symbol="AMZN", session="closed"),
                   self.demand(3, symbol="TSLA",
                               lastObservedAt=(NOW - timedelta(seconds=30)).isoformat()),
                   self.demand(4, asset="prediction", symbol="EVENT",
                               expiresAt=(NOW + timedelta(seconds=35)).isoformat()),
                   self.demand(5, asset="crypto", symbol="BTC")]
        p = self.plan(demands)
        self.assertEqual(p["proposedProviderCalls"], 2)
        self.assertEqual({x["symbol"] for x in p["proposedTasks"]}, {"AAPL", "BTC"})
        self.assertEqual(p["skippedReasonCounts"], {
            "market_unavailable": 1, "recent_sample": 1,
            "settlement_or_expiry_unverified": 1, "unverified_entitlement": 1})

    def test_prediction_requires_settlement_and_respects_provider_license(self):
        p = self.plan([self.demand(0, asset="prediction", symbol="EVENT")])
        self.assertEqual(p["proposedProviderCalls"], 1)
        self.assertFalse(p["tradingAllowed"])
        q = self.plan([self.demand(0, asset="prediction", symbol="EVENT",
                                   settlementVerified=False)])
        self.assertEqual(q["proposedProviderCalls"], 0)

    def test_stale_quota_or_missing_explicit_permissions_fail_closed(self):
        for broken in (
            dict(self.policy, quotaObservedAt=(NOW - timedelta(minutes=10)).isoformat()),
            dict(self.policy, centralFetchVerified="true"),
            dict(self.policy, centralRequestsRemaining=-1),
            dict(self.policy, cycleRequestLimit=251),
            dict(self.policy, rights=dict(self.rights, analysis=False)),
            dict(self.policy, rights=dict(self.rights, coverageVerified=False)),
            {k: v for k, v in self.policy.items() if k != "quotaObservedAt"},
        ):
            with self.subTest(broken=broken), self.assertRaises(planner.PlanningUnavailable):
                self.plan([self.demand(0)], broken)

    def test_backoff_and_quota_limit_are_dormant_and_no_requests_are_made(self):
        p = dict(self.policy, backoffUntil=(NOW + timedelta(minutes=2)).isoformat())
        blocked = self.plan([self.demand(i) for i in range(10)], p)
        self.assertEqual(blocked["proposedProviderCalls"], 0)
        self.assertEqual(blocked["skippedReasonCounts"]["provider_backoff"], 10)
        p = dict(self.policy, centralRequestsRemaining=0)
        self.assertEqual(self.plan([self.demand(i) for i in range(10)], p)
                         ["proposedProviderCalls"], 0)
        p = dict(self.policy, centralRequestsRemaining=1, cycleRequestLimit=1)
        small = self.plan([self.demand(0, symbol="AAPL"),
                           self.demand(1, symbol="MSFT")], p)
        self.assertEqual(small["proposedProviderCalls"], 1)
        self.assertEqual(small["skippedReasonCounts"]["central_quota_or_cycle_exhausted"], 1)

    def test_duplicate_member_forbidden_fields_and_future_sample_fail_closed(self):
        for demand in (
            self.demand(0, userKey="not-allowed"),
            self.demand(0, holdings=["PRIVATE"]),
            self.demand(0, lastObservedAt=(NOW + timedelta(seconds=3)).isoformat()),
            self.demand(0, assetClass="unlicensed-market"),
            self.demand(0, memberRef="bad-uuid"),
            self.demand(0, provider="other"),
        ):
            with self.subTest(demand=demand), self.assertRaises(planner.PlanningUnavailable):
                self.plan([demand])
        with self.assertRaises(planner.PlanningUnavailable):
            self.plan([self.demand(0), self.demand(0)])

    def test_independent_member_quotas_and_fairness(self):
        rights = dict(self.rights, redistribute=False)
        p = dict(self.policy, rights=rights, perMemberFetchVerified=True,
                 memberRequestsRemaining={self.users[0]: 1, self.users[1]: 2},
                 cycleRequestLimit=2)
        ds = [self.demand(0, symbol="AAPL"), self.demand(0, symbol="MSFT"),
              self.demand(1, symbol="AAPL"), self.demand(1, symbol="MSFT")]
        result = self.plan(ds, p)
        self.assertEqual(result["proposedProviderCalls"], 2)
        self.assertEqual({t["internalMemberRefs"][0] for t in result["proposedTasks"]},
                         {self.users[0], self.users[1]})
        self.assertEqual(result["skippedReasonCounts"]["member_quota_or_cycle_exhausted"], 2)
        # No plan alters the provided source quota map.
        self.assertEqual(p["memberRequestsRemaining"][self.users[0]], 1)

    def test_too_many_requests_and_invalid_market_metadata_rejected(self):
        with self.assertRaises(planner.PlanningUnavailable):
            self.plan([self.demand(0)] * 1001)
        with self.assertRaises(planner.PlanningUnavailable):
            self.plan([self.demand(0, expiresAt=NOW.isoformat())])


if __name__ == "__main__":
    unittest.main()
