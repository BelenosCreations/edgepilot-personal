"""Legacy owner AI accounting compatibility: zero AI is off, not an API cap."""
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from engine import ai_analysis as ai

NOW = datetime(2026, 11, 10, 18, 0, tzinfo=timezone.utc)
ON = {"ai_enabled": "1", "ai_monthly_budget_usd": "0.40"}


class TestAI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "db.sqlite")
        ai.setup(self.path)
        self.clock = patch.object(ai, "_now", lambda now=None: NOW if now is None else now)
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.tmp.cleanup()

    def test_status_disabled(self):
        s = ai.status(self.path, {
            "ai_enabled": "0", "ai_monthly_budget_usd": "0"}, False)
        self.assertFalse(s["enabled"])
        self.assertFalse(s["credentialConfigured"])
        self.assertEqual(s["estimatedBudgetReservedUsd"], "0.000000")
        self.assertFalse(s["providerBillingCapGuaranteed"]) if "providerBillingCapGuaranteed" in s else None

    def test_budget_rejects(self):
        with self.assertRaises(ai.AIError):
            ai.reserve(self.path, {"ai_enabled": "0", "ai_monthly_budget_usd": "10"},
                       "q", "stock", "ABC")
        with self.assertRaises(ai.AIError):
            ai.reserve(self.path, {
                "ai_enabled": "1", "ai_monthly_budget_usd": "0"},
                "q", "stock", "ABC")
        self.assertEqual(ai.status(self.path, ON, False)["blockedRequestCount"], 1)

    def test_reservation_limit_and_monthly_summary(self):
        budget = {"ai_enabled": "1", "ai_monthly_budget_usd": "0.001000"}
        first = ai.reserve(self.path, budget, "q1", "stock", "ABC",
                           input_bound_tokens=1000, max_output_tokens=500)
        second = ai.reserve(self.path, budget, "q2", "etf", "XYZ",
                            input_bound_tokens=1000, max_output_tokens=500)
        self.assertNotEqual(first, second)
        with self.assertRaises(ai.AIError):
            ai.reserve(self.path, budget, "q3", "prediction", "X",
                       input_bound_tokens=1000, max_output_tokens=500)
        status = ai.status(self.path, budget, True)
        self.assertEqual(status["estimatedBudgetReservedUsd"], "0.000700")
        self.assertEqual(status["blockedReasons"], {"monthly_budget_exceeded": 1})

    def test_no_history_for_reserved(self):
        ai.reserve(self.path, ON, "q", "stock", "ABC")
        self.assertEqual(ai.history(self.path), [])

    def test_extract_text(self):
        self.assertEqual(ai.extract_text({"output": [{
            "type": "message", "content": [{"type": "output_text", "text": "OK"}]
        }]}), "OK")

    def test_unknown_model_and_expired_pricing_fail_closed(self):
        with self.assertRaises(ai.AIError):
            ai._rate("unverified-model")
        with self.assertRaises(ai.AIError):
            ai._rate("gpt-6-luna", datetime(2026, 12, 11, tzinfo=timezone.utc))
        self.assertEqual(ai._rate("gpt-6-luna"),
                         (ai.Decimal("0.10"), ai.Decimal("0.50")))

if __name__ == "__main__":
    unittest.main()
