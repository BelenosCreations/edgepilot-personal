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
        self.assertEqual(audit["identityRoutesReviewed"],9)
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

    def test_new_dormant_router_or_monitor_cannot_be_wired_silently(self):
        for name in ("tenant_api_gateway","tenant_monitor_blueprint"):
            with self.assertRaises(tenant_route_audit.ApiBoundaryError):
                tenant_route_audit.inspect_sources(
                    self.app + "\nfrom engine import "+name+"\n",self.worker)
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
