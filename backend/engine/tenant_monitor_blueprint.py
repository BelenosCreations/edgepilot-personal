"""Dormant, per-account observation planner and isolated synthetic replay.

There is no scheduling loop, network client, Public credential decryption,
HTTP endpoint, real quote fetch, paper trade or live order execution.

Existing global Observe worker remains the only configured production worker.
This module operates only on explicit user/account pairs from a future trusted
backend scheduler. An offline replay requires a verified /dev/shm DB.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import account_scope, shadow_storage
from .tenant_foundation import TenantAccessError

_SYMBOL=re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")
_MAX_WATCHLIST=25


class MonitorPlanningError(RuntimeError):
    """Sanitized monitoring plan error."""


def _symbols_from_watchlist(value):
    if value is None or value == "":
        return ()
    if not isinstance(value,str) or len(value)>512:
        raise MonitorPlanningError("Invalid account watchlist")
    raw=value.split(",")
    if len(raw)>_MAX_WATCHLIST:
        raise MonitorPlanningError("Account watchlist exceeds supported limits")
    symbols=[]
    for item in raw:
        symbol=item.strip()
        if not _SYMBOL.fullmatch(symbol):
            raise MonitorPlanningError("Invalid account watchlist")
        if symbol not in symbols:
            symbols.append(symbol)
    return tuple(symbols)


@dataclass(frozen=True)
class MonitorBlueprint:
    user_id:str
    account_id:str
    symbols:tuple[str,...]
    mode:str="observe"
    scheduled:bool=False
    runtime_enabled:bool=False
    broker_requests_allowed:bool=False
    paper_trading_allowed:bool=False
    live_trading_allowed:bool=False


class DormantAccountMonitorPlanner:
    """No global selected_account fallback and no broker/worker activation.

    Trusted backend caller supplies an owner/account pair, never an HTTP
    client. A plan is refused if user or connection is revoked or disabled.
    All plans are intentionally disabled; future job scheduler needs
    separate review and explicit activation approval.
    """

    def __init__(self, path):
        self.path=str(path)

    def plan_for(self,user_id,account_id):
        if not all(isinstance(x,str) and 1<=len(x)<=128 for x in
                   (user_id,account_id)):
            raise TenantAccessError("Account unavailable")
        with account_scope._db(self.path) as con:
            account_scope.AccountScopeStore._check(con,user_id,account_id)
            row=con.execute("""SELECT setting_value FROM tenant_account_settings
                WHERE user_id=? AND account_id=? AND setting_key='watchlist_csv'""",
                (user_id,account_id)).fetchone()
            mode=con.execute("""SELECT requested_mode,worker_enabled,
                paper_enabled,live_enabled FROM tenant_runtime_status
                WHERE user_id=? AND account_id=?""",(user_id,account_id)).fetchone()
        # Do not trust persisted flags beyond the known disabled schema.
        if mode and (mode["requested_mode"]!="observe" or mode["worker_enabled"] or
                     mode["paper_enabled"] or mode["live_enabled"]):
            raise MonitorPlanningError("Unexpected active tenant runtime")
        symbols=_symbols_from_watchlist(row["setting_value"] if row else None)
        return MonitorBlueprint(user_id,account_id,symbols)

    def enumerate_disabled(self):
        """Internal-only inventory; never a candidate for a live job queue."""
        with account_scope._db(self.path) as con:
            pairs=con.execute("""SELECT a.user_id,a.account_id FROM tenant_accounts a
                JOIN tenant_users u ON u.user_id=a.user_id
                JOIN tenant_connections c ON c.connection_id=a.connection_id
                  AND c.user_id=a.user_id
                WHERE a.disabled_at IS NULL AND u.disabled_at IS NULL
                  AND c.revoked_at IS NULL
                ORDER BY a.user_id,a.account_id""").fetchall()
        return [self.plan_for(row["user_id"],row["account_id"]) for row in pairs]

    def offline_replay(self,plan,worker_id,*,approval):
        """Write one synthetic NO_DATA observation to RAM-only test DB.

        This is NOT a quote scan or evidence of worker liveness. A plan with
        any active capability is explicitly prohibited. Neither the production
        database nor any actual Public quote API is opened.
        """
        if approval!="SYNTHETIC ACCOUNT OBSERVATION ONLY":
            raise MonitorPlanningError("Offline replay not authorized")
        if not isinstance(plan,MonitorBlueprint) or any((
            plan.scheduled,plan.runtime_enabled,plan.broker_requests_allowed,
            plan.paper_trading_allowed,plan.live_trading_allowed
        )) or plan.mode!="observe":
            raise MonitorPlanningError("Inactive observation plan required")
        shadow_storage.require_isolated_source(self.path)
        fresh=self.plan_for(plan.user_id,plan.account_id)
        if fresh != plan:
            raise MonitorPlanningError("Account plan changed before replay")
        store=account_scope.DormantAccountWorkerStore(self.path)
        if not store.claim_lease(plan.user_id,plan.account_id,worker_id,ttl=120):
            raise MonitorPlanningError("Account lease busy")
        try:
            store.record_observation(plan.user_id,plan.account_id,worker_id,
                mode="observe",state="NO_DATA",
                symbols=plan.symbols,market_session="NOT_APPLICABLE",
                accepted=0,rejected=0,issue="SYNTHETIC OFFLINE REPLAY ONLY")
        finally:
            store.release_lease(plan.user_id,plan.account_id,worker_id)
        return {"offlineSyntheticRecordCreated":True,
                "userAccountScoped":True,"realQuotesFetched":False,
                "workerActivated":False,"paperOrLiveOrderSubmitted":False,
                "productionDatabaseChanged":False}

    def start_live_monitoring(self,*_args,**_kwargs):
        raise MonitorPlanningError("Tenant monitoring is not enabled")

    def execute_order(self,*_args,**_kwargs):
        raise MonitorPlanningError("Tenant trading is not enabled")
