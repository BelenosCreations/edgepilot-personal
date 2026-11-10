"""v0.2.30 account page and Android association safety tests.

No passkey private keys, real biometrics, real Public connections or APKs.
WebAuthn cryptography is covered separately in the existing passkey tests.
"""
import importlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
HOST="https://edgepilot.example.test"


class AccountPageSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="edgepilot-mobile-auth-")
        self.env=patch.dict(os.environ,{
          "EDGE_DB_PATH":self.temp.name+"/edgepilot.db",
          "EDGE_TENANT_SCHEMA_PREPARE":"false",
          "EDGE_IDENTITY_AUTH_ENABLED":"false",
          "EDGE_TENANT_PASSKEYS_ENABLED":"false",
          "EDGE_ANDROID_CERT_SHA256":"",
          "EDGE_AUTOMATION_WORKER_ENABLED":"false"
        })
        self.env.start()
        import app
        self.mod=importlib.reload(app)
        self.client=self.mod.app.test_client()

    def tearDown(self):
        self.env.stop()
        import app
        importlib.reload(app)
        self.temp.cleanup()

    def test_account_screen_is_unprivileged_and_no_identity_api_is_active(self):
        response=self.client.get("/account",base_url=HOST)
        self.assertEqual(response.status_code,200)
        self.assertIn(b"/assets/identity.js",response.data)
        self.assertIn(b"EdgePilot",response.data)
        self.assertIn(b"Add biometric passkey",response.data)
        self.assertNotIn(b"synthetic-Public-key",response.data)
        js=self.client.get("/assets/identity.js",base_url=HOST)
        self.assertEqual(js.status_code,200)
        for snippet in (b"navigator.credentials.get",b"navigator.credentials.create",
                        b"requestId",b"X-Edge-Identity-CSRF",
                        b'credentials:"same-origin"'):
            self.assertIn(snippet,js.data)
        self.assertNotIn(b"localStorage",js.data)
        self.assertNotIn(b"sessionStorage",js.data)
        self.assertNotIn(b"document.cookie",js.data)
        self.assertEqual(self.client.post(
            "/api/identity/passkeys/authenticate/options",
            base_url=HOST,headers={"Origin":HOST},json={}).status_code,404)
        self.assertEqual(self.client.get("/api/identity/session",
            base_url=HOST).status_code,404)

    def test_assetlinks_fail_closed_without_exact_valid_signing_certificate(self):
        self.assertEqual(self.client.get(
            "/.well-known/assetlinks.json",base_url=HOST).status_code,404)
        for bad in ("not-a-real-fingerprint","AA:"*31+"XX","AA:"*30+"BB",
                    "A"*64,"AA:"*32+"extra"):
            with patch.dict(os.environ,{"EDGE_ANDROID_CERT_SHA256":bad}):
                self.assertEqual(self.client.get("/.well-known/assetlinks.json",
                                                 base_url=HOST).status_code,404)
        fingerprint="ab:"*31+"cd"
        with patch.dict(os.environ,{"EDGE_ANDROID_CERT_SHA256":fingerprint}):
            response=self.client.get("/.well-known/assetlinks.json",base_url=HOST)
        self.assertEqual(response.status_code,200)
        association=response.get_json()
        self.assertEqual(len(association),1)
        target=association[0]["target"]
        self.assertEqual(target["package_name"],"com.edgepilot.mobile")
        self.assertEqual(target["namespace"],"android_app")
        self.assertEqual(target["sha256_cert_fingerprints"],[fingerprint.upper()])
        self.assertIn("delegate_permission/common.get_login_creds",
                      association[0]["relation"])
        self.assertNotIn("delegate_permission/common.handle_all_urls",
                         association[0]["relation"])

    def test_android_must_require_system_webauthn_and_secure_origin(self):
        java=(ROOT/"android/app/src/main/java/com/edgepilot/mobile/MainActivity.java").read_text()
        gradle=(ROOT/"android/app/build.gradle.kts").read_text()
        manifest=(ROOT/"android/app/src/main/AndroidManifest.xml").read_text()
        for value in ("WebViewFeature.WEB_AUTHENTICATION",
                      "WEB_AUTHENTICATION_SUPPORT_FOR_APP",
                      "setWebAuthenticationSupport(", "MIXED_CONTENT_NEVER_ALLOW",
                      "setAcceptThirdPartyCookies(webView, false)",
                      "shouldInterceptRequest("):
            self.assertIn(value,java)
        for library in ("androidx.webkit:webkit:1.16.0",
                        "androidx.credentials:credentials:1.6.0",
                        "androidx.credentials:credentials-play-services-auth:1.6.0"):
            self.assertIn(library,gradle)
        self.assertIn('android:usesCleartextTraffic="false"',manifest)
        self.assertIn('android:allowBackup="false"',manifest)
        self.assertNotIn("addJavascriptInterface(",java)

if __name__=="__main__":
    unittest.main()
