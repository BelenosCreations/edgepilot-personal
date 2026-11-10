"""v0.2.38: signer-pinned manual Android build is fail closed.

No actual signing keys, private passwords, or real certificates in tests.
The signed workflow is intentionally not triggered by PR or push events.
"""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "android/tools/verify_signed_apk_cert.py"
WORKFLOW = ROOT / ".github/workflows/android-private-signed.yml"
DEBUG_WORKFLOW = ROOT / ".github/workflows/android-apk.yml"


def _module():
    spec = importlib.util.spec_from_file_location("edgepilot_signed_cert", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AndroidSignerPreflightTests(unittest.TestCase):
    def setUp(self):
        self.signer = _module()
        self.expected = "ab" * 32
        self.good = (
            "Verifies\n"
            "Verified using v1 scheme (JAR signing): false\n"
            "Verified using v2 scheme (APK Signature Scheme v2): true\n"
            "Signer #1 certificate SHA-256 digest: " + self.expected + "\n"
        )

    def test_one_expected_signer_with_64_hex_bytes_passes(self):
        self.assertTrue(self.signer.check_apk_identity(self.good, self.expected))
        formatted = ":".join(self.expected[i:i+2] for i in range(0,64,2)).upper()
        self.assertTrue(self.signer.check_apk_identity(self.good, formatted))
        self.assertEqual(self.signer.normalize_fingerprint(formatted),self.expected)

    def test_missing_malformed_mismatched_and_multiple_signers_denied(self):
        invalid = (
            ("", self.expected),
            ("Signer #1 certificate SHA-256 digest: " + self.expected,self.expected),
            (self.good,self.expected[:-2]),
            (self.good,"unknown"),
            (self.good,"ff"*32),
            (self.good + "Signer #2 certificate SHA-256 digest: " + "ab"*32,self.expected),
            (self.good.replace("Signer #1","Signer #2"),self.expected),
            (self.good.replace("ab"*32,"f"*64),self.expected),
        )
        for report,expected in invalid:
            with self.subTest(report=str(report)[:35],expected=str(expected)[:15]):
                with self.assertRaises(self.signer.SigningIdentityDenied):
                    self.signer.check_apk_identity(report,expected)

    def test_offline_preflight_reads_only_report_and_expected_fingerprint(self):
        with tempfile.TemporaryDirectory(prefix="edgepilot-sign-test-") as temp:
            report=Path(temp)/"signer.txt"
            report.write_text(self.good,encoding="utf-8")
            with patch.dict(os.environ,{"EDGE_ANDROID_EXPECTED_CERT_SHA256":self.expected}):
                with patch("sys.argv",["verify_signed_apk_cert.py",str(report)]):
                    self.assertEqual(self.signer.main(),0)
            with patch.dict(os.environ,{"EDGE_ANDROID_EXPECTED_CERT_SHA256":"00"*32}):
                with patch("sys.argv",["verify_signed_apk_cert.py",str(report)]):
                    self.assertEqual(self.signer.main(),1)

    def test_workflow_manual_main_only_never_uploads_key_or_uses_shell_secret_args(self):
        wf = WORKFLOW.read_text(encoding="utf-8")
        for required in (
            "workflow_dispatch:",
            "if: github.ref == 'refs/heads/main'",
            "permissions:\n  contents: read",
            "assembleRelease",
            "apksigner",
            "verify --min-sdk-version 26 --verbose --print-certs",
            "python3 android/tools/verify_signed_apk_cert.py",
            "base64 --decode",
            "set -euo pipefail",
            "umask 077",
            "trap 'rm -f",
            "EDGE_ANDROID_EXPECTED_CERT_SHA256",
            "--ks-pass env:EDGE_ANDROID_SIGNING_STORE_PASS",
            "--key-pass env:EDGE_ANDROID_SIGNING_KEY_PASS",
            "if-no-files-found: error",
            "retention-days: 7",
            "EdgePilot-private-signed-test.apk",
        ):
            self.assertIn(required,wf)
        self.assertNotIn("pull_request:",wf)
        self.assertNotIn("  push:",wf)
        self.assertNotIn("assembleDebug",wf)
        self.assertNotIn("upload-artifact@v4\n        with:\n          path: $RUNNER_TEMP",wf)
        self.assertNotIn(".jks\n          if-no-files-found",wf)
        for forbidden in ("keytool -genkey", "apksigner sign --key ",
                          "set -x","--ks-pass pass:","--key-pass pass:"):
            self.assertNotIn(forbidden,wf)
        old=DEBUG_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("assembleDebug",old)
        self.assertNotIn("EDGE_ANDROID_SIGNING_JKS_B64",old)

    def test_key_storage_file_patterns_are_ignored(self):
        text=(ROOT/".gitignore").read_text(encoding="utf-8")
        for file_pattern in ("*.jks","*.keystore","*.p12","*.pfx"):
            self.assertIn(file_pattern,text)


if __name__=="__main__":
    unittest.main()
