"""v0.2.69: Android console owner bootstrap input handling tests.

Never writes live disks or prints passwords, usernames or broker secrets.
A real owner account is created only by the separately gated engine.
"""
import contextlib
import io
import os
import unittest
from unittest import mock

from tools import first_owner_bootstrap as cli


class InteractiveCapture(io.StringIO):
    def isatty(self):
        return True


class OwnerBootstrapPromptTests(unittest.TestCase):
    def setUp(self):
        self.env_patch=mock.patch.dict(os.environ, {
            "EDGE_DB_PATH":"/data/edgepilot.db",
            "EDGE_TENANT_DB_PATH":"/data/edgepilot-tenants.db",
        })
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.created=mock.patch.object(
            cli.permanent_owner_bootstrap, "create_first_owner",
            return_value={"created": True})
        self.mockcreate=self.created.start()
        self.addCleanup(self.created.stop)

    def go(self, typed, hidden):
        stdout=InteractiveCapture()
        stderr=io.StringIO()
        with (mock.patch.object(cli.sys, "stdin", mock.Mock(isatty=lambda: True)),
              mock.patch("builtins.input", side_effect=typed) as inp,
              mock.patch.object(cli.getpass, "getpass", side_effect=hidden) as sec,
              contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr)):
            status=cli.main()
        return status, stdout.getvalue(), stderr.getvalue(), inp, sec

    def test_manual_visible_approval_success_and_hidden_passwords(self):
        pw="SYNTHETIC-secret-not-to-log-password-2026"
        result,out,err,inp,sec=self.go(
            ["Belenos-Owner","Belenos-Owner",cli.permanent_owner_bootstrap.APPROVAL],
            [pw,pw])
        self.assertEqual(result,0)
        self.assertEqual(sec.call_count,2)
        self.assertEqual(inp.call_count,3)
        self.assertIn("First EdgePilot owner identity created",out)
        self.assertIn("visible",out)
        self.assertNotIn(pw,out+err)
        self.mockcreate.assert_called_once()
        kw=self.mockcreate.call_args.kwargs
        self.assertEqual(kw["approval"],cli.permanent_owner_bootstrap.APPROVAL)
        self.assertEqual(kw["login_name"],"Belenos-Owner")

    def test_empty_password_from_ghost_enter_fails_before_approval(self):
        result,out,err,inp,sec=self.go(["Label","login"],["",""])
        self.assertEqual(result,2)
        self.assertEqual(inp.call_count,2)
        self.assertIn("empty input",err)
        self.mockcreate.assert_not_called()

    def test_different_passwords_never_ask_approval_or_call_engine(self):
        result,out,err,inp,sec=self.go(
            ["Label","login"],["SYNTHETIC-one-2026","SYNTHETIC-two-2026"])
        self.assertEqual(result,2)
        self.assertEqual(inp.call_count,2)
        self.assertIn("did not match",err)
        self.mockcreate.assert_not_called()

    def test_short_password_never_asks_approval(self):
        result,out,err,inp,sec=self.go(["Label","login"],["short","short"])
        self.assertEqual(result,2)
        self.assertEqual(inp.call_count,2)
        self.assertIn("14",err)
        self.mockcreate.assert_not_called()

    def test_empty_approval_from_android_input_refuses_to_create(self):
        result,out,err,inp,sec=self.go(
            ["Label","login",""],["SYNTHETIC-long-password-2026"]*2)
        self.assertEqual(result,2)
        self.assertIn("Approval phrase not received exactly",err)
        self.mockcreate.assert_not_called()

    def test_owner_engine_denial_shows_only_sanitized_reason(self):
        self.mockcreate.side_effect=cli.permanent_owner_bootstrap.OwnerBootstrapDenied(
            "Existing tenant identities require a separate recovery procedure")
        result,out,err,inp,sec=self.go(
            ["Label","login",cli.permanent_owner_bootstrap.APPROVAL],
            ["SYNTHETIC-long-password-2026"]*2)
        self.assertEqual(result,2)
        self.assertIn("Existing tenant identities",err)
        self.assertNotIn("SYNTHETIC-long-password-2026",out+err)
        self.assertNotIn("Label",out+err)
        self.assertNotIn("login",out+err)
        self.assertIn("read-only readiness",err)


if __name__=="__main__":
    unittest.main()
