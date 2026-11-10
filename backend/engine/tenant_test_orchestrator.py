"""Bounded, synchronous synthetic tenant observation orchestration.

No server loop, timer, thread, background job, network adapter, Public API
calls, credential decryption, live broker funds, paper/live orders or trade
signals. Only a /dev/shm synthetic database is permitted, with exact approval.
The live single-owner observation worker does not import this module.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass

from . import shadow_storage
from .tenant_foundation import TenantAccessError
from .tenant_worker_boundary import (
    DormantAdmission, DormantWorkerBoundary, WorkerBoundaryDenied,
)
from .tenant_monitor_blueprint import MonitorPlanningError

APPROVAL="SYNTHETIC OFFLINE TENANT BATCH ONLY"


class OfflineOrchestrationDenied(RuntimeError):
    """No broker/account identifiers or secrets exposed in error text."""


@dataclass(frozen=True)
class OfflineOutcome:
    examined: int
    completed: int
    rejected: int
    deferred: int
    real_provider_calls: int = 0
    external_orders: int = 0
    jobs_enqueued: int = 0
    worker_activated: bool = False
    production_database_changed: bool = False
    synthetic_only: bool = True


class OfflineTenantOrchestrator:
    """A single explicitly-invoked pass of separate synthetic account slots."""

    def __init__(self, boundary: DormantWorkerBoundary):
        if type(boundary) is not DormantWorkerBoundary:
            raise TypeError("Verified offline worker boundary required")
        self.boundary=boundary

    def plan(self, *, account_cap=10, owner_cap=2):
        shadow_storage.require_isolated_source(self.boundary.planner.path)
        return self.boundary.admission(
            maximum_accounts=account_cap,per_owner_limit=owner_cap)

    def replay_once(self, admission: DormantAdmission, *, approval: str):
        if approval!=APPROVAL or type(admission) is not DormantAdmission:
            raise OfflineOrchestrationDenied("Synthetic batch not authorized")
        shadow_storage.require_isolated_source(self.boundary.planner.path)
        if admission.can_activate or admission.external_calls_permitted or admission.account_jobs_scheduled or admission.migration_authorized:
            raise OfflineOrchestrationDenied("An active admission is prohibited")
        if (not isinstance(admission.total_accounts,int) or not isinstance(admission.deferred_accounts,int)
            or admission.total_accounts<0 or admission.deferred_accounts<0
            or admission.total_accounts!=len(admission.slots)+admission.deferred_accounts
            or len(admission.slots)>100):
            raise OfflineOrchestrationDenied("Invalid admission counts")
        seen=set()
        for slot in admission.slots:
            key=(slot.blueprint.user_id,slot.blueprint.account_id)
            if key in seen or slot.scheduled or slot.authorized_to_fetch_quotes or slot.allowed_to_trade:
                raise OfflineOrchestrationDenied("Duplicate or active account slot")
            seen.add(key)
        completed=rejected=0
        # A revoked or stale account is rejected independently. Other accounts
        # still get one synthetic replay. No caught exception enables a retry.
        for slot in admission.slots:
            try:
                report=self.boundary.synthetic_replay(
                    slot,"offline-test-"+secrets.token_hex(12),
                    approval="SYNTHETIC ACCOUNT OBSERVATION ONLY")
                if (not report.get("offlineSyntheticRecordCreated") or
                    report.get("publicQuoteApiCalled") or
                    report.get("paperOrLiveOrderSubmitted") or
                    report.get("workerActivated")):
                    raise OfflineOrchestrationDenied("Synthetic-only guarantee failed")
                completed+=1
            except (TenantAccessError, WorkerBoundaryDenied, MonitorPlanningError):
                rejected+=1
            # Programming errors and SQLite corruption intentionally propagate,
            # rather than silently reporting a successful batch.
        return OfflineOutcome(
            examined=len(admission.slots),completed=completed,
            rejected=rejected,deferred=admission.deferred_accounts)

    def start_scheduler(self,*_args,**_kwargs):
        raise OfflineOrchestrationDenied("Tenant background orchestration disabled")

    def connect_public(self,*_args,**_kwargs):
        raise OfflineOrchestrationDenied("Public API access disabled")

    def submit_order(self,*_args,**_kwargs):
        raise OfflineOrchestrationDenied("Tenant trading disabled")
