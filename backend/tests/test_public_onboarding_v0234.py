"""v0.2.34 official Public account onboarding guardrails.

Navigation checks are structural; Android compilation is tested separately
by GitHub Actions, and final link handling must be exercised on a phone.
No real Public credentials or signup requests are made by this suite.
"""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]


class PublicOnboardingChecks(unittest.TestCase):
    def test_public_links_are_official_explicit_https_urls(self):
        html=(ROOT/"backend/static/identity.html").read_text(encoding="utf-8")
        home=(ROOT/"backend/static/index.html").read_text(encoding="utf-8")
        self.assertIn('href="https://public.com/signup"',html)
        self.assertIn('href="https://public.com/api/docs/quickstart"',html)
        self.assertIn(">Sign Up for Public</a>",html)
        self.assertIn("Get your Public API key",html)
        self.assertIn("Settings &gt; Security &gt; API",html)
        self.assertIn("return to EdgePilot",html)
        self.assertIn('href="/account"',home)
        self.assertIn("Separate multi-user accounts are currently in staged development",home)
        self.assertNotIn('href="http://public.com',html)
        self.assertNotIn("public.com/signup?",html)
        self.assertNotIn("public.com/api/docs/quickstart?",html)
        self.assertIn('id="publicSecret" type="password"',html)
        self.assertIn('autocomplete="off" autocapitalize="off" spellcheck="false"',html)
        self.assertIn("This does not enable trading",html)

    def test_android_external_links_allow_only_two_public_pages_on_user_click(self):
        java=(ROOT/"android/app/src/main/java/com/edgepilot/mobile/MainActivity.java").read_text(encoding="utf-8")
        for marker in (
            'private static boolean approvedPublicHelp(Uri uri)',
            '"https".equalsIgnoreCase(uri.getScheme())',
            '"public.com".equalsIgnoreCase(uri.getHost())',
            '"/signup".equals(path)',
            '"/api/docs/quickstart".equals(path)',
            'uri.getQuery() != null',
            'uri.getFragment() != null',
            'uri.getUserInfo() != null',
            'request.isForMainFrame() && request.hasGesture()',
            'approvedPublicHelp(request.getUrl())',
            'Intent.ACTION_VIEW',
            'Intent.CATEGORY_BROWSABLE',
            'startActivity(browser)',
            'return true;',
            'MIXED_CONTENT_NEVER_ALLOW',
            'setAcceptThirdPartyCookies(webView, false)',
        ):
            self.assertIn(marker,java)
        self.assertNotIn("addJavascriptInterface(",java)
        self.assertNotIn("setAllowUniversalAccessFromFileURLs(true)",java)
        self.assertNotIn("http://public.com",java)
        self.assertNotIn("PUBLIC_API_SECRET",java)
        self.assertNotIn("api.public.com",java)

    def test_android_debug_release_version_increments(self):
        gradle=(ROOT/"android/app/build.gradle.kts").read_text(encoding="utf-8")
        workflow=(ROOT/".github/workflows/android-apk.yml").read_text(encoding="utf-8")
        self.assertIn("versionCode = 1917",gradle)
        self.assertIn('versionName = "0.19.17"',gradle)
        self.assertIn("EdgePilot-v0.19.17-public-onboarding-debug-apk",workflow)


if __name__=="__main__":
    unittest.main()
