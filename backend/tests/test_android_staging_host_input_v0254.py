"""v0.2.54: Execute the exact workflow hostname guard against mobile input.

No GitHub dispatch, Android signing, real domain requests, or broker access.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/android-staging-signed.yml"
EXPECTED = "staging-edgepilot.belenoscreations.biz"


def validate_workflow_input(raw):
    """Run only the workflow's checked shell block in a local Bash process."""
    text = WORKFLOW.read_text(encoding="utf-8")
    block = text.split("      - name: Verify distinct owned staging hostname\n", 1)[1]
    block = block.split("      - name: Use JDK 17\n", 1)[0]
    script = textwrap.dedent(block.split("        run: |\n", 1)[1])
    with tempfile.TemporaryDirectory() as tmp:
        gh_env = Path(tmp) / "gh-env"
        env = {**os.environ, "EDGE_STAGING_HOST_RAW": raw, "GITHUB_ENV": str(gh_env)}
        run = subprocess.run(["bash", "-c", script], env=env,
                             capture_output=True, text=True, timeout=5)
        output = gh_env.read_text(encoding="utf-8") if gh_env.exists() else ""
    return run.returncode, output


class AndroidStagingHostInputTests(unittest.TestCase):
    def test_phone_keyboard_whitespace_is_removed(self):
        for raw in (
            EXPECTED, EXPECTED + " ", " " + EXPECTED,
            "\t" + EXPECTED + " \t", "\r\n" + EXPECTED + "\r\n",
        ):
            with self.subTest(raw=repr(raw)):
                status, value = validate_workflow_input(raw)
                self.assertEqual(status, 0)
                self.assertEqual(value, "EDGE_STAGING_HOST=" + EXPECTED + "\n")

    def test_non_staging_host_still_fails_closed(self):
        for raw in (
            "", " ", "edgepilot.belenoscreations.biz",
            "http://" + EXPECTED, "https://" + EXPECTED, EXPECTED + "/account",
            EXPECTED + ".attacker.test", "staging..belenoscreations.biz",
            EXPECTED.replace("-", "_"), "example.com",
            EXPECTED + " something", "a b.belenoscreations.biz",
            EXPECTED + "\nEDGE_APP_TOKEN=not-a-key",
            "staging-edgepilot.BELENOSCREATIONS.BIZ",
        ):
            with self.subTest(raw=repr(raw)):
                status, value = validate_workflow_input(raw)
                self.assertNotEqual(status, 0)
                self.assertEqual(value, "")

    def test_signed_build_uses_only_normalized_validated_hostname(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        verified = source.split("      - name: Verify distinct owned staging hostname\n", 1)[1].split("      - name: Use JDK 17\n", 1)[0]
        built = source.split("      - name: Assemble unsigned isolated staging APK\n", 1)[1].split("      - name: Sign, verify, and pin", 1)[0]
        self.assertIn('EDGE_STAGING_HOST_RAW: ${{ inputs.staging_host }}', verified)
        self.assertIn('>> "$GITHUB_ENV"', verified)
        self.assertIn("-PedgePilotStagingHost=$EDGE_STAGING_HOST", built)
        self.assertNotIn("inputs.staging_host", built)
        self.assertIn("if: github.ref == 'refs/heads/main'", source)
        self.assertIn("com[.]edgepilot[.]mobile[.]staging", source)
        self.assertNotIn("  push:", source)
        self.assertNotIn("pull_request:", source)


if __name__ == "__main__":
    unittest.main()
