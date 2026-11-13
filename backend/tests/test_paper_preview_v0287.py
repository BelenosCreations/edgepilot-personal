"""v0.2.87: pure paper preview must remain isolated and fail closed."""
from pathlib import Path
import unittest

from engine.paper_preview import preview_paper_buy, PaperPreviewUnavailable


NOW = "2026-11-12T20:00:00Z"


def evidence(asset="stock"):
    result = {
        "assetClass": asset, "symbol": "TEST.1",
        "rights": {"provider": "SYNTHETIC_LICENSED_TEST", "analysis": True,
                   "cache": False, "redistribute": False,
                   "coverageVerified": True},
        "observedAt": "2026-11-12T19:59:55Z",
        "receivedAt": "2026-11-12T19:59:58Z",
        "bid": "1.99", "ask": "2.00", "last": "1.995",
        "volume": "1000", "state": "open",
    }
    if asset == "prediction":
        result.update({"bookDepth": "100", "expiresAt": "2026-11-12T20:15:00Z",
                       "settlementRules": "Synthetic test settlement only.",
                       "bid": "0.48", "ask": "0.50", "last": "0.49"})
    return result


def policy(**changes):
    result = {
        "public_equity": "100", "independent_equity": None,
        "balance_source": "public", "protected_pct": "90",
        "spend_cap": "100", "per_trade_cap": "5",
        "broker_buying_power": "100", "attributed_exposure": "0",
        "other_exposure": "0", "open_orders": "0",
        "unreconciled_orders": "0", "fresh": True, "reconciled": True,
        "pending_external_sale": False,
    }
    result.update(changes)
    return result


def preview(**changes):
    params = {
        "observation": evidence(), "now": NOW, "quantity": "2",
        "fee_per_unit": "0.02", "slippage_per_unit": "0.01",
        "paper_cash": "30", "risk_inputs": policy(),
    }
    params.update(changes)
    return preview_paper_buy(**params)


class RiskControlledPaperPreviewTests(unittest.TestCase):
    def test_only_hypothetical_cost_with_explicit_friction_and_no_order(self):
        result = preview()
        self.assertEqual(result["mode"], "PAPER_PREVIEW_ONLY")
        self.assertEqual(result["source"], "SYNTHETIC_LICENSED_TEST")
        self.assertEqual(result["estimatedTotalCost"], "4.06")
        self.assertEqual(result["paperCashAfter"], "25.94")
        self.assertEqual(result["singleTradeRiskLimit"], "5.00")
        self.assertFalse(result["recorded"])
        self.assertFalse(result["orderSubmitted"])
        self.assertFalse(result["tradeAllowed"])
        self.assertNotIn("profit", str(result).lower())
        self.assertNotIn("accountId", result)

    def test_cash_and_risk_capacity_are_both_hard_limits(self):
        for changes in [
            {"paper_cash": "4.05"}, {"quantity": "3"},
            {"risk_inputs": policy(per_trade_cap="4")},
            {"risk_inputs": policy(protected_pct="99")},
            {"risk_inputs": policy(open_orders="9")},
            {"risk_inputs": policy(attributed_exposure="9")},
            {"risk_inputs": policy(unreconciled_orders="8")},
            {"risk_inputs": policy(broker_buying_power="2")},
        ]:
            with self.subTest(changes=changes):
                with self.assertRaises(PaperPreviewUnavailable):
                    preview(**changes)

    def test_protection_policy_fail_closed_without_trading_permissions(self):
        for changes in [
            {"protected_pct": "100"}, {"protected_pct": "-1"},
            {"fresh": False}, {"reconciled": False},
            {"pending_external_sale": True}, {"independent_equity": "200",
            "balance_source": "independent"},
            {"broker_buying_power": None},
        ]:
            with self.subTest(changes=changes):
                with self.assertRaises(PaperPreviewUnavailable):
                    preview(risk_inputs=policy(**changes))
        with self.assertRaises(PaperPreviewUnavailable):
            incomplete = policy()
            del incomplete["open_orders"]
            preview(risk_inputs=incomplete)
        with self.assertRaises(PaperPreviewUnavailable):
            preview(risk_inputs={**policy(), "ignoreLimits": True})

    def test_unverified_stale_or_nontrading_evidence_refused(self):
        cases = [
            {"observedAt": "2026-11-12T19:55:00Z"},
            {"receivedAt": "2026-11-12T19:55:00Z"},
            {"observedAt": "2026-11-12T20:01:00Z"},
            {"state": "halted"}, {"ask": "1.90"},
            {"rights": {**evidence()["rights"], "coverageVerified": False}},
            {"rights": {**evidence()["rights"], "analysis": False}},
        ]
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(PaperPreviewUnavailable):
                    preview(observation={**evidence(), **case})
        with self.assertRaises(PaperPreviewUnavailable):
            preview(now="2026-11-12T20:03:00Z")
        with self.assertRaises(PaperPreviewUnavailable):
            preview(observation=evidence("prediction"))
        self.assertEqual(preview(observation=evidence("crypto"))["assetClass"], "crypto")

    def test_invalid_inputs_and_fractional_cent_spending_block(self):
        for changes in [
            {"quantity": 0}, {"quantity": "-1"}, {"quantity": "NaN"},
            {"quantity": 0.5}, {"quantity": "0.0000000000000000001"},
            {"fee_per_unit": "-0.02"}, {"fee_per_unit": None},
            {"slippage_per_unit": float("inf")}, {"paper_cash": "-1"},
            {"paper_cash": True}, {"paper_cash": "Infinity"},
        ]:
            with self.subTest(changes=changes):
                with self.assertRaises(PaperPreviewUnavailable):
                    preview(**changes)
        # 99% protection on $100: exactly $1 risk capacity; $0.99
        # paper ask plus tiny fee must round UP, never risk $1.01.
        quote = evidence()
        quote["ask"] = "0.99"
        quote["bid"] = "0.98"
        with self.assertRaises(PaperPreviewUnavailable):
            preview(observation=quote, quantity="1", fee_per_unit="0.01001",
                    slippage_per_unit="0", risk_inputs=policy(protected_pct="99"))

    def test_module_has_no_network_persistence_or_order_api(self):
        source = (Path(__file__).resolve().parents[1] / "engine" /
                  "paper_preview.py").read_text(encoding="utf-8")
        for forbidden in ("requests", "sqlite3", "submit_order(", "broker_call(",
                          "urlopen(", "EDGE_APP_TOKEN", "os.environ",
                          "INSERT INTO", "UPDATE ", "DELETE FROM"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
