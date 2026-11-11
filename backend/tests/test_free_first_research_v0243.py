"""v0.2.43 deterministic no-AI data/license/freshness and net-cost tests."""
import unittest
from datetime import datetime, timedelta, timezone

from engine import research_intelligence as research

NOW = "2026-11-10T19:00:00Z"
RIGHTS = {
    "provider": "TEST_ONLY_LICENSED_SOURCE",
    "analysis": True, "cache": False, "redistribute": False,
    "coverageVerified": True
}


def payload(asset="stock"):
    sample = {
        "assetClass": asset, "symbol": "TEST.1",
        "rights": dict(RIGHTS),
        "observedAt": "2026-11-10T18:59:50Z",
        "receivedAt": "2026-11-10T18:59:55Z",
        "bid": "100.00", "ask": "100.05", "last": "100.03",
        "volume": "12345", "state": "open"
    }
    if asset == "prediction":
        sample.update({
            "bid": "0.47", "ask": "0.50", "last": "0.48",
            "bookDepth": "25", "expiresAt": "2026-11-10T19:15:00Z",
            "settlementRules": "Test only: explicit no-live-contract payout terms."
        })
    return sample


def quote(data=None, *, asset="stock"):
    return research.Observation.validate(
        data if data is not None else payload(asset), now=NOW)


