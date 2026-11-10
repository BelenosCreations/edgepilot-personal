"""v0.2.31 account UI boundary tests (no live brokerage requests)."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]


class AccountScopedReadOnlyUiTests(unittest.TestCase):
    def test_ui_supports_only_verified_user_owned_public_read_paths(self):
        html=(ROOT/"backend/static/identity.html").read_text(encoding="utf-8")
        js=(ROOT/"backend/static/assets/identity.js").read_text(encoding="utf-8")
        for control in ("connectionChoice","findPublicAccounts","discoveredAccounts",
                        "linkedAccounts","portfolioSummary","holdings"):
            self.assertIn('id="'+control+'"',html)
        for route in ('"/public/connections"',
                      '"/public/read/connections/"','"/public/read/accounts/"',
                      '"/accounts"'):
            self.assertIn(route,js)
        for flag in ("discovered.readOnly !== true","discovered.ordersEnabled !== false",
                     "result.verifiedByPublic !== true","result.ordersEnabled !== false",
                     "portfolio.transfersEnabled !== false",
                     "portfolio.ordersEnabled !== false"):
            self.assertIn(flag,js)
        self.assertIn("encodeURIComponent(connectionId)",js)
        self.assertIn("encodeURIComponent(id)",js)
        # The existing tenant storage list returns snake_case account_id,
        # whereas Public adapter returns camelCase accountId.
        account_scope=(ROOT/"backend/engine/account_scope.py").read_text(encoding="utf-8")
        self.assertIn("SELECT a.account_id,a.label,a.provider",account_scope)
        self.assertIn("account.accountId || account.account_id",js)
        self.assertIn("data.readOnly !== true",js)
        self.assertIn("Invalid scoped account identifier",js)
        self.assertIn('document.createElement("li")',js)
        self.assertIn('document.createTextNode(',js)
        self.assertIn("textContent",js)
        for forbidden in ("innerHTML","document.cookie","localStorage","sessionStorage",
                          '"/api/order/','"/api/transfer/',"eval("):
            self.assertNotIn(forbidden,js)

    def test_logout_and_user_switch_clear_private_visible_data(self):
        js=(ROOT/"backend/static/assets/identity.js").read_text(encoding="utf-8")
        self.assertIn("function clearReadOnly()",js)
        self.assertIn('el("discoveredAccounts").replaceChildren()',js)
        self.assertIn('el("linkedAccounts").replaceChildren()',js)
        self.assertIn('el("holdings").replaceChildren()',js)
        self.assertIn('el("connectionChoice").replaceChildren()',js)
        # Both logout and new authenticated session reset UI state.
        self.assertGreaterEqual(js.count("clearReadOnly();"),2)

    def test_backend_only_discloses_sanitized_verified_account_scoped_data(self):
        from engine import tenant_public_live_readonly
        from engine import tenant_route_audit
        api=(ROOT/"backend/app.py").read_text(encoding="utf-8")
        worker=(ROOT/"backend/engine/automation_worker.py").read_text(encoding="utf-8")
        self.assertIn("tenant_public_reader.discover(token,connection_id)",api)
        self.assertIn("tenant_public_reader.link_verified(",api)
        self.assertIn("tenant_public_reader.portfolio(token,account_id)",api)
        self.assertIn("'EDGE_TENANT_PUBLIC_READONLY_ENABLED','false'",api)
        self.assertTrue(tenant_route_audit.inspect_sources(api,worker)
                        ["fullRouteAndWorkerRefactorRequired"])
        self.assertFalse(tenant_route_audit.inspect_sources(api,worker)
                         ["crossAccountProductionCutoverAllowed"])
        self.assertTrue(tenant_public_live_readonly.TIMEOUT > 0)


if __name__=="__main__":
    unittest.main()
