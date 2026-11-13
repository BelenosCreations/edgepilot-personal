"""v0.2.84 owner overview UI: zero additional broker reads or secret storage.

The owner summary displays the last explicit user-requested, sanitized Public
portfolio snapshot. These tests do not import any real credentials or make
requests to Render, Public or an external browser.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "static" / "identity.html").read_text(encoding="utf-8")
JS = (ROOT / "static" / "assets" / "identity.js").read_text(encoding="utf-8")


class SingleOwnerPortfolioOverviewTests(unittest.TestCase):
    def test_overview_is_hidden_until_owner_eligible(self):
        self.assertIn('id="ownerOverviewPane" class="panel" hidden', HTML)
        self.assertIn('aria-label="Read-only owner portfolio overview"', HTML)
        self.assertIn('id="ownerOverviewValue">Not loaded', HTML)
        self.assertIn('id="ownerOverviewPositions">Not loaded', HTML)
        self.assertIn('id="ownerOverviewStatus"', HTML)
        self.assertIn('id="ownerOverviewDetail"', HTML)
        self.assertIn('href="#portfolioPane"', HTML)
        self.assertIn('el("ownerOverviewPane").hidden = !(soloPortfolio && data.accounts.length > 0)', JS)
        self.assertIn('resetOwnerOverview(true);', JS)
        self.assertIn('el("ownerOverviewPane").hidden = hidden;', JS)

    def test_only_explicit_portfolio_click_can_fill_overview(self):
        self.assertIn('button.textContent = "View read-only portfolio"', JS)
        self.assertIn('button.addEventListener("click", () => action(async () => {', JS)
        self.assertIn('resetOwnerOverview(false);', JS)
        self.assertIn('portfolioUsd(portfolio.balance)', JS)
        self.assertIn('portfolioUnits(position.quantity)', JS)
        self.assertIn('portfolioUsd(position.currentValue)', JS)
        self.assertIn('el("ownerOverviewValue").textContent = total;', JS)
        self.assertIn('el("ownerOverviewPositions").textContent = String(positions.length);', JS)
        self.assertIn('el("ownerOverviewStatus").textContent = "Latest manual read-only Public snapshot";', JS)
        self.assertIn('if (requestGeneration === identityViewGeneration)', JS)
        self.assertIn('"Portfolio snapshot unavailable. Select View read-only portfolio to retry."', JS)
        self.assertIn('holdings.replaceChildren();', JS)
        self.assertEqual(
            JS.count('await api("/public/read/accounts/" + encodeURIComponent(id) + "/portfolio")'),
            1
        )
        # The overview must not independently make a second broker request.
        self.assertNotIn('fetch("/api/identity/public/read/accounts/"', JS)

    def test_no_private_account_persistence_or_false_financial_claims(self):
        self.assertIn("not combined balances or profit/loss", HTML)
        self.assertIn("No automatic refresh", HTML)
        self.assertIn("not a market quote timestamp", JS)
        for forbidden in (
            "localStorage", "sessionStorage", "indexedDB", "setInterval(",
            "innerHTML", 'id="ownerOverviewProfit"', "automatic trading",
            "edgepilot-recovery-key", "EDGE_APP_TOKEN",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, HTML)
                self.assertNotIn(forbidden, JS)


if __name__ == "__main__":
    unittest.main()
