"""v0.2.35 UI and API guardrails for tenant Public key lifecycle.

No Public API requests or real credentials. Crypto, account revocation, and
cross-owner HTTP behavior are additionally covered by the existing vault tests.
"""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]


class TenantPublicConnectionControlsTests(unittest.TestCase):
    def test_form_holds_secret_only_in_ephemeral_password_input(self):
        html=(ROOT/"backend/static/identity.html").read_text(encoding="utf-8")
        js=(ROOT/"backend/static/assets/identity.js").read_text(encoding="utf-8")
        for name in ("connectionChoice","replacementSecret",
                     "rotatePublicSecret","disconnectPublicConnection"):
            self.assertIn('id="'+name+'"',html)
        self.assertIn('id="replacementSecret" type="password" autocomplete="off"',html)
        self.assertIn("Replacing the API secret or disconnecting removes",html)
        self.assertIn("does not close your Public brokerage account",html)
        self.assertNotIn("localStorage",js)
        self.assertNotIn("sessionStorage",js)
        self.assertNotIn("innerHTML",js)
        self.assertNotIn("document.cookie",js)
        self.assertIn('el("replacementSecret").value = "";',js)
        self.assertGreaterEqual(js.count('el("replacementSecret").value = "";'),2)

    def test_rotation_and_disconnect_require_owner_selection_csrf_and_confirmation(self):
        js=(ROOT/"backend/static/assets/identity.js").read_text(encoding="utf-8")
        for marker in (
            '"rotatePublicSecret").addEventListener("click"',
            '"disconnectPublicConnection").addEventListener("click"',
            'const connectionId = chosenConnectionId();',
            'window.confirm("Replace the saved secret',
            'window.confirm("Disconnect this encrypted Public connection',
            'encodeURIComponent(connectionId) + "/rotate", "POST", {secret}, true',
            'encodeURIComponent(connectionId), "DELETE", undefined, true',
            'result.boundAccountsDisabled !== true',
            'result.secretsReturned !== false',
            'result.realOrdersEnabled !== false',
            'generation !== identityViewGeneration',
            'await refreshAfterCredentialChange();',
        ):
            self.assertIn(marker,js)
        self.assertIn("clearReadOnly();",js)
        self.assertIn("await loadLinkedAccounts();",js)
        self.assertNotIn('"/api/order/',js)
        self.assertNotIn('"/api/transfer/',js)

    def test_backend_rechecks_current_identity_under_write_lock(self):
        vault=(ROOT/"backend/engine/tenant_public_vault.py").read_text(encoding="utf-8")
        app=(ROOT/"backend/app.py").read_text(encoding="utf-8")
        self.assertIn("def _principal_locked(db, identity_token, csrf)",vault)
        self.assertIn("db.execute(\"BEGIN IMMEDIATE\")",vault)
        self.assertIn("self._principal_locked(db, identity_token, csrf) != owner",vault)
        self.assertIn("s.credential_version=i.credential_version",vault)
        self.assertIn("u.disabled_at IS NULL",vault)
        self.assertIn("hmac.compare_digest(",vault)
        self.assertIn("tenant_connection_vault.rotate(",app)
        self.assertIn("tenant_connection_vault.disconnect(",app)
        self.assertIn("set(body)!={'secret'}",app)
        self.assertIn("'EDGE_TENANT_PUBLIC_VAULT_ENABLED','false'",app)


if __name__=="__main__":
    unittest.main()
