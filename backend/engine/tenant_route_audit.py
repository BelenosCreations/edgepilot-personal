"""Static, read-only API/worker isolation inventory for migration readiness.

This is a *gate report*, not a security proof and not a new HTTP endpoint.
It explicitly marks the current global single-owner routes and worker as
BLOCKERS to production multi-account activation.
"""
from __future__ import annotations
import ast
from pathlib import Path

IDENTITY_ROUTES=frozenset((
    ("POST","/api/identity/login"),
    ("POST","/api/identity/logout"),
    ("GET","/api/identity/session"),
    ("GET","/api/identity/accounts"),
    ("GET","/api/identity/accounts/<account_id>/summary"),
))
HTTP={"get":"GET","post":"POST","put":"PUT","delete":"DELETE",
      "patch":"PATCH"}

class ApiBoundaryError(RuntimeError):
    """Error never prints source code, credentials, user data or secrets."""


def inspect_sources(app_source,worker_source):
    try:
        tree=ast.parse(app_source)
    except SyntaxError:
        raise ApiBoundaryError("Backend API source cannot be audited") from None
    routes=set()
    for node in ast.walk(tree):
        if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            continue
        for d in node.decorator_list:
            if not (isinstance(d,ast.Call) and
                    isinstance(d.func,ast.Attribute) and
                    isinstance(d.func.value,ast.Name) and
                    d.func.value.id=="app"):
                continue
            method=HTTP.get(d.func.attr)
            if method is None:
                raise ApiBoundaryError("Unreviewed route decorator")
            if len(d.args)!=1 or not isinstance(d.args[0],ast.Constant) or not isinstance(
                d.args[0].value,str):
                raise ApiBoundaryError("Dynamic route declaration requires review")
            path=d.args[0].value
            if path.startswith("/api/"):
                pair=(method,path)
                if pair in routes:
                    raise ApiBoundaryError("Duplicate API route declaration")
                routes.add(pair)
    identity={r for r in routes if r[1].startswith("/api/identity/")}
    if identity!=IDENTITY_ROUTES:
        raise ApiBoundaryError("Identity route surface requires security review")
    required_guard=(
        "if request.path.startswith('/api/identity/'):",
        "sessions.validate(session)",
        "identity_store.principal(token)",
        "request.headers.get('X-Edge-Identity-CSRF'",
        "return fail('Not authenticated',401)",
    )
    if not all(value in app_source for value in required_guard):
        raise ApiBoundaryError("Legacy/identity authorization boundary has changed")
    if any(name in app_source for name in (
        "from engine import tenant_history_details",
        "from engine import tenant_history,",
        "tenant_api_gateway", "tenant_monitor_blueprint",
        "tenant_request_boundary", "tenant_worker_boundary",
        "tenant_test_http", "tenant_test_orchestrator",
        "tenant_test_public_binding", "tenant_test_recovery",
        "tenant_test_binding_rehearsal", "tenant_legacy_dependency_audit",
    )):
        raise ApiBoundaryError("Dormant historical store exposed in legacy HTTP app")
    if ("appmod.selected_account()" not in worker_source or
            "EDGE_AUTOMATION_WORKER_ENABLED" not in worker_source or
            "tenant_history_details" in worker_source or
            "tenant_api_gateway" in worker_source or
            "tenant_monitor_blueprint" in worker_source or
            "tenant_request_boundary" in worker_source or
            "tenant_worker_boundary" in worker_source or
            "tenant_test_http" in worker_source or
            "tenant_test_orchestrator" in worker_source or
            "tenant_test_public_binding" in worker_source or
            "tenant_test_recovery" in worker_source or
            "tenant_test_binding_rehearsal" in worker_source or
            "tenant_legacy_dependency_audit" in worker_source):
        raise ApiBoundaryError("Legacy worker authorization surface changed")
    legacy={r for r in routes if r not in identity}
    if not legacy:
        raise ApiBoundaryError("Legacy API inventory unexpectedly empty")
    return {
        "apiRoutesInventoried":len(routes),
        "identityRoutesReviewed":len(identity),
        "legacySingleOwnerRoutes":len(legacy),
        "legacyRoutesConvertedToTenantScope":0,
        "legacyWorkerUsesGlobalSelectedAccount":True,
        "tenantHistoryDetailsExposedByApi":False,
        "dormantAccountSwitcherExposedByApi":False,
        "tenantMonitorPlannerWiredToWorker":False,
        "tenantRequestBoundaryWiredToHttp":False,
        "tenantWorkerBoundaryWiredToLiveWorker":False,
        "tenantTestHttpMountedOnProduction":False,
        "tenantBatchOrchestratorActivated":False,
        "syntheticPublicBindingConnectedToProduction":False,
        "tenantRecoveryGateWiredToLiveWorker":False,
        "realProviderOwnershipProved":False,
        "httpIntegrationOnlyInIsolatedFixture":True,
        "legacyApiStillGlobalSingleOwner":True,
        "sessionScopedSelectionCannotReplaceLegacyAccountYet":True,
        "historyImportEndpointEnabled":False,
        "crossAccountProductionCutoverAllowed":False,
        "fullRouteAndWorkerRefactorRequired":True,
        "auditIsStaticNotProofOfRuntimeIsolation":True,
    }


def inspect_repo():
    root=Path(__file__).resolve().parents[1]
    try:
        return inspect_sources(
            (root/"app.py").read_text(encoding="utf-8"),
            (root/"engine"/"automation_worker.py").read_text(encoding="utf-8"))
    except (OSError,UnicodeError):
        raise ApiBoundaryError("API boundary files unavailable") from None
