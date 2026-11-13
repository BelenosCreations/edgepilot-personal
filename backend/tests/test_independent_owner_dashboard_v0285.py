"""v0.2.85 independent identity-backed owner dashboard boundary tests.

This milestone adds a separate read-only owner UI but must NEVER grant
the old global token session access to another identity's Public portfolio.
No provider HTTP, keys, real brokerage account, deployment or paid service.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
PAGE = (ROOT / "static" / "owner-dashboard.html").read_text(encoding="utf-8")
JS = (ROOT / "static" / "assets" / "owner-dashboard.js").read_text(encoding="utf-8")
IDENTITY = (ROOT / "static" / "identity.html").read_text(encoding="utf-8")
LEGACY = (ROOT / "static" / "index.html").read_text(encoding="utf-8")


class IndependentOwnerDashboardTests(unittest.TestCase):
    def test_new_shell_stays_separate_from_legacy_auth(self):
        self.assertIn("@app.get('/owner')", APP)
        self.assertIn("send_from_directory(ROOT/'static','owner-dashboard.html')", APP)
        self.assertIn('src="/assets/owner-dashboard.js"', PAGE)
        self.assertIn('href="/account"', PAGE)
        self.assertIn('href="/owner"', IDENTITY)
        self.assertIn('href="/owner"', LEGACY)
        self.assertIn('href="/"', PAGE)
        self.assertNotIn("window.localStorage", JS)
        self.assertNotIn("localStorage", JS)
        self.assertNotIn("sessionStorage", JS)
        self.assertNotIn("indexedDB", JS)
        self.assertNotIn("innerHTML", JS)
        self.assertNotIn("document.cookie", JS)
        self.assertNotIn("EDGE_APP_TOKEN", JS)
        self.assertNotIn("/api/login", JS)
        self.assertNotIn('fetch("/api/dashboard"', JS)
        self.assertNotIn("automation/start", JS)
        self.assertNotIn("submit-order", JS)
        self.assertNotIn("bank-transfer", JS)
        self.assertNotIn("trade/execute", JS)

    def test_server_verified_owner_only_and_linked_accounts(self):
        self.assertIn('api("/api/identity/session")', JS)
        self.assertIn('session.user.role !== "owner"', JS)
        self.assertIn('api("/api/identity/accounts")', JS)
        self.assertIn("data.soloOwnerPortfolioAvailable !== true", JS)
        self.assertIn("data.readOnly !== true", JS)
        self.assertIn("data.discoveryOnlyPilot !== true", JS)
        self.assertIn("accountIdPattern.test(id)", JS)
        self.assertIn("el(\"dashboard\").hidden = true;", JS)
        self.assertIn("el(\"signedOut\").hidden = false;", JS)
        self.assertIn('api("/api/identity/logout", "POST", csrf)', JS)
        self.assertIn('ownerSession = null;', JS)

    def test_manual_snapshot_only_and_prevent_cross_account_display(self):
        self.assertIn('el("loadPortfolio").addEventListener("click"', JS)
        path = '"/api/identity/public/read/accounts/" +'
        # Portfolio, quote and history each have a manual account-scoped request.
        self.assertEqual(JS.count(path), 3)
        self.assertIn('encodeURIComponent(id) + "/market-history"', JS)
        self.assertIn('encodeURIComponent(id) + "/quote"', JS)
        self.assertIn('encodeURIComponent(id) + "/portfolio"', JS)
        self.assertIn("data.accountId !== selectedId", JS)
        self.assertIn("data.readOnly !== true", JS)
        self.assertIn("data.ordersEnabled !== false", JS)
        self.assertIn("data.transfersEnabled !== false", JS)
        self.assertIn("revision !== current", JS)
        self.assertIn("el(\"accountChoice\").value !== id", JS)
        self.assertIn('clearSnapshot();', JS)
        self.assertIn('window.addEventListener("pagehide", clearSnapshot)', JS)
        self.assertIn("el(\"positions\").replaceChildren(...rows);", JS)
        self.assertIn('el("portfolioValue").textContent = snapshot.value', JS)
        self.assertIn("money(position.currentValue)", JS)
        self.assertIn("quantity(position.quantity)", JS)
        self.assertNotIn("setInterval(", JS)
        self.assertNotIn("setTimeout(", JS)
        self.assertNotIn("WebSocket(", JS)
        self.assertNotIn("EventSource(", JS)

    def test_no_fictitious_performance_or_automatic_orders(self):
        self.assertIn("not your total net worth or a historical performance chart", PAGE)
        self.assertIn("not a market quote timestamp", JS)
        self.assertIn("no orders or transfers", JS)
        self.assertIn("remain disabled", PAGE)
        self.assertIn("No chart or returns are fabricated", PAGE)
        self.assertNotIn('id="dailyProfit"', PAGE)
        self.assertNotIn('id="tradeButton"', PAGE)
        self.assertNotIn("onclick=", PAGE)
        self.assertNotIn("portfolioPerformance", JS)
        self.assertNotIn("profitLoss", JS)
        # No server session token or provider API secret appears in HTML source.
        self.assertNotRegex(PAGE, r"(?i)(?:authorization:\s*bearer|-----begin .*private key)")

if __name__ == "__main__":
    unittest.main()