class ResearchCoreTests(unittest.TestCase):
    def test_no_paid_ai_no_provider_calls_and_no_executable_quote(self):
        sample = quote()
        summary = sample.summary()
        self.assertEqual(summary["aiCalls"], 0) if "aiCalls" in summary else None
        self.assertFalse(summary["executableQuote"])
        self.assertFalse(summary["tradeAllowed"])
        self.assertEqual(summary["spread"], "0.05")
        self.assertEqual(summary["midpointReferenceOnly"], "100.025")
        self.assertFalse(summary["cacheAllowed"])
        self.assertFalse(summary["redistributionAllowed"])

    def test_stale_missing_rights_and_inconsistent_snapshot_fail_closed(self):
        cases = [
            ("observedAt", "2026-11-10T18:00:00Z"),
            ("receivedAt", "2026-11-10T18:00:00Z"),
            ("observedAt", "2026-11-10T19:01:00Z"),
            ("receivedAt", "2026-11-10T19:00:30Z"),
            ("bid", "101.00"),
            ("ask", "0"),
            ("last", "-1"),
            ("volume", "NaN"),
            ("volume", float("inf")),
            ("state", "halted"),
            ("assetClass", "unknown"),
            ("assetClass", "CRYPTO"),
            ("symbol", "TEST<script>"),
        ]
        for name, value in cases:
            with self.subTest(field=name, value=value):
                x = payload()
                x[name] = value
                with self.assertRaises(research.ResearchUnavailable):
                    quote(x)

    def test_provider_license_and_coverage_must_be_explicit_and_analysis_permitted(self):
        original = payload()
        rights = dict(RIGHTS)
        for removed in RIGHTS:
            with self.subTest(missing=removed):
                test = {k: v for k, v in rights.items() if k != removed}
                with self.assertRaises(research.ResearchUnavailable):
                    quote({**original, "rights": test})
        for bad in ("false", 1, None):
            with self.subTest(bad=bad):
                t = dict(RIGHTS, coverageVerified=bad)
                with self.assertRaises(research.ResearchUnavailable):
                    quote({**original, "rights": t})
        for name in ("analysis", "coverageVerified"):
            with self.subTest(denied=name):
                t = dict(RIGHTS, **{name: False})
                with self.assertRaises(research.ResearchUnavailable):
                    quote({**original, "rights": t})
        yes = quote({**original, "rights": dict(RIGHTS, cache=True, redistribute=True)})
        self.assertTrue(yes.rights.allowed_cache)
        self.assertTrue(yes.rights.allowed_redistribution)

    def test_no_implicit_supported_crypto_provider(self):
        tested = quote(payload("crypto"))
        self.assertEqual(tested.asset_class, "crypto")
        unsupported = payload("crypto")
        unsupported["rights"]["coverageVerified"] = False
        with self.assertRaises(research.ResearchUnavailable):
            quote(unsupported)
        stale = payload("crypto")
        stale["observedAt"] = "2026-11-10T18:58:00Z"
        with self.assertRaises(research.ResearchUnavailable):
            quote(stale)

    def test_prediction_requires_expiry_depth_settlement_and_book(self):
        valid = quote(payload("prediction"))
        self.assertEqual(valid.asset_class, "prediction")
        for name, value in [
            ("expiresAt", None), ("expiresAt", "2026-11-10T18:59:00Z"),
            ("bookDepth", None), ("bookDepth", "0"),
            ("settlementRules", ""), ("settlementRules", None),
            ("bid", "1.01"), ("ask", "1.01"), ("state", "expired")
        ]:
            with self.subTest(name=name, value=value):
                case=payload("prediction")
                case[name]=value
                with self.assertRaises(research.ResearchUnavailable):
                    quote(case)

    def test_prediction_expected_value_must_charge_all_explicit_costs(self):
        observation = quote(payload("prediction"))
        evidence={
            "probability": "0.65", "basis": "chronological-held-out",
            "heldOutSamples": 100,
            "validatedAt": "2026-11-10T18:45:00Z",
        }
        scenario=research.prediction_yes_scenario(
            observation, calibrated_probability=evidence,
            commission="0.005", exchange_fee="0.003", settlement_fee="0.002",
            slippage="0.01", quantity="10")
        self.assertEqual(scenario["breakEvenProbability"], "0.520")
        self.assertEqual(scenario["netExpectedValueTotal"], "1.300")
        self.assertTrue(scenario["eligible"])
        self.assertFalse(scenario["tradeAllowed"])
        self.assertTrue(scenario["expectedValueIsForecastNotFact"])
        pessimistic=research.prediction_yes_scenario(
            observation, calibrated_probability=dict(evidence, probability="0.50"),
            commission="0.005", exchange_fee="0.003", settlement_fee="0.002",
            slippage="0.01", quantity="10")
        self.assertFalse(pessimistic["eligible"])

    def test_prediction_net_value_fail_closed_on_probability_and_depth(self):
        evidence={
            "probability": "0.65", "basis": "chronological-held-out",
            "heldOutSamples": 100,
            "validatedAt": "2026-11-10T18:45:00Z",
        }
        for changes in [
            {"basis": "llm-confidence"}, {"heldOutSamples": 29},
            {"probability": "1.01"}, {"probability": "-0.1"},
            {"validatedAt": "2026-11-10T19:00:01Z"},
        ]:
            with self.subTest(changes=changes):
                with self.assertRaises(research.ResearchUnavailable):
                    research.prediction_yes_scenario(
                        quote(payload("prediction")),
                        calibrated_probability={**evidence, **changes},
                        commission="0", exchange_fee="0", settlement_fee="0",
                        slippage="0", quantity="1")
        with self.assertRaises(research.ResearchUnavailable):
            research.prediction_yes_scenario(
                quote(payload("prediction")), calibrated_probability=evidence,
                commission="0", exchange_fee="0", settlement_fee="0",
                slippage="0", quantity="30")
        costly=research.prediction_yes_scenario(
            quote(payload("prediction")), calibrated_probability=evidence,
            commission="0.6", exchange_fee="0", settlement_fee="0",
            slippage="0", quantity="1")
        self.assertFalse(costly["eligible"])

    def test_free_chronological_features_have_no_probabilities_or_trades(self):
        bars=[]
        start=datetime(2026, 10, 1, tzinfo=timezone.utc)
        for day in range(30):
            bars.append({
                "at": (start + timedelta(days=day)).isoformat(),
                "close": str(100 + day)
            })
        result=research.chronological_momentum(bars, lookback=5)
        self.assertEqual(result["signal"], "positive-momentum")
        self.assertEqual(result["aiCalls"], 0)
        self.assertFalse(result["tradeAllowed"])
        self.assertIsNone(result["predictiveProbability"])
        for invalid in [
            bars[:-1] + [bars[-2]],
            list(reversed(bars)),
            bars[:-1] + [{"at": bars[-1]["at"], "close": "NaN"}],
        ]:
            with self.assertRaises(research.ResearchUnavailable):
                research.chronological_momentum(invalid)
        with self.assertRaises(research.ResearchUnavailable):
            research.chronological_momentum(bars[:6])
        with self.assertRaises(research.ResearchUnavailable):
            research.chronological_momentum(bars, lookback=0)


if __name__ == "__main__":
    unittest.main()
