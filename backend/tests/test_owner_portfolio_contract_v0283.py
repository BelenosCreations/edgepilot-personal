"""v0.2.83 Public portfolio response and owner screen safety regression.

All examples are synthetic. No live account, key, broker network or Render
database access is used. The account page still requires a deliberate click.
"""
from pathlib import Path
import unittest

from engine import tenant_public_live_readonly as reader

ROOT=Path(__file__).resolve().parents[2]


class OwnerPortfolioContractTests(unittest.TestCase):
    def test_current_public_v2_contract_requires_matching_account_binding(self):
        code=(ROOT/"backend/engine/tenant_public_live_readonly.py").read_text(
            encoding="utf-8")
        self.assertIn('if _safe_id(data.get("accountId")) != provider_id:',code)
        self.assertIn("self._accounts(token)",code)
        self.assertIn("self._credential_fingerprint(owner,conn)",code)
        self.assertIn("self._principal(identity_token)!=owner",code)
        self.assertIn('"ordersEnabled":False,"transfersEnabled":False',code)
        for forbidden in (
            "def submit_order(", "def place_order(", "def transfer_funds("
        ):
            self.assertNotIn(forbidden,code)

    def test_invalid_money_and_quantity_fail_closed_without_guessing(self):
        self.assertEqual(reader._decimal("0"),"0.00")
        self.assertEqual(reader._decimal("210.35"),"210.35")
        self.assertEqual(reader._quantity("0.00000001"),"0.00000001")
        self.assertEqual(reader._quantity("-0.5"),"-0.5")
        for value in (None,True,False,"",float("nan"),"NaN","Infinity"):
            with self.subTest(value=str(value)):
                with self.assertRaises(reader.PublicReadUnavailable):
                    reader._quantity(value)

    def test_owner_ui_never_calls_broker_without_click_or_assumes_shares(self):
        html=(ROOT/"backend/static/identity.html").read_text(encoding="utf-8")
        js=(ROOT/"backend/static/assets/identity.js").read_text(encoding="utf-8")
        self.assertIn("Your Public accounts (read-only)",html)
        self.assertIn("View read-only portfolio",js)
        self.assertIn('button.addEventListener("click", () => action(async () => {',js)
        self.assertIn('portfolioUsd(portfolio.balance)',js)
        self.assertIn('portfolioUnits(position.quantity)',js)
        self.assertIn('portfolioUsd(position.currentValue)',js)
        self.assertIn('portfolio.holdings.length > 100',js)
        self.assertIn('portfolio.accountId !== id',js)
        self.assertIn('holdings.replaceChildren()',js)
        self.assertIn('quantity " + position.quantity +',js)
        self.assertIn('units · current value "',js)
        self.assertIn('Public reported no open positions',js)
        self.assertIn('not a market quote timestamp',js)
        self.assertNotIn('" shares · value "',js)
        self.assertNotIn("innerHTML",js)
        self.assertNotIn("localStorage",js)
        self.assertNotIn("sessionStorage",js)
        self.assertNotIn("setInterval",js)
        self.assertNotIn("setTimeout",js)
        self.assertNotIn('"/api/order/',js)
        self.assertNotIn('"/api/transfer/',js)


if __name__=="__main__":
    unittest.main()
