"""v0.2.50 dormant AI reconciliation: do not undercount over-preflight usage."""
from datetime import datetime, timezone
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from engine import tenant_foundation, identity_auth, tenant_ai_budget_vault as ai

NOW = datetime(2026, 11, 10, 19, 0, tzinfo=timezone.utc)


class CostOverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="edge-ai-overage-")
        self.path = self.tmp.name + "/synthetic.db"
        tenant_foundation.setup(self.path)
        identity_auth.setup(self.path)
        ai.setup(self.path)
        self.auth = identity_auth.IdentityStore(self.path)
        self.vault = ai.TenantAIBudgetVault(
            self.path, self.auth, credential_key=Fernet.generate_key().decode())
        self.people = []
        self.net = patch("requests.sessions.Session.request",
                         side_effect=AssertionError("No AI network allowed"))
        self.net.start()
        for i in range(2):
            uid = tenant_foundation.TenantStore(self.path).provision_user(
                "Synthetic AI cost tester " + str(i))
            login = "synthetic_cost_" + str(i)
            password = "synthetic-overage-passphrase-" + str(i)
            self.auth.provision(uid, login, password)
            session = self.auth.authenticate(login, password, "local_" + str(i))
            self.people.append(session)
            self.vault.set_policy(session["token"], session["csrf"],
                                  mode="byok", monthly_budget_usd="0.001000")
            self.vault.put_key(session["token"], session["csrf"],
                               "sk-SYNTHETIC-NEVER-BILLED-" + str(i), consent=True)

    def tearDown(self):
        self.net.stop()
        self.tmp.cleanup()

    def tokens(self, i):
        p = self.people[i]
        return p["token"], p["csrf"]

    def reserve(self, i):
        return self.vault.reserve_simulated(
            *self.tokens(i), model="gpt-6-luna",
            input_tokens_bound=1200, max_output_tokens=500, now=NOW)

    def test_higher_actual_cost_is_retained_not_silently_counted_at_hold(self):
        initial = self.reserve(0)
        self.assertEqual(initial["heldMicroUsd"], 370)
        over = self.vault.settle_simulated(
            *self.tokens(0), initial["requestId"],
            input_tokens=10000, output_tokens=5000, now=NOW)
        self.assertEqual(over["state"], "uncertain")
        self.assertTrue(over["overageDetected"])
        self.assertGreater(over["actualMicroUsd"], initial["heldMicroUsd"])
        state = self.vault.status(*self.tokens(0), now=NOW)
        self.assertEqual(state["locallyCountedMicroUsd"], over["actualMicroUsd"])
        self.assertEqual(state["remainingMicroUsd"], 0)
        self.assertEqual(state["pendingOrUncertainCount"], 1)
        self.assertEqual(self.vault.status(*self.tokens(1), now=NOW)
                         ["locallyCountedMicroUsd"], 0)
        with self.assertRaises(ai.TenantAIDenied):
            self.reserve(0)
        with self.assertRaises(ai.TenantAIDenied):
            self.vault.settle_simulated(*self.tokens(0), initial["requestId"],
                                        input_tokens=100, output_tokens=50, now=NOW)
        self.vault.disconnect_key(*self.tokens(0))
        self.assertEqual(self.vault.status(*self.tokens(0), now=NOW)
                         ["locallyCountedMicroUsd"], over["actualMicroUsd"])

    def test_under_reservation_actual_finalizes_normally(self):
        initial = self.reserve(1)
        done = self.vault.settle_simulated(
            *self.tokens(1), initial["requestId"],
            input_tokens=100, output_tokens=50, now=NOW)
        self.assertEqual(done["state"], "complete")
        self.assertFalse(done["overageDetected"])
        self.assertLess(done["actualMicroUsd"], initial["heldMicroUsd"])
        self.assertEqual(self.vault.status(*self.tokens(1), now=NOW)
                         ["locallyCountedMicroUsd"], done["actualMicroUsd"])
        self.assertEqual(self.vault.status(*self.tokens(1), now=NOW)
                         ["pendingOrUncertainCount"], 0)

    def test_unknown_cost_remains_held_without_fabricated_actual_usage(self):
        held = self.reserve(0)
        uncertain = self.vault.settle_simulated(
            *self.tokens(0), held["requestId"], input_tokens=0,
            output_tokens=0, uncertain=True, now=NOW)
        self.assertEqual(uncertain["state"], "uncertain")
        self.assertIsNone(uncertain["actualMicroUsd"])
        self.assertFalse(uncertain["overageDetected"])
        self.assertEqual(self.vault.status(*self.tokens(0), now=NOW)
                         ["locallyCountedMicroUsd"], held["heldMicroUsd"])

    def test_cross_member_cannot_settle_another_members_overage(self):
        held = self.reserve(0)
        with self.assertRaises(ai.TenantAIDenied):
            self.vault.settle_simulated(
                *self.tokens(1), held["requestId"],
                input_tokens=10000, output_tokens=5000, now=NOW)
        self.assertEqual(self.vault.status(*self.tokens(0), now=NOW)
                         ["locallyCountedMicroUsd"], held["heldMicroUsd"])


if __name__ == "__main__":
    unittest.main()
