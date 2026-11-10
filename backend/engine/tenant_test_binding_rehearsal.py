"""Detached synthetic provider/account rehearsal with isolated recovery.

This is a controlled FAKE adapter integration test, not real Public ownership
verification or live account synchronization. Never imported into Flask or
automation_worker.py. No background schedule or broker execution surface.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import shadow_storage
from .tenant_foundation import TenantAccessError
from .tenant_worker_boundary import DormantAdmission, DormantWorkerBoundary, WorkerBoundaryDenied
from .tenant_monitor_blueprint import MonitorPlanningError
from .tenant_test_public_binding import ControlledFixtureBinding, FixtureBindingRejected
from .tenant_test_recovery import OfflineRecoveryGate, OfflineRecoveryDenied

APPROVAL="OFFLINE ACCOUNT BINDING REHEARSAL ONLY"


class FixtureRehearsalDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class FixtureRehearsalReport:
    attempted:int
    synthetic_cycles:int
    failed_bindings:int
    paused_accounts:int
    unavailable_accounts:int
    deferred_accounts:int
    real_public_ownership_verified:bool=False
    provider_calls:int=0
    trades_submitted:int=0
    production_database_changed:bool=False
    any_runtime_activated:bool=False


class IsolatedPublicAccountRehearsal:
    """One synchronous fixture pass; does not mutate live broker state."""

    def __init__(self,boundary,binding,recovery):
        if (type(boundary) is not DormantWorkerBoundary or
            type(binding) is not ControlledFixtureBinding or
            type(recovery) is not OfflineRecoveryGate):
            raise FixtureRehearsalDenied("Only isolated test components supported")
        paths=(boundary.planner.path,binding.path,recovery.path)
        resolved=[shadow_storage.require_isolated_source(p)[0] for p in paths]
        if len(set(resolved))!=1:
            raise FixtureRehearsalDenied("Test components have different databases")
        self.boundary,self.binding,self.recovery=boundary,binding,recovery

    def run_once(self,admission,*,approval):
        if approval!=APPROVAL or type(admission) is not DormantAdmission:
            raise FixtureRehearsalDenied("Offline-only approval required")
        shadow_storage.require_isolated_source(self.binding.path)
        if (admission.can_activate or admission.account_jobs_scheduled or
            admission.external_calls_permitted or admission.migration_authorized or
            admission.total_accounts!=len(admission.slots)+admission.deferred_accounts or
            len(admission.slots)>100):
            raise FixtureRehearsalDenied("Active or invalid admission not supported")
        seen=set()
        for slot in admission.slots:
            uid,aid=slot.blueprint.user_id,slot.blueprint.account_id
            if (uid,aid) in seen or slot.scheduled or slot.authorized_to_fetch_quotes or slot.allowed_to_trade:
                raise FixtureRehearsalDenied("Duplicate or active account slot")
            seen.add((uid,aid))
        completed=failures=paused=unavailable=0
        for slot in admission.slots:
            uid,aid=slot.blueprint.user_id,slot.blueprint.account_id
            try:
                self.boundary.revalidate(slot)
                self.recovery.ensure_test_replay_allowed(uid,aid)
                evidence=self.binding.verify_for(uid,aid)
                if (not evidence.fixture_account_matches or
                    evidence.real_public_ownership_verified or
                    evidence.provider_network_requests):
                    raise FixtureRehearsalDenied("Unexpected fake adapter capability")
                result=self.boundary.synthetic_replay(
                    slot,"fake-binding-rehearsal-"+aid[:8],
                    approval="SYNTHETIC ACCOUNT OBSERVATION ONLY")
                if (not result.get("offlineSyntheticRecordCreated") or
                    result.get("publicQuoteApiCalled") or
                    result.get("workerActivated") or
                    result.get("paperOrLiveOrderSubmitted")):
                    raise FixtureRehearsalDenied("Offline observation safety violated")
                completed+=1
            except FixtureBindingRejected:
                # The failed binding does NOT become a Public ownership claim.
                # This is the only failure that triggers a review latch.
                try:
                    self.recovery.record_failure(uid,aid,"BINDING_MISMATCH")
                    failures+=1
                except TenantAccessError:
                    unavailable+=1
            except OfflineRecoveryDenied:
                paused+=1
            except (TenantAccessError,WorkerBoundaryDenied,MonitorPlanningError):
                unavailable+=1
        return FixtureRehearsalReport(
            attempted=len(admission.slots),synthetic_cycles=completed,
            failed_bindings=failures,paused_accounts=paused,
            unavailable_accounts=unavailable,
            deferred_accounts=admission.deferred_accounts)

    def verify_real_ownership(self,*_args,**_kwargs):
        raise FixtureRehearsalDenied("Real provider ownership verification unavailable")

    def enable_live(self,*_args,**_kwargs):
        raise FixtureRehearsalDenied("Tenant live execution is disabled")
