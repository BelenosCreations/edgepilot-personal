"""v0.2.86 deterministic, offline risk policy tests.

This future read-only exposure calculator does not read any bank or broker,
submit orders, move money, or activate an automation worker.
"""
import unittest

from engine import risk


DEFAULT = {
    "public_equity": "100.00",
    "independent_equity": None,
    "balance_source": "public",
    "protected_pct": "20",
    "spend_cap": "80",
    "per_trade_cap": "20",
    "broker_buying_power": "90",
    "attributed_exposure": "10",
    "other_exposure": "5",
    "open_orders": "5",
    "unreconciled_orders": "0",
    "fresh": True,
    "reconciled": True,
    "pending_external_sale": False,
}


def capacity(**changes):
    return risk.buying_capacity(**{**DEFAULT, **changes})


class ProtectedBalanceRiskPolicyTests(unittest.TestCase):
    def test_exact_zero_to_ninety_nine_policy(self):
        unrestricted = capacity(protected_pct="0")
        self.assertEqual(unrestricted["riskBudget"], "80.00")
        self.assertEqual(unrestricted["remainingToRisk"], "60.00")
        self.assertEqual(unrestricted["singleTradeLimit"], "20.00")
        self.assertEqual(unrestricted["protectedValue"], "0.00")
        protected = capacity(
            protected_pct="99",spend_cap="100",per_trade_cap="100",
            attributed_exposure="0",other_exposure="0",open_orders="0",
            unreconciled_orders="0",broker_buying_power="100")
        self.assertEqual(protected["riskBudget"], "1.00")
        self.assertEqual(protected["remainingToRisk"], "1.00")
        self.assertEqual(protected["singleTradeLimit"], "1.00")
        self.assertEqual(protected["protectedValue"], "99.00")
        for invalid in ("100", "100.01", "-1", "NaN", "Infinity", True, None):
            with self.subTest(invalid=invalid):
                with self.assertRaises(risk.RiskBlocked):
                    capacity(protected_pct=invalid)

    def test_all_outstanding_risk_reduces_remaining_allowance(self):
        result = capacity()
        self.assertEqual(result["riskBudget"], "80.00")
        self.assertEqual(result["remainingToRisk"], "60.00")
        self.assertEqual(result["singleTradeLimit"], "20.00")
        self.assertEqual(result["protectedValue"], "20.00")
        self.assertIn("not trading authorization", result["warning"])
        self.assertEqual(
            capacity(broker_buying_power="3.59")["singleTradeLimit"],"3.59")
        self.assertEqual(
            capacity(open_orders="500")["remainingToRisk"],"0.00")
        self.assertEqual(
            capacity(per_trade_cap="0")["singleTradeLimit"],"0.00")

    def test_independent_allocation_cannot_exceed_public_value(self):
        result=capacity(balance_source="independent",independent_equity="25.00",
                        protected_pct="20",spend_cap="50",
                        per_trade_cap="9",attributed_exposure="3",
                        other_exposure="0",open_orders="0")
        self.assertEqual(result["riskBudget"],"20.00")
        self.assertEqual(result["remainingToRisk"],"17.00")
        self.assertEqual(result["singleTradeLimit"],"9.00")
        self.assertEqual(result["protectedValue"],"5.00")
        for independent in (None,"0","100.01","-12","Infinity"):
            with self.subTest(independent=independent):
                with self.assertRaises(risk.RiskBlocked):
                    capacity(balance_source="independent",independent_equity=independent)

    def test_fractional_cents_never_round_up_exposable_amounts(self):
        value=capacity(public_equity="0.15",protected_pct="99",
            spend_cap="0.15",per_trade_cap="0.15",
            broker_buying_power="0.15",
            attributed_exposure="0",other_exposure="0",
            open_orders="0",unreconciled_orders="0")
        self.assertEqual(value["riskBudget"],"0.00")
        self.assertEqual(value["remainingToRisk"],"0.00")
        self.assertEqual(value["singleTradeLimit"],"0.00")
        self.assertEqual(value["protectedValue"],"0.15")

    def test_stale_unreconciled_manual_sales_and_malformed_values_fail_closed(self):
        for changes in (
            {"fresh":False}, {"fresh":"true"},
            {"reconciled":False}, {"reconciled":1},
            {"pending_external_sale":True},
            {"balance_source":"unknown"},
            {"broker_buying_power":None},
            {"broker_buying_power":True},
            {"broker_buying_power":"-1"},
            {"spend_cap":"NaN"},
            {"open_orders":"Infinity"},
            {"unreconciled_orders":"-10"},
            {"other_exposure":"not money"},
            {"attributed_exposure":object()},
            {"public_equity":"0"},
            {"public_equity":"-0.01"},
            {"public_equity":"1e100"},
        ):
            with self.subTest(changes={k:str(v)[:28] for k,v in changes.items()}):
                with self.assertRaises(risk.RiskBlocked):
                    capacity(**changes)


if __name__=="__main__":
    unittest.main()
