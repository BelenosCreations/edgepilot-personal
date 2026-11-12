"""v0.2.77 public-source CI guardrails: no real credentials or external calls.

These tests use synthetic strings generated at runtime inside throwaway local
Git repositories. They never use Render, Public, real GitHub secrets or a signer.
"""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
SCANNER = ROOT / "tools" / "public_git_history_scan.py"


class PublicRepositoryCIControls(unittest.TestCase):
    def test_regular_pr_ci_scans_checked_out_files_without_full_history_refetch(self):
        source = (WORKFLOWS / "tests.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request:", source)
        self.assertIn("branches: [main]", source)
        self.assertIn("permissions:\n  contents: read", source)
        self.assertIn("runs-on: ubuntu-latest", source)
        self.assertIn("cancel-in-progress: true", source)
        self.assertIn("python tools/public_git_history_scan.py", source)
        self.assertNotIn("fetch-depth: 0", source)
        self.assertNotIn("upload-artifact", source)
        self.assertNotIn("secrets.", source)

    def test_manual_full_history_scan_does_not_spend_on_unrelated_prs(self):
        audit = (WORKFLOWS / "public-release-audit.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("workflow_dispatch:", audit)
        self.assertIn("pull_request:", audit)
        self.assertIn("tools/public_git_history_scan.py", audit)
        self.assertIn("fetch-depth: 0", audit)
        self.assertIn("persist-credentials: false", audit)
        self.assertIn("permissions:\n  contents: read", audit)
        self.assertIn("runs-on: ubuntu-latest", audit)
        self.assertIn("cancel-in-progress: true", audit)
        self.assertNotIn("secrets.", audit)

    def test_unsigned_apk_builds_on_android_changes_without_pr_artifacts(self):
        debug = (WORKFLOWS / "android-apk.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request:", debug)
        self.assertIn("android/**", debug)
        for variant in ("assembleDebug", "assembleRelease", "assembleStaging"):
            self.assertIn(variant, debug)
        self.assertIn("if: github.event_name == 'workflow_dispatch'", debug)
        self.assertIn("retention-days: 3", debug)
        self.assertIn("permissions:\n  contents: read", debug)
        self.assertIn("runs-on: ubuntu-latest", debug)
        self.assertIn("cancel-in-progress: true", debug)
        self.assertNotIn("EDGE_ANDROID_SIGNING_JKS_B64", debug)

    def test_signed_apk_signing_remains_manual_main_only(self):
        for filename in ("android-private-signed.yml",
                         "android-staging-signed.yml"):
            with self.subTest(workflow=filename):
                signed = (WORKFLOWS / filename).read_text(encoding="utf-8")
                self.assertIn("workflow_dispatch:", signed)
                self.assertNotIn("pull_request:", signed)
                self.assertNotIn("\n  push:", signed)
                self.assertIn("if: github.ref == 'refs/heads/main'", signed)
                self.assertIn("permissions:\n  contents: read", signed)
                self.assertIn("runs-on: ubuntu-latest", signed)
                self.assertIn("cancel-in-progress: false", signed)
                self.assertIn("EDGE_ANDROID_SIGNING_JKS_B64", signed)
                self.assertNotIn("set -x", signed)
                self.assertNotIn("--ks-pass pass:", signed)
                self.assertNotIn("--key-pass pass:", signed)

    def test_secret_file_types_remain_excluded(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for path_pattern in (
            "**/.env", "**/.env.*", "**/*.db", "**/*.sqlite",
            "**/*.sqlite3", "*.jks", "*.keystore", "*.p12",
            "*.pfx", "*.pem", "*.key", "*.p8", "*.gpg", "*.asc",
            "**/recovery-key.b64", "**/recovery_key.b64",
        ):
            self.assertIn(path_pattern, ignored)

    @staticmethod
    def _local_git_repo(folder, filename, content):
        def call(*args):
            return subprocess.run(
                ["git", *args], cwd=folder, capture_output=True,
                check=True, text=True
            )
        call("init", "-q")
        call("config", "user.name", "Synthetic CI Test")
        call("config", "user.email", "synthetic@example.test")
        (Path(folder) / filename).write_text(content, encoding="utf-8")
        call("add", filename)
        call("commit", "-q", "-m", "synthetic test fixture")

    @staticmethod
    def _scan(folder):
        return subprocess.run(
            [sys.executable, str(SCANNER)],
            cwd=folder, capture_output=True, text=True, timeout=30
        )

    def test_synthetic_clean_checkout_passes_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            self._local_git_repo(folder, "readme.txt", "No credentials here.\n")
            scan = self._scan(folder)
            self.assertEqual(scan.returncode, 0, scan.stderr + scan.stdout)
            self.assertIn("PASS:", scan.stdout)

    def test_synthetic_token_detected_but_never_printed(self):
        # Splitting the synthetic marker prevents creating a matching
        # credential-shaped string in the tracked test source itself.
        pretend = "gh" + "p_" + ("Z" * 32)
        with tempfile.TemporaryDirectory() as folder:
            self._local_git_repo(folder, "fixture.txt", pretend + "\n")
            scan = self._scan(folder)
            self.assertEqual(scan.returncode, 1, scan.stderr + scan.stdout)
            self.assertIn("github-token", scan.stdout)
            self.assertNotIn(pretend, scan.stdout)
            self.assertNotIn(pretend, scan.stderr)


if __name__ == "__main__":
    unittest.main()
