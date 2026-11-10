"""Dormant fair scheduling/admission contract for future tenant observers.

No threads, timers, brokerage clients, background tasks, broker credential
decryption, HTTP routes or network access. A returned slot is NOT runnable.
This module is solely a planning and synthetic /dev/shm test primitive.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .tenant_monitor_blueprint import (
    DormantAccountMonitorPlanner, MonitorBlueprint, MonitorPlanningError,
)

class WorkerBoundaryDenied(PermissionError):
    """Sanitized: no owner names or Public account IDs in errors."""


@dataclass(frozen=True)
class DormantWorkerSlot:
    blueprint: MonitorBlueprint
    max_symbols: int = 25
    max_queued_cycles: int = 1
    per_account_concurrency: int = 1
    scheduled: bool = False
    authorized_to_fetch_quotes: bool = False
    allowed_to_trade: bool = False


@dataclass(frozen=True)
class DormantAdmission:
    slots: tuple[DormantWorkerSlot, ...]
    total_accounts: int
    deferred_accounts: int
    account_jobs_scheduled: int = 0
    external_calls_permitted: int = 0
    migration_authorized: bool = False
    can_activate: bool = False


class DormantWorkerBoundary:
    """Fair account choice across owners without any runnable credentials.

    Plan identity is provided by internal account inventory only; worker
    caller cannot supply a new owner/account pair to impersonate.
    Disallow active runtime even if a persisted config is altered.
    """

    def __init__(self,planner: DormantAccountMonitorPlanner):
        if not isinstance(planner,DormantAccountMonitorPlanner):
            raise TypeError("Verified tenant monitoring planner required")
        self.planner=planner

    def admission(self,*,maximum_accounts=10,per_owner_limit=2) -> DormantAdmission:
        if (not isinstance(maximum_accounts,int) or isinstance(maximum_accounts,bool)
            or not 1<=maximum_accounts<=100
            or not isinstance(per_owner_limit,int) or isinstance(per_owner_limit,bool)
            or not 1<=per_owner_limit<=10):
            raise WorkerBoundaryDenied("Invalid worker planning constraints")
        all_plans=self.planner.enumerate_disabled()
        by_owner={}
        for plan in all_plans:
            self._check_plan(plan)
            by_owner.setdefault(plan.user_id,[]).append(plan)
        # Deterministic round-robin. One owner cannot consume all of the
        # bounded slots ahead of other owners.
        users=sorted(by_owner)
        slots=[]
        for index in range(per_owner_limit):
            for user in users:
                choices=by_owner[user]
                if index>=len(choices) or len(slots)>=maximum_accounts:
                    continue
                slots.append(DormantWorkerSlot(choices[index]))
        return DormantAdmission(
            tuple(slots),len(all_plans),len(all_plans)-len(slots))

    @staticmethod
    def _check_plan(plan: MonitorBlueprint) -> None:
        if (not isinstance(plan,MonitorBlueprint) or plan.mode!="observe"
            or len(plan.symbols)>25 or any((
                plan.scheduled,plan.runtime_enabled,plan.broker_requests_allowed,
                plan.paper_trading_allowed,plan.live_trading_allowed
            ))):
            raise WorkerBoundaryDenied("An active tenant worker plan is prohibited")

    def revalidate(self,slot: DormantWorkerSlot) -> bool:
        if not isinstance(slot,DormantWorkerSlot):
            raise WorkerBoundaryDenied("Invalid worker slot")
        self._check_plan(slot.blueprint)
        latest=self.planner.plan_for(
            slot.blueprint.user_id,slot.blueprint.account_id)
        if latest!=slot.blueprint:
            raise WorkerBoundaryDenied("Account plan changed before use")
        return True

    def synthetic_replay(self,slot: DormantWorkerSlot,worker_id: str,*,
                         approval: str) -> dict:
        """Optional single-account offline replay only; no real scan.

        This is an isolated test helper, not a scheduled process. Existing
        planner enforces real /dev/shm storage, exact approval and scoped
        lease; account revocation prevents replay.
        """
        self.revalidate(slot)
        result=self.planner.offline_replay(
            slot.blueprint,worker_id,approval=approval)
        return {**result,"scheduleActivated":False,
                "publicQuoteApiCalled":False,
                "runWasSynthetic":True}

    def start(self,*_args,**_kwargs):
        raise WorkerBoundaryDenied("Tenant workers are disabled")

    def enqueue(self,*_args,**_kwargs):
        raise WorkerBoundaryDenied("Tenant workers are disabled")

    def submit_order(self,*_args,**_kwargs):
        raise WorkerBoundaryDenied("Tenant trading is disabled")
