"""Static, read-only inventory of legacy global-account dependencies.

Counts direct selected_account() calls inside the current Flask module and
appmod.selected_account() in the legacy observation worker. No production
refactoring, routing switch, or worker activation. Reports blockers.
"""
from __future__ import annotations

import ast
from pathlib import Path


class LegacyDependencyAuditError(RuntimeError):
    pass


def inspect_sources(app_source,worker_source):
    try:
        app=ast.parse(app_source)
        worker=ast.parse(worker_source)
    except (SyntaxError,TypeError):
        raise LegacyDependencyAuditError("Legacy account source could not be inspected") from None
    direct=[]
    for node in ast.walk(app):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=="selected_account":
            direct.append(node.lineno)
    worker_calls=[]
    for node in ast.walk(worker):
        if (isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and
            node.func.attr=="selected_account" and
            isinstance(node.func.value,ast.Name) and
            node.func.value.id=="appmod"):
            worker_calls.append(node.lineno)
    if not direct or not worker_calls:
        raise LegacyDependencyAuditError("Legacy global dependency inventory changed; security review required")
    return {
        "legacyFlaskDirectSelectedAccountCalls":len(direct),
        "legacyWorkerGlobalSelectedAccountCalls":len(worker_calls),
        "legacyHttpRoutesRefactored":False,
        "legacyWorkerRefactored":False,
        "offlineAdapterUsesExplicitUserAndAccount":True,
        "realPublicOwnershipVerified":False,
        "cutoverReady":False,
        "auditIsStaticNotProofOfIsolation":True,
    }


def inspect_repo():
    root=Path(__file__).resolve().parents[1]
    return inspect_sources(
        (root/"app.py").read_text(encoding="utf-8"),
        (root/"engine"/"automation_worker.py").read_text(encoding="utf-8"))
