"""v0.2.49: ten-member dormant tier preferences cannot activate billing."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from engine import identity_auth, tenant_foundation, tenant_tier_intent


class TierIntentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="edge-tiers-")
        self.path = self.tmp.name + "/tenant.db"
        tenant_foundation.setup(self.path)
        identity_auth.setup(self.path)
        tenant_tier_intent.setup(self.path)
        self.auth = identity_auth.IdentityStore(self.path)
        self.intent = tenant_tier_intent.DormantTenantTierIntent(
            self.path, self.auth)
        self.users = [self.add(i) for i in range(10)]
        self.no_network = patch("requests.sessions.Session.request",
                                side_effect=AssertionError("No payment or provider network"))
        self.no_network.start()

    def tearDown(self):
        self.no_network.stop()
        self.tmp.cleanup()

    def add(self, i):
        uid = tenant_foundation.TenantStore(self.path).provision_user(
            "Synthetic private friend " + str(i))
        username = "synthetic_tier_friend_" + str(i)
        password = "strong-synthetic-tier-password-" + str(i)
        self.auth.provision(uid, username, password)
        session = self.auth.authenticate(username, password, "synthetic_" + str(i))
        self.assertIsNotNone(session)
        return uid, session

    def keys(self, i):
        return self.users[i][1]["token"], self.users[i][1]["csrf"]

    def test_default_free_is_dormant_and_no_paid_credential_or_rights(self):
        out = self.intent.status(*self.keys(0))
        self.assertEqual(out["requestedTierConcept"], "free")
        self.assertEqual(out["effectiveTier"], "free")
        self.assertTrue(out["tierActive"])
        for name in ("premiumGrantVerified", "paymentAuthorizationRecorded",
                     "subscriptionActive", "managedAiCreditsActive",
                     "ownerFundedAiAllocationActive", "aiKeyOrBudgetChanged",
                     "marketDataRightsChanged", "publicConnectionChanged",
                     "realTradingPermissionsChanged", "commercialDistributionEnabled",
                     "upgradeAvailableNow"):
            self.assertFalse(out[name])

    def test_ten_separate_requested_tiers_never_get_subscription(self):
        requested = ("plus", "pro", "custom", "free", "plus",
                     "pro", "custom", "free", "plus", "pro")
        def choose(i):
            return self.intent.choose_for_future_review(
                *self.keys(i), requested_tier=requested[i])
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(choose, range(10)))
        for i in range(10):
            out = self.intent.status(*self.keys(i))
            self.assertEqual(out["requestedTierConcept"], requested[i])
            self.assertEqual(out["effectiveTier"], "free")
            self.assertFalse(out["subscriptionActive"])
            self.assertFalse(out["managedAiCreditsActive"])
            self.assertFalse(out["paymentAuthorizationRecorded"])
            self.assertEqual(results[i], out)
        with sqlite3.connect(self.path) as con:
            rows = con.execute("SELECT user_id,requested_tier FROM tenant_tier_intents").fetchall()
        self.assertEqual(len(rows), 10)
        self.assertEqual({uid for uid, _ in rows}, {uid for uid, _ in self.users})

    def test_cross_member_csrf_theft_or_revocation_cannot_modify_any_tier(self):
        token0, csrf0 = self.keys(0)
        token1, csrf1 = self.keys(1)
        with self.assertRaises(tenant_tier_intent.EntitlementDenied):
            self.intent.choose_for_future_review(
                token0, csrf1, requested_tier="pro")
        self.assertEqual(self.intent.status(*self.keys(0))["requestedTierConcept"], "free")
        self.intent.choose_for_future_review(token1, csrf1, requested_tier="plus")
        self.assertEqual(self.intent.status(token0, csrf0)["requestedTierConcept"], "free")
        self.auth.revoke(token1)
        with self.assertRaises(tenant_tier_intent.EntitlementDenied):
            self.intent.status(token1, csrf1)
        with self.assertRaises(tenant_tier_intent.EntitlementDenied):
            self.intent.choose_for_future_review(token1, csrf1, "custom")

    def test_unapproved_prices_billing_and_user_privileges_are_rejected(self):
        for malformed in (None, True, "enterprise", "paid", "Plus",
                          " pro ", {"plan": "pro"}, "10.00"):
            with self.subTest(value=malformed), self.assertRaises(
                    tenant_tier_intent.EntitlementDenied):
                self.intent.choose_for_future_review(
                    *self.keys(0), requested_tier=malformed)
        with self.assertRaises(tenant_tier_intent.EntitlementDenied):
            self.intent.grant_paid_tier(self.users[0][0], "pro", "$9.99")
        self.assertFalse(self.intent.status(*self.keys(0))["subscriptionActive"])

    def test_schema_does_not_initialize_untrusted_owner_database(self):
        with self.assertRaises(RuntimeError):
            tenant_tier_intent.setup(str(Path(self.tmp.name) / "legacy_owner.db"))


if __name__ == "__main__":
    unittest.main()
