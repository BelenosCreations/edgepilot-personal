"""Test-only, single-pass Public response-preflight + isolated recovery.

Never schedules work, connects to Public, emits quotes, activates an account,
or places orders. All calls are synthetic, on verified memory-backed SQLite.
"""
from __future__ import annotations

from dataclasses import dataclass
from . import shadow_storage
from .tenant_foundation import TenantAccessError
from .tenant_monitor_blueprint import MonitorPlanningError
from .tenant_worker_boundary import DormantAdmission, DormantWorkerBoundary, WorkerBoundaryDenied
from .tenant_test_recovery import OfflineRecoveryGate, OfflineRecoveryDenied
from .tenant_public_readonly_preflight import (
    IsolatedPublicReadOnlyPreflight, PublicPreflightDenied,
)

APPROVAL="REVIEW RECORDED PUBLIC ACCOUNT RESPONSES ONLY"


class OfflinePreflightDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class RecordedPreflightReport:
    attempted:int
    matching_synthetic_accounts:int
    preflight_failures:int
    paused_accounts:int
    unavailable_accounts:int
    deferred_accounts:int
    provider_network_requests:int=0
    real_public_account_access_proved:bool=False
    live_accounts_activated:int=0
    quote_scans:int=0
    trades_submitted:int=0
    production_database_changed:bool=False


class OfflineRecordedPublicBatch:
    def __init__(self,boundary,preflight,recovery):
        if (type(boundary) is not DormantWorkerBoundary or
            type(preflight) is not IsolatedPublicReadOnlyPreflight or
            type(recovery) is not OfflineRecoveryGate):
            raise TypeError("Test-only boundaries required")
        paths=(boundary.planner.path,preflight.path,recovery.path)
        resolved=[shadow_storage.require_isolated_source(p)[0] for p in paths]
        if len(set(resolved))!=1:
            raise OfflinePreflightDenied("Offline fixture mismatch")
        self.boundary=boundary
        self.preflight=preflight
        self.recovery=recovery

    def run_once(self,admission,*,approval):
        if approval!=APPROVAL or type(admission) is not DormantAdmission:
            raise OfflinePreflightDenied("Recorded preflight requires explicit approval")
        shadow_storage.require_isolated_source(self.preflight.path)
        if (admission.can_activate or admission.migration_authorized or
            admission.account_jobs_scheduled or admission.external_calls_permitted or
            admission.total_accounts!=len(admission.slots)+admission.deferred_accounts or
            len(admission.slots)>100):
            raise OfflinePreflightDenied("Active or invalid tenant admission refused")
        seen=set()
        for slot in admission.slots:
            uid,aid=slot.blueprint.user_id,slot.blueprint.account_id
            if ((uid,aid) in seen or slot.scheduled or
                slot.authorized_to_fetch_quotes or slot.allowed_to_trade):
                raise OfflinePreflightDenied("Duplicate or enabled tenant account refused")
            seen.add((uid,aid))
        matched=failures=paused=unavailable=0
        for slot in admission.slots:
            uid,aid=slot.blueprint.user_id,slot.blueprint.account_id
            try:
                self.boundary.revalidate(slot)
                self.recovery.ensure_test_replay_allowed(uid,aid)
                evidence=self.preflight.check(uid,aid)
                if (not evidence.fake_credential_access_matches or
                    not evidence.provider_account_list_matched or
                    evidence.verified_by_real_public or evidence.external_network_requests or
                    evidence.authorized_for_trading or evidence.account_activated):
                    raise OfflinePreflightDenied("Synthetic provider boundary violated")
                matched+=1
            except PublicPreflightDenied as failure:
                # Pause *only* this user/account; no retriable auto-resume.
                reason=("BINDING_MISMATCH" if failure.code=="ACCOUNT_NOT_ACCESSIBLE"
                        else "FAKE_PROVIDER_UNAVAILABLE")
                try:
                    self.recovery.record_failure(uid,aid,reason)
                    failures+=1
                except TenantAccessError:
                    unavailable+=1
            except OfflineRecoveryDenied:
                paused+=1
            except (TenantAccessError,WorkerBoundaryDenied,MonitorPlanningError):
                unavailable+=1
        return RecordedPreflightReport(len(admission.slots),matched,failures,
                                       paused,unavailable,admission.deferred_accounts)

    def verify_live_public(self,*_args,**_kwargs):
        raise OfflinePreflightDenied("Real Public network verification disabled")

    def start_live_workers(self,*_args,**_kwargs):
        raise OfflinePreflightDenied("Live worker activation disabled")

    def transfer_funds(self,*_args,**_kwargs):
        raise OfflinePreflightDenied("Transfer operation disabled")
