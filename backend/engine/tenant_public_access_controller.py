"""Disabled-by-default per-account budgets and emergency shutoff.

The controls apply to an offline mock-HTTPS integration; no real Public
connections are available through this module in v0.2.21. Failures do not
resume automatically and each owner's account has separate state.
"""
from __future__ import annotations

from collections import deque
import threading
import time


class PublicAccessDenied(RuntimeError):
    def __init__(self,code):
        code=code if code in ("EMERGENCY_STOP","ACCOUNT_PAUSED",
                              "REQUEST_BUDGET_EXHAUSTED","INVALID_SCOPE") else "INVALID_SCOPE"
        self.code=code
        super().__init__(code)


class ReadOnlyAccessController:
    """Fixed guardrails, with no user-configurable auto-activation.

    Max 2 operations/account in 60 seconds, 10 overall, with no automatic
    retries. Circuit state stays paused after a 429 or auth failure until
    an explicit offline reset. Kill switch is global and irreversible for
    the current controller instance; no reset method exists.
    """

    def __init__(self,*,clock=None):
        self._clock=clock or time.monotonic
        self._lock=threading.Lock()
        self._stopped=False
        self._global=deque()
        self._per_account={}
        self._paused=set()

    @staticmethod
    def _scope(user_id,account_id):
        if (not isinstance(user_id,str) or not isinstance(account_id,str)
            or not 1<=len(user_id)<=128 or not 1<=len(account_id)<=128):
            raise PublicAccessDenied("INVALID_SCOPE")
        return (user_id,account_id)

    def emergency_stop(self):
        with self._lock:
            self._stopped=True
        return {"emergencyStop":True,"liveConnectionsPermitted":False}

    def paused(self,user_id,account_id):
        key=self._scope(user_id,account_id)
        with self._lock:
            return key in self._paused

    def block_account(self,user_id,account_id):
        key=self._scope(user_id,account_id)
        with self._lock:
            self._paused.add(key)

    def acquire(self,user_id,account_id):
        key=self._scope(user_id,account_id)
        with self._lock:
            if self._stopped:
                raise PublicAccessDenied("EMERGENCY_STOP")
            if key in self._paused:
                raise PublicAccessDenied("ACCOUNT_PAUSED")
            now=self._clock()
            if type(now) not in (float,int):
                raise PublicAccessDenied("INVALID_SCOPE")
            while self._global and now-self._global[0]>=60:
                self._global.popleft()
            events=self._per_account.setdefault(key,deque())
            while events and now-events[0]>=60:
                events.popleft()
            if len(self._global)>=10 or len(events)>=2:
                # No automatic retry, delay, sleep, queued job or bypass.
                raise PublicAccessDenied("REQUEST_BUDGET_EXHAUSTED")
            events.append(now)
            self._global.append(now)
            return {"accountScoped":True,"noAutomaticRetry":True,
                    "liveNetworkEnabled":False,"ordersAllowed":False}

    def unpause_for_offline_test(self,user_id,account_id,*,phrase):
        """Only if the emergency stop was NOT triggered, and never starts a job."""
        if phrase!="REVIEW OFFLINE ACCESS ONLY":
            raise PublicAccessDenied("ACCOUNT_PAUSED")
        key=self._scope(user_id,account_id)
        with self._lock:
            if self._stopped:
                raise PublicAccessDenied("EMERGENCY_STOP")
            self._paused.discard(key)
        return {"offlineOnly":True,"liveNetworkEnabled":False}

    def is_stopped(self):
        with self._lock:
            return self._stopped
