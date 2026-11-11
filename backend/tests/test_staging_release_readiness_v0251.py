"""v0.2.51: static staging deployment safety, no Render provisioning."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from engine import staging_release_readiness as readiness

PROPOSAL = (Path(__file__).resolve().parents[2] /
            "deploy/staging/render-service.proposal.json")


class StagingReadinessTests(unittest.TestCase):
    def proposal(self):
        return json.loads(PROPOSAL.read_text(encoding="utf-8"))

    def test_repo_proposal_is_non_deployable_and_cost_gated(self):
        report = readiness.inspect_file(PROPOSAL)
        self.assertTrue(report["staticProposalValidated"])
        for key in ("serviceCreated", "verifiedCertificateSupplied",
                    "customDomainVerified", "renderChargesApproved",
                    "productionResourcesChanged", "physicalPasskeyValidated"):
            self.assertFalse(report[key])
        self.assertTrue(report["needsExternalApprovalAndEvidence"])
        self.assertTrue(report["hasEphemeralDatabase"])
        doc = self.proposal()
        self.assertEqual(doc["plan"], "free")
        self.assertEqual(doc["autoDeploy"], "no")
        self.assertFalse(doc["serviceCreationApprovedByThisFile"])
        self.assertNotIn("EDGE_APP_TOKEN", str(doc))
        self.assertNotIn("PUBLIC_API_SECRET", str(doc))
        self.assertNotIn("OPENAI_API_KEY", str(doc))

    def test_injected_owner_secret_or_trading_controls_fail_closed(self):
        cases = (
            ("EDGE_APP_TOKEN", "not-a-real-owner-token"),
            ("PUBLIC_API_SECRET", "fake-production-credential"),
            ("OPENAI_API_KEY", "sk-NEVER-ACTUAL"),
            ("EDGE_CREDENTIAL_KEY", "fake-key"),
            ("ENABLE_LIVE_ORDERS", "true"),
            ("EDGE_AUTOMATION_WORKER_ENABLED", "true"),
            ("EDGE_TENANT_PUBLIC_VAULT_ENABLED", "true"),
            ("EDGE_TENANT_PUBLIC_READONLY_ENABLED", "true"),
            ("EDGE_TENANT_ACCOUNT_READS_ENABLED", "true"),
            ("EDGE_TENANT_MONITOR_PREVIEW_ENABLED", "true"),
            ("EDGE_TENANT_WATCHLIST_EDIT_ENABLED", "true"),
        )
        for key, value in cases:
            with self.subTest(key=key), self.assertRaises(
                    readiness.StagingProposalDenied):
                data = self.proposal()
                found = next((x for x in data["envVars"] if x["key"] == key), None)
                if found:
                    found["value"] = value
                else:
                    data["envVars"].append({"key": key, "value": value})
                readiness.inspect(data)

    def test_domain_package_database_and_redeploy_guard_cannot_drift(self):
        cases = (
            ("candidateCustomHostname", "edgepilot.belenoscreations.biz"),
            ("candidateCustomHostname", "attacker.example"),
            ("autoDeploy", "yes"),
            ("branch", "feature/untrusted"),
            ("plan", "starter"),
            ("region", "oregon"),
            ("repo", "https://github.com/outsider/repo"),
            ("serviceCreationApprovedByThisFile", True),
        )
        for key, value in cases:
            with self.subTest(key=key), self.assertRaises(
                    readiness.StagingProposalDenied):
                data = self.proposal()
                data[key] = value
                readiness.inspect(data)
        for key, value in (
            ("EDGE_DB_PATH", "/data/edgepilot.db"),
            ("EDGE_ANDROID_ASSOCIATION_PACKAGE", "com.edgepilot.mobile"),
            ("EDGE_WEBAUTHN_RP_ID", "edgepilot.belenoscreations.biz"),
            ("EDGE_WEBAUTHN_ORIGIN", "https://edgepilot.belenoscreations.biz"),
            ("EDGE_ANDROID_CERT_SHA256", ":".join(["A1"] * 32)),
            ("EDGE_ISOLATED_STAGING", "false"),
        ):
            with self.subTest(env_key=key), self.assertRaises(
                    readiness.StagingProposalDenied):
                data = self.proposal()
                next(x for x in data["envVars"] if x["key"] == key)["value"] = value
                readiness.inspect(data)

    def test_duplicate_unapproved_environment_and_incomplete_policy_denied(self):
        data = self.proposal()
        data["envVars"].append(deepcopy(data["envVars"][0]))
        with self.assertRaises(readiness.StagingProposalDenied):
            readiness.inspect(data)
        data = self.proposal()
        data["envVars"].pop()
        with self.assertRaises(readiness.StagingProposalDenied):
            readiness.inspect(data)
        data = self.proposal()
        data["blockedUntil"] = []
        with self.assertRaises(readiness.StagingProposalDenied):
            readiness.inspect(data)

    def test_readiness_never_contacts_render_broker_or_external_provider(self):
        with patch("requests.sessions.Session.request",
                   side_effect=AssertionError("Network not permitted")):
            self.assertTrue(readiness.inspect(self.proposal())
                            ["staticProposalValidated"])


if __name__ == "__main__":
    unittest.main()
