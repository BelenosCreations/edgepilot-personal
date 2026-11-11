"""Architecture regression gates for the approved shared-backend direction.

These are static non-activation checks, NOT passkey or multi-tenant end-to-end
acceptance. Fail if a future edit silently changes the currently isolated
identity or provider boundaries while the migration is incomplete.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class SharedBackendArchitectureGates(unittest.TestCase):
    def test_identity_is_dormant_until_explicitly_enabled(self):
        app = (ROOT / "backend/app.py").read_text(encoding="utf-8")
        self.assertIn("EDGE_IDENTITY_AUTH_ENABLED','false'", app)
        self.assertIn("EDGE_TENANT_PUBLIC_VAULT_ENABLED','false'", app)
        self.assertIn("EDGE_TENANT_PUBLIC_READONLY_ENABLED','false'", app)

    def test_web_authn_has_verified_origin_and_user_verification(self):
        source = (ROOT / "backend/engine/tenant_passkeys.py").read_text(encoding="utf-8")
        for required in (
            "verify_registration_response(", "verify_authentication_response(",
            "expected_rp_id=self.rp_id", "expected_origin=self.allowed_origins",
            "require_user_verification=True", "ResidentKeyRequirement.REQUIRED",
            "UserVerificationRequirement.REQUIRED",
            "identity_store.principal(",
        ):
            self.assertIn(required, source)
        self.assertNotIn("from flask import", source)

    def test_legacy_credentials_are_global_and_not_reused_as_tenant_vault(self):
        legacy = (ROOT / "backend/engine/broker_credentials.py").read_text(encoding="utf-8")
        app = (ROOT / "backend/app.py").read_text(encoding="utf-8")
        self.assertIn("provider TEXT PRIMARY KEY", legacy)
        self.assertIn("tenant_public_vault.TenantPublicVault(", app)
        self.assertIn("identity_auth_enabled", app)

    def test_shared_android_endpoint_not_per_user_backend_selector(self):
        java = (ROOT / "android/app/src/main/java/com/edgepilot/mobile/MainActivity.java").read_text(encoding="utf-8")
        self.assertIn("private static final String SITE", java)
        gradle = (ROOT / "android/app/build.gradle.kts").read_text(encoding="utf-8")
        self.assertIn("BuildConfig.EDGE_HOST", java)
        self.assertIn('"https://" + HOST + "/"', java)
        self.assertIn('applicationId = "com.edgepilot.mobile"', gradle)
        self.assertIn('edgepilot.belenoscreations.biz', gradle)
        self.assertIn('applicationIdSuffix = ".staging"', gradle)
        self.assertIn("setAcceptThirdPartyCookies(webView, false)", java)
        self.assertIn("MIXED_CONTENT_NEVER_ALLOW", java)

    def test_live_legacy_worker_remains_separate(self):
        from engine import tenant_route_audit
        report = tenant_route_audit.inspect_repo()
        self.assertTrue(report["legacyApiStillGlobalSingleOwner"])
        self.assertTrue(report["fullRouteAndWorkerRefactorRequired"])
        self.assertFalse(report["crossAccountProductionCutoverAllowed"])
        self.assertFalse(report["passkeyIdentityActivatedInProduction"])


if __name__ == "__main__":
    unittest.main()
