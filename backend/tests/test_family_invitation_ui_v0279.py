"""v0.2.79: owner-only private invitation UI static safety regression.

UI tests deliberately use source inspection; HTTP invitation auth, one-time
token use and two-identity isolation are covered in the v0.2.78 Flask tests.
No real invitations, provider requests or secrets are created here.
"""
from pathlib import Path
import unittest


ROOT=Path(__file__).resolve().parents[1]
HTML=ROOT/"static"/"identity.html"
JS=ROOT/"static"/"assets"/"identity.js"
APP=ROOT/"app.py"


class PrivateFamilyInvitationUITests(unittest.TestCase):
    def test_owner_panel_has_safe_one_time_display_and_no_public_url(self):
        html=HTML.read_text(encoding="utf-8")
        for expected in (
            'id="familyInvitationsPane" class="panel" hidden',
            'id="generateFamilyInvite"',
            'id="familyInviteResult" hidden',
            'id="familyInviteCode" type="password"',
            'id="revealFamilyInvite"',
            'id="copyFamilyInvite"',
            'only once',
            'Share the code privately',
        ):
            self.assertIn(expected,html)
        self.assertIn('id="registerForm"',html)
        self.assertIn('id="invite" type="password"',html)
        self.assertNotIn('value="SYNTHETIC-',html)
        self.assertNotIn('href="/api/identity/admin/invitations"',html)

    def test_ui_invite_is_csrf_bound_hidden_by_default_and_erased_on_logout(self):
        js=JS.read_text(encoding="utf-8")
        for required in (
            'data.privateInvitationsAvailable === true',
            'data.user.role === "owner"',
            'el("familyInvitationsPane").hidden = true',
            'el("familyInviteCode").value = ""',
            'el("familyInviteResult").hidden = true',
            'await api("/admin/invitations", "POST", {}, true)',
            'issued.newUserRole !== "member"',
            'issued.tradingEnabled !== false',
            'issued.fundTransfersEnabled !== false',
            'issued.publicBrokerageEnabled !== false',
            'navigator.clipboard.writeText(el("familyInviteCode").value)',
            'el("familyInviteCode").type = "password"',
        ):
            with self.subTest(required=required):
                self.assertIn(required,js)
        self.assertNotIn("localStorage",js)
        self.assertNotIn("sessionStorage",js)
        self.assertNotIn("console.log",js)
        self.assertNotIn("window.location.search",js)
        self.assertNotIn("window.location.hash",js)

    def test_server_never_includes_a_token_in_session_metadata(self):
        app=APP.read_text(encoding="utf-8")
        self.assertIn("'privateInvitationsAvailable':bool(",app)
        self.assertIn("permanent_admin_invites_enabled and principal['role']=='owner'",app)
        self.assertIn("permanent_admin_invites.issue(",app)
        self.assertIn("request.headers.get('X-Edge-Identity-CSRF','')",app)


if __name__=="__main__":
    unittest.main()
