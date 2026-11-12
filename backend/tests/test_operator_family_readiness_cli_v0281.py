"""v0.2.81: SSH-only operator CLI emits sanitized status, never secrets.

The current production files and env variables are not touched. No SSH, HTTP,
backup, Render, or Public access occurs during these tests.
"""
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "inspect_family_invitation_readiness.py"
APPROVAL = "INSPECT PRIVATE FAMILY READINESS ONLY"


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "edgepilot_private_family_rollout_operator", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FamilyReadinessOperatorCLITests(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()
        self.fake_env = {
            "EDGE_FAMILY_ROLLOUT_PREFLIGHT_ALLOWED": "true",
            "EDGE_DB_PATH": "/data/edgepilot.db",
            "EDGE_TENANT_DB_PATH": "/data/edgepilot-tenants.db",
            # Deliberately NOT a real key; the called inspection is mocked.
            "EDGE_CREDENTIAL_KEY": "SYNTHETIC-NEVER-USE-FAKE-KEY",
        }
        self.report = {
            "inspection": "passed",
            "independent_owner_initialized": True,
            "legacy_database_present_and_separate": True,
            "legacy_login_end_to_end_verified": False,
            "public_network_verification_performed": False,
            "enrollment_currently_disabled": True,
            "member_registration_authorized": False,
            "live_trading_enabled": False,
            "autonomous_orders_enabled": False,
            "bank_transfers_enabled": False,
        }

    def invoke(self, args, *, env=None, report=None, exception=None):
        output, errors = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, self.fake_env if env is None else env,
                        clear=True):
            with patch.object(
                self.tool.preflight, "inspect_first_invitation_readiness",
                side_effect=exception,
                return_value=self.report if report is None else report) as inspect:
                with redirect_stdout(output), redirect_stderr(errors):
                    status = self.tool.main(args)
        return status, output.getvalue(), errors.getvalue(), inspect

    def test_exact_ephemeral_opt_in_prints_only_aggregate_sanitized_json(self):
        code, output, errors, inspect = self.invoke(
            ["--approve", APPROVAL])
        self.assertEqual(code, 0)
        self.assertEqual(errors, "")
        self.assertEqual(json.loads(output), self.report)
        self.assertEqual(inspect.call_count, 1)
        self.assertNotIn("SYNTHETIC-NEVER", output)
        self.assertNotIn("/data/", output)
        self.assertFalse(json.loads(output)["member_registration_authorized"])

    def test_invalid_approval_or_ephemeral_flag_refuses_without_opening_db(self):
        cases = [
            ([], self.fake_env),
            (["--approve", "INVITE A REAL USER"], self.fake_env),
            (["--approve", APPROVAL, "--verbose"], self.fake_env),
            (["--approve", APPROVAL], {
                **self.fake_env,
                "EDGE_FAMILY_ROLLOUT_PREFLIGHT_ALLOWED": "false"}),
            (["--approve", APPROVAL], {
                **self.fake_env,
                "EDGE_TENANT_DB_PATH": "/data/owner-other.db"}),
            (["--approve", APPROVAL], {
                **self.fake_env,
                "EDGE_DB_PATH": "/data/edgepilot-tenants.db"}),
        ]
        for args, env in cases:
            with self.subTest(args=args, env_flag=env.get(
                    "EDGE_FAMILY_ROLLOUT_PREFLIGHT_ALLOWED")):
                code, stdout, stderr, inspect = self.invoke(args, env=env)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertTrue(stderr.strip())
                inspect.assert_not_called()

    def test_inspection_refusal_and_unexpected_errors_are_never_echoed(self):
        for exception in (
            self.tool.preflight.FamilyRolloutReadinessDenied(
                "SYNTHETIC-NEVER-LOG-OWNER-IDENTITY"),
            RuntimeError("SYNTHETIC-NEVER-LOG-CREDENTIAL"),
        ):
            with self.subTest(exception=type(exception).__name__):
                code, stdout, stderr, inspect = self.invoke(
                    ["--approve", APPROVAL], exception=exception)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertIn("DENIED", stderr)
                self.assertNotIn("SYNTHETIC-NEVER-LOG", stderr)
                self.assertEqual(inspect.call_count, 1)

    def test_rejects_a_report_that_could_appear_to_authorize_execution(self):
        for changed in (
            {"member_registration_authorized": True},
            {"live_trading_enabled": True},
            {"autonomous_orders_enabled": True},
            {"bank_transfers_enabled": True},
            {"enrollment_currently_disabled": False},
            {"inspection": "unknown"},
        ):
            with self.subTest(changed=changed):
                code, stdout, stderr, inspect = self.invoke(
                    ["--approve", APPROVAL],
                    report={**self.report, **changed})
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertIn("DENIED", stderr)

    def test_script_cannot_be_reached_by_web_app_startup(self):
        backend = SCRIPT.parents[1]
        app = (backend / "app.py").read_text(encoding="utf-8")
        dockerfile = (backend / "Dockerfile").read_text(encoding="utf-8")
        module = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("inspect_family_invitation_readiness", app)
        self.assertNotIn("inspect_family_invitation_readiness", dockerfile)
        self.assertIn('if __name__ == "__main__":', module)
        self.assertIn("raise SystemExit(main())", module)
        for forbidden in (
            "flask", "requests.", "app.run(", "subprocess.",
            "os.environ[", "update_environment_variables", "DELETE FROM",
        ):
            self.assertNotIn(forbidden, module)


if __name__ == "__main__":
    unittest.main()
