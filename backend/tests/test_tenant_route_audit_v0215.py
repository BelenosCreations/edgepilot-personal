"""Guard legacy API/worker boundaries before any tenant history activation."""
import ast
import unittest
from pathlib import Path

from engine import tenant_route_audit

ROOT=Path(__file__).resolve().parents[2]


class TenantBoundaryAuditTests(unittest.TestCase):
    def setUp(self):
        self.app=(ROOT/"backend"/"app.py").read_text()
        self.worker=(ROOT/"backend"/"engine"/"automation_worker.py").read_text()

    def test_current_legacy_api_worker_are_explicitly_cutover_blockers(self):
        audit=tenant_route_audit.inspect_sources(self.app,self.worker)
        self.assertEqual(audit["identityRoutesReviewed"],24)
        self.assertTrue(audit["tenantSessionControlsDefaultOff"])
        self.assertTrue(audit["tenantSessionControlsOtherDeviceOnly"])
        self.assertTrue(audit["tenantPasswordChangeDefaultOff"])
        self.assertTrue(audit["tenantPasswordChangeSessionRevocation"])
        self.assertTrue(audit["tenantWatchlistEditDefaultOff"])
        self.assertTrue(audit["tenantWatchlistEditSessionAndCsrfRequired"])
        self.assertTrue(audit["tenantMonitorPreviewDefaultOff"])
        self.assertTrue(audit["tenantMonitorPlannerWiredToReadOnlyHttp"])
        self.assertTrue(audit["passkeyIdentityDefaultOff"])
        self.assertTrue(audit["passkeyAuthRequiresVerifiedWebAuthn"])
        self.assertTrue(audit["tenantSignupDefaultOff"])
        self.assertTrue(audit["tenantRegistrationRequiresOneUseInvite"])
        self.assertGreater(audit["legacySingleOwnerRoutes"],20)
        self.assertEqual(audit["legacyRoutesConvertedToTenantScope"],0)
        self.assertTrue(audit["legacyWorkerUsesGlobalSelectedAccount"])
        self.assertFalse(audit["tenantHistoryDetailsExposedByApi"])
        self.assertFalse(audit["historyImportEndpointEnabled"])
        self.assertFalse(audit["crossAccountProductionCutoverAllowed"])
        self.assertTrue(audit["auditIsStaticNotProofOfRuntimeIsolation"])
        self.assertTrue(audit["fullRouteAndWorkerRefactorRequired"])
        self.assertEqual(audit,tenant_route_audit.inspect_repo())

    def test_new_identity_endpoint_requires_route_security_review(self):
        added=self.app+"\n@app.get('/api/identity/accounts/<account_id>/history')\ndef future_history():\n    return {}\n"
        with self.assertRaisesRegex(tenant_route_audit.ApiBoundaryError,
                                    "Identity route surface"):
            tenant_route_audit.inspect_sources(added,self.worker)

    def test_identity_boundary_or_workflow_change_fails_closed(self):
        changed=self.app.replace("sessions.validate(session)", "True")
        with self.assertRaises(tenant_route_audit.ApiBoundaryError):
            tenant_route_audit.inspect_sources(changed,self.worker)
        changed=self.worker.replace("appmod.selected_account()", "appmod.random_account()")
        with self.assertRaises(tenant_route_audit.ApiBoundaryError):
            tenant_route_audit.inspect_sources(self.app,changed)

    def test_unreviewed_gateway_and_live_monitor_worker_import_fail_closed(self):
        # Gated read-only monitor planning is now reviewed for HTTP; the
        # dormant gateway remains prohibited and BOTH must stay out of worker.
        self.assertIn("tenant_monitor_blueprint",self.app)
        with self.assertRaises(tenant_route_audit.ApiBoundaryError):
            tenant_route_audit.inspect_sources(
                self.app + "\nfrom engine import tenant_api_gateway\n",self.worker)
        for name in ("tenant_api_gateway","tenant_monitor_blueprint","tenant_watchlist","tenant_password_change","tenant_session_controls"):
            with self.assertRaises(tenant_route_audit.ApiBoundaryError):
                tenant_route_audit.inspect_sources(
                    self.app,self.worker + "\nfrom engine import "+name+"\n")

    def test_tenant_payload_code_is_not_live_wired(self):
        self.assertNotIn("tenant_history_details",self.app)
        self.assertNotIn("tenant_history_details",self.worker)
        self.assertNotIn("tenant_route_audit",self.app)
        self.assertNotIn("tenant_route_audit",self.worker)
        self.assertIn("'liveTradingAvailable':False",self.app)


if __name__=="__main__":
    unittest.main()
