"""v0.2.42 isolated Android staging package and website association tests.

Only local fake configuration. No real Public or EdgePilot credentials, outside
network operations, live service changes, trades or device passkeys.
"""
import importlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
STAGE="staging.belenoscreations.biz"
OWNER="edgepilot.belenoscreations.biz"
FP=":".join(["AA"]*32)


class StagingAndroidIsolation(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="edge-stage-")
        self.env=patch.dict(os.environ,{
            "EDGE_DB_PATH":self.temp.name+"/staging.db",
            "EDGE_ANDROID_CERT_SHA256":FP,
            "EDGE_ANDROID_ASSOCIATION_PACKAGE":"com.edgepilot.mobile.staging",
            "EDGE_ISOLATED_STAGING":"true",
            "EDGE_WEBAUTHN_RP_ID":STAGE,
            "EDGE_WEBAUTHN_ORIGIN":"https://"+STAGE,
            "EDGE_APP_TOKEN":"",
            "PUBLIC_API_SECRET":"",
            "EDGE_CREDENTIAL_KEY":"",
            "EDGE_TENANT_ACCOUNT_READS_ENABLED":"false",
            "EDGE_TENANT_MONITOR_PREVIEW_ENABLED":"false",
            "EDGE_TENANT_WATCHLIST_EDIT_ENABLED":"false",
            "EDGE_AUTOMATION_WORKER_ENABLED":"false",
            "ENABLE_LIVE_ORDERS":"false",
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED":"false",
            "EDGE_TENANT_PUBLIC_READONLY_ENABLED":"false",
            "EDGE_TENANT_SCHEMA_PREPARE":"true",
            "EDGE_IDENTITY_AUTH_ENABLED":"true",
            "EDGE_TENANT_PASSKEYS_ENABLED":"true",
            "EDGE_TENANT_SIGNUP_ENABLED":"true",
        })
        self.env.start()
        import app
        self.client=importlib.reload(app).app.test_client()

    def tearDown(self):
        self.env.stop()
        import app
        importlib.reload(app)
        self.temp.cleanup()

    def get(self,host=STAGE):
        return self.client.get("/.well-known/assetlinks.json",base_url="https://"+host)

    def test_staging_link_only_on_isolated_owned_domain(self):
        r=self.get()
        self.assertEqual(r.status_code,200,r.get_data(as_text=True))
        self.assertEqual(r.get_json()[0]["target"]["package_name"],
                         "com.edgepilot.mobile.staging")
        self.assertEqual(r.get_json()[0]["target"]["sha256_cert_fingerprints"],[FP])
        self.assertIn("delegate_permission/common.get_login_creds",
                      r.get_json()[0]["relation"])
        self.assertEqual(self.get(OWNER).status_code,404)

    def test_staging_never_inherits_live_keys_or_incomplete_config(self):
        invalid={
            "EDGE_ANDROID_ASSOCIATION_PACKAGE":["","com.edgepilot.mobile","com.other"],
            "EDGE_ISOLATED_STAGING":["false",""],
            "EDGE_WEBAUTHN_RP_ID":[OWNER,"fake.example.org",""],
            "EDGE_WEBAUTHN_ORIGIN":["https://"+OWNER,"http://"+STAGE],
            "EDGE_DB_PATH":["/data/edgepilot.db"],
            "EDGE_APP_TOKEN":["fake-owner-secret"],
            "PUBLIC_API_SECRET":["fake-provider-secret"],
            "EDGE_AUTOMATION_WORKER_ENABLED":["true"],
            "ENABLE_LIVE_ORDERS":["true"],
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED":["true"],
            "EDGE_TENANT_PUBLIC_READONLY_ENABLED":["true"],
            "EDGE_ANDROID_CERT_SHA256":["","invalid"],
        }
        for key,values in invalid.items():
            for value in values:
                with self.subTest(setting=key,value=value):
                    with patch.dict(os.environ,{key:value}):
                        self.assertEqual(self.get().status_code,404)

    def test_isolated_staging_process_startup_refuses_unsafe_settings(self):
        from engine import staging_isolation
        good=dict(os.environ)
        self.assertTrue(staging_isolation.validate(good))
        unsafe={
            "EDGE_ISOLATED_STAGING":["maybe"],
            "EDGE_ANDROID_ASSOCIATION_PACKAGE":["com.edgepilot.mobile",""],
            "EDGE_WEBAUTHN_RP_ID":[OWNER,"example.invalid"],
            "EDGE_DB_PATH":["/data/edgepilot.db","/tmp/../data/edgepilot.db"],
            "EDGE_APP_TOKEN":["fake"],
            "PUBLIC_API_SECRET":["fake"],
            "EDGE_CREDENTIAL_KEY":["fake"],
            "EDGE_AUTOMATION_WORKER_ENABLED":["true"],
            "ENABLE_LIVE_ORDERS":["true"],
            "EDGE_TENANT_ACCOUNT_READS_ENABLED":["true"],
            "EDGE_TENANT_MONITOR_PREVIEW_ENABLED":["true"],
            "EDGE_TENANT_WATCHLIST_EDIT_ENABLED":["true"],
            "EDGE_TENANT_PUBLIC_VAULT_ENABLED":["true"],
            "EDGE_TENANT_PUBLIC_READONLY_ENABLED":["true"],
            "EDGE_TENANT_SCHEMA_PREPARE":["false"],
            "EDGE_IDENTITY_AUTH_ENABLED":["false"],
            "EDGE_TENANT_SIGNUP_ENABLED":["false"],
            "EDGE_TENANT_PASSKEYS_ENABLED":["false"],
            "EDGE_ANDROID_CERT_SHA256":["malformed"],
        }
        for name,values in unsafe.items():
            for value in values:
                with self.subTest(name=name,value=value):
                    with self.assertRaises(staging_isolation.StagingIsolationDenied):
                        staging_isolation.validate({**good,name:value})
        self.assertFalse(staging_isolation.validate({
            **good,"EDGE_ISOLATED_STAGING":"false"}))

    def test_default_owner_site_remains_bound_to_original_package(self):
        with patch.dict(os.environ,{
            "EDGE_ANDROID_ASSOCIATION_PACKAGE":"",
            "EDGE_ISOLATED_STAGING":"false",
        }):
            response=self.get(OWNER)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.get_json()[0]["target"]["package_name"],
                             "com.edgepilot.mobile")

    def test_gradle_host_and_package_pinning_separate_from_owner(self):
        gradle=(ROOT/"android/app/build.gradle.kts").read_text()
        activity=(ROOT/"android/app/src/main/java/com/edgepilot/mobile/MainActivity.java").read_text()
        manifest=(ROOT/"android/app/src/main/AndroidManifest.xml").read_text()
        for text in (
            'applicationId = "com.edgepilot.mobile"',
            'applicationIdSuffix = ".staging"',
            'versionNameSuffix = "-staging"',
            'manifestPlaceholders["edgePilotAppLabel"] = "EdgePilot Staging"',
            'edgePilotStagingHost',
            'unconfigured.edgepilot.invalid',
            'stagingHost != "edgepilot.belenoscreations.biz"',
            'buildConfigField("String", "EDGE_HOST",',
        ):
            self.assertIn(text,gradle)
        self.assertIn("BuildConfig.EDGE_HOST",activity)
        self.assertNotIn('private static final String HOST = "edgepilot.belenoscreations.biz"',activity)
        self.assertIn('android:label="${edgePilotAppLabel}"',manifest)
        self.assertNotIn("addJavascriptInterface(",activity)
        self.assertIn("shouldInterceptRequest(",activity)

    def test_manual_only_signing_workflow_and_unchanged_owner_release(self):
        stage=(ROOT/".github/workflows/android-staging-signed.yml").read_text()
        prod=(ROOT/".github/workflows/android-private-signed.yml").read_text()
        debug=(ROOT/".github/workflows/android-apk.yml").read_text()
        for text in (
            "workflow_dispatch:","staging_host:","required: true",
            "if: github.ref == 'refs/heads/main'",":app:assembleStaging",
            "app-staging-unsigned.apk","com[.]edgepilot[.]mobile[.]staging",
            "python3 android/tools/verify_signed_apk_cert.py",
            "retention-days: 7","env:EDGE_ANDROID_SIGNING_STORE_PASS",
            "env:EDGE_ANDROID_SIGNING_KEY_PASS",
        ):
            self.assertIn(text,stage)
        for forbidden in ("pull_request:","  push:",":app:assembleRelease",
                          "app-release-unsigned.apk","--ks-pass pass:",
                          "--key-pass pass:","set -x"):
            self.assertNotIn(forbidden,stage)
        self.assertIn(":app:assembleRelease",prod)
        self.assertIn("app-release-unsigned.apk",prod)
        self.assertIn("name='com[.]edgepilot[.]mobile'",prod)
        self.assertIn(":app:assembleDebug",debug)
        self.assertIn(":app:assembleStaging",debug)
        self.assertIn("app-debug.apk",debug)
        self.assertNotIn("EDGE_ANDROID_SIGNING_JKS_B64",debug)


if __name__=="__main__":
    unittest.main()
