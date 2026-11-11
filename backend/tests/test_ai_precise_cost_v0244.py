"""v0.2.44 model-aware owner-only accounting adversarial tests.

All provider HTTP calls are mocked; no API requests, tokens or billing occur.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, Mock

from engine import ai_analysis as ai

NOW = datetime(2026, 11, 10, 19, 0, tzinfo=timezone.utc)
SETTINGS = {"ai_enabled": "1", "ai_monthly_budget_usd": "0.002000"}


class CostControls(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="edge-ai-cost-")
        self.path = os.path.join(self.folder.name, "ai.db")
        ai.setup(self.path)
        self.clock = patch.object(ai, "_now", lambda now=None: NOW if now is None else now)
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.folder.cleanup()

    @staticmethod
    def fake_response(*, include_usage=True, input_tokens=120, output_tokens=60,
                      okay=True, text="Synthetic risk explanation"):
        content = {"output": [{"type": "message", "content": [
            {"type": "output_text", "text": text}]}]}
        if include_usage:
            content["usage"] = {
                "input_tokens": input_tokens, "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens}
        response = Mock()
        response.ok = okay
        response.status_code = 200 if okay else 429
        response.json.return_value = content
        return response

    def test_preflight_is_model_aware_and_much_smaller_than_fixed_twenty_cents(self):
        payload = {"text": "Market data is unverified; research only"}
        inp, luna = ai.preflight(payload, "gpt-6-luna")
        _, sol = ai.preflight(payload, "gpt-6-sol")
        self.assertGreater(inp, len(str(payload)))
        self.assertLess(luna, 10_000)  # < 1 US cent: illustrative small prompt
        self.assertGreater(sol, luna)
        self.assertGreater(luna, 0)
        self.assertLess(ai._usd(luna), ai._usd(200_000))
        with self.assertRaises(ai.AIError):
            ai.preflight({"x": "y"*16_000}, "gpt-6-luna")
        with self.assertRaises(ai.AIError):
            ai.preflight(payload, "gpt-6-luna", max_output_tokens=2000)

    def test_usage_reconciles_and_releases_unspent_local_reserve(self):
        old_budget = SETTINGS.copy()
        with patch.object(ai.requests, "post",
                          return_value=self.fake_response()) as post:
            output = ai.analyze(self.path, old_budget, "Help explain this risk",
                                "stock", "ABC", "hypothetical context",
                                "fake-API-key-test-only", "gpt-6-luna")
        self.assertEqual(post.call_count, 1)
        payload = post.call_args.kwargs["json"]
        self.assertTrue(payload["store"] is False)
        self.assertEqual(payload["max_output_tokens"], ai.MAX_OUTPUT_TOKENS)
        self.assertEqual(output["providerUsage"], {
            "inputTokens": 120, "outputTokens": 60})
        self.assertFalse(output["providerBillingCapGuaranteed"])
        self.assertFalse(output["tradePlaced"])
        # 120*0.1 + 60*0.5 = 42 microUSD => $0.000042.
        self.assertEqual(output["tokenCostEstimateUsd"], "0.000042")
        status = ai.status(self.path, SETTINGS, True)
        self.assertEqual(status["actualTokenCostEstimateUsd"], "0.000042")
        self.assertEqual(status["estimatedBudgetReservedUsd"], "0.000042")
        self.assertEqual(status["unresolvedRequestCount"], 0)
        self.assertEqual(len(ai.history(self.path)), 1)
        self.assertEqual(ai.history(self.path)[0]["model"], "gpt-6-luna")

    def test_missing_usage_retains_reservation_and_no_automatic_retry(self):
        with patch.object(ai.requests, "post",
                          return_value=self.fake_response(include_usage=False)) as http:
            with self.assertRaises(ai.AIError):
                ai.analyze(self.path, SETTINGS, "q", "stock", "ABC", "",
                           "fake-API-key-test-only", "gpt-6-luna")
        self.assertEqual(http.call_count, 1)
        status = ai.status(self.path, SETTINGS, True)
        self.assertEqual(status["unresolvedRequestCount"], 1)
        self.assertEqual(status["actualTokenCostEstimateUsd"], "0.000000")
        self.assertGreater(float(status["estimatedBudgetReservedUsd"]), 0)
        self.assertEqual(ai.history(self.path), [])

    def test_timeout_and_provider_rejection_hold_reserve(self):
        for outcome in (TimeoutError("synthetic timeout"),
                        self.fake_response(okay=False)):
            with self.subTest(outcome=type(outcome).__name__):
                with patch.object(ai.requests, "post",
                                  side_effect=outcome if isinstance(
                                      outcome, Exception) else None,
                                  return_value=outcome if not isinstance(
                                      outcome, Exception) else None) as http:
                    with self.assertRaises(ai.AIError):
                        ai.analyze(self.path, SETTINGS, "q", "stock", "ABC", "",
                                   "fake-API-key-test-only", "gpt-6-luna")
                self.assertEqual(http.call_count, 1)
        self.assertEqual(ai.status(self.path, SETTINGS, True)["unresolvedRequestCount"], 2)

    def test_month_rollover_does_not_charge_new_month_for_old_reservations(self):
        ai.reserve(self.path, SETTINGS, "q", "stock", "ABC", model="gpt-6-luna",
                   input_bound_tokens=1500)
        nov = ai.status(self.path, SETTINGS, True)
        dec = ai.status(self.path, SETTINGS, True,
                        now=datetime(2026, 12, 1, tzinfo=timezone.utc))
        self.assertNotEqual(nov["month"], dec["month"])
        self.assertGreater(float(nov["estimatedBudgetReservedUsd"]), 0)
        self.assertEqual(dec["estimatedBudgetReservedUsd"], "0.000000")

    def test_historical_rows_are_preserved_at_original_reserved_cost(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("""INSERT INTO ai_runs
                (ts,month,question,market,asset,reply,status,reserved_usd)
                VALUES(?,?,?,?,?,?,?,?)""", (
                NOW.isoformat(), NOW.strftime("%Y-%m"), "past",
                "stock", "ABC", "past answer", "complete", "0.20"))
        ai.setup(self.path)  # idempotent migration
        budget={"ai_enabled": "1", "ai_monthly_budget_usd": "0.20"}
        with self.assertRaises(ai.AIError):
            ai.reserve(self.path, budget, "new", "stock", "XYZ")
        status=ai.status(self.path, budget, True)
        self.assertEqual(status["estimatedBudgetReservedUsd"], "0.200000")
        self.assertEqual(status["actualTokenCostEstimateUsd"], "0.000000")
        self.assertEqual(len(ai.history(self.path)), 1)

    def test_concurrent_reservations_never_exceed_local_budget(self):
        price = ai._charge_micro(1200, 500, "gpt-6-luna", NOW)
        budget = {"ai_enabled": "1",
                  "ai_monthly_budget_usd": ai._usd(price * 3)}
        def attempt(n):
            try:
                ai.reserve(self.path, budget, "q"+str(n), "etf", "ABC",
                           model="gpt-6-luna", input_bound_tokens=1200)
                return True
            except ai.AIError:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(attempt, range(16)))
        self.assertEqual(sum(results), 3)
        status=ai.status(self.path, budget, True)
        self.assertEqual(status["estimatedBudgetReservedUsd"], ai._usd(price*3))
        self.assertEqual(status["blockedRequestCount"], 13)

    def test_unsupported_model_and_expired_rate_prevent_http(self):
        with patch.object(ai.requests, "post") as http:
            with self.assertRaises(ai.AIError):
                ai.analyze(self.path, SETTINGS, "q", "stock", "ABC", "",
                           "fake-key", "unknown-unverified-model")
            http.assert_not_called()
        with patch.object(ai, "_now", lambda now=None: datetime(
                2027, 1, 1, tzinfo=timezone.utc)):
            with patch.object(ai.requests, "post") as http:
                with self.assertRaises(ai.AIError):
                    ai.analyze(self.path, SETTINGS, "q", "stock", "ABC", "",
                               "fake-key", "gpt-6-luna")
                http.assert_not_called()

    def test_rate_changes_only_new_reservations_old_rates_are_not_repriced(self):
        first=ai.reserve(self.path, SETTINGS, "q1", "stock", "ABC",
                         model="gpt-6-luna", input_bound_tokens=1200)
        with ai.db(self.path) as conn:
            old=conn.execute("SELECT reserved_micro_usd FROM ai_runs WHERE id=?",
                             (first,)).fetchone()[0]
        with patch.dict(ai.RATES, {
            "gpt-6-luna": (ai.Decimal("0.20"), ai.Decimal("1.00"))
        }):
            next_id=ai.reserve(self.path, SETTINGS, "q2", "stock", "ABC",
                               model="gpt-6-luna", input_bound_tokens=1200)
            with ai.db(self.path) as conn:
                newer=conn.execute("SELECT reserved_micro_usd FROM ai_runs WHERE id=?",
                                   (next_id,)).fetchone()[0]
        self.assertEqual(newer, 2*old)
        with ai.db(self.path) as conn:
            original=conn.execute("SELECT reserved_micro_usd FROM ai_runs WHERE id=?",
                                  (first,)).fetchone()[0]
        self.assertEqual(original, old)

    def test_missing_api_key_and_no_consent_prevent_provider_request(self):
        with patch.object(ai.requests, "post") as http:
            with self.assertRaises(ai.AIError):
                ai.analyze(self.path, SETTINGS, "q", "stock", "ABC", "",
                           "", "gpt-6-luna")
            with self.assertRaises(ai.AIError):
                ai.analyze(self.path, {"ai_enabled": "0",
                          "ai_monthly_budget_usd": "10"},
                           "q", "stock", "ABC", "", "fake-key", "gpt-6-luna")
            http.assert_not_called()

    def test_duplicate_finalization_does_not_change_bill_twice(self):
        run_id=ai.reserve(self.path, SETTINGS, "q", "stock", "ABC")
        ai._finish(self.path, run_id, state="complete", actual_micro=15,
                   input_tokens=50, output_tokens=20, reply="fake")
        with self.assertRaises(ai.AIError):
            ai._finish(self.path, run_id, state="complete", actual_micro=9000,
                       input_tokens=100, output_tokens=100, reply="fake")
        self.assertEqual(ai.status(self.path, SETTINGS, True)[
            "actualTokenCostEstimateUsd"], "0.000015")


if __name__=="__main__":
    unittest.main()
