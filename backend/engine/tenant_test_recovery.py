"""Account-scoped failure and manual recovery rehearsal on RAM-only fixtures.

No scheduler, trade/funds permission, Public API access, or worker restart.
Recovery approval ONLY permits the next synthetic NO_DATA rehearsal cycle.
This module is NOT linked to production Flask or the legacy Observe worker.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import account_scope, shadow_storage

_FAILURES=frozenset((
    "BINDING_MISMATCH","FAKE_PROVIDER_UNAVAILABLE",
    "STALE_ACCOUNT_PLAN","SYNTHETIC_OBSERVATION_FAILED",
))
_MANUAL_PHRASE="REVIEW SYNTHETIC ACCOUNT ONLY"


class OfflineRecoveryDenied(RuntimeError):
    """Fixed errors: no user names, broker credentials or private references."""


@dataclass(frozen=True)
class RecoveryStatus:
    state:str
    revision:int
    automatic_resume:bool=False
    live_worker_enabled:bool=False
    real_public_recheck_passed:bool=False
    can_submit_orders:bool=False


class OfflineRecoveryGate:
    def __init__(self,path):
        self.path=str(path)
        shadow_storage.require_isolated_source(self.path)

    def setup(self):
        """Create only on verified detached /dev/shm test source."""
        shadow_storage.require_isolated_source(self.path)
        with account_scope._db(self.path) as con:
            con.execute("""CREATE TABLE IF NOT EXISTS tenant_test_recovery (
                user_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('PAUSED','CLEARED_SYNTHETIC_ONLY')),
                failure_code TEXT NOT NULL CHECK(failure_code IN (
                    'BINDING_MISMATCH','FAKE_PROVIDER_UNAVAILABLE',
                    'STALE_ACCOUNT_PLAN','SYNTHETIC_OBSERVATION_FAILED')),
                revision INTEGER NOT NULL CHECK(revision>=1),
                PRIMARY KEY(user_id,account_id),
                FOREIGN KEY(account_id,user_id)
                  REFERENCES tenant_accounts(account_id,user_id)
            )""")

    def _check(self,con,user_id,account_id):
        account_scope.AccountScopeStore._check(con,user_id,account_id)

    def status(self,user_id,account_id):
        shadow_storage.require_isolated_source(self.path)
        with account_scope._db(self.path) as con:
            self._check(con,user_id,account_id)
            row=con.execute("""SELECT state,revision FROM tenant_test_recovery
                WHERE user_id=? AND account_id=?""",(user_id,account_id)).fetchone()
            if row is None:
                return RecoveryStatus("NO_FAILURE",0)
            return RecoveryStatus(row["state"],row["revision"])

    def record_failure(self,user_id,account_id,failure_code):
        if failure_code not in _FAILURES:
            raise OfflineRecoveryDenied("Unrecognized test-only failure")
        shadow_storage.require_isolated_source(self.path)
        with account_scope._db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            self._check(con,user_id,account_id)
            con.execute("""INSERT INTO tenant_test_recovery
                (user_id,account_id,state,failure_code,revision)
                VALUES(?,?,'PAUSED',?,1)
                ON CONFLICT(user_id,account_id) DO UPDATE SET
                  state='PAUSED',failure_code=excluded.failure_code,
                  revision=tenant_test_recovery.revision+1""",
                (user_id,account_id,failure_code))
            row=con.execute("""SELECT revision FROM tenant_test_recovery
                WHERE user_id=? AND account_id=?""",(user_id,account_id)).fetchone()
        return RecoveryStatus("PAUSED",row["revision"])

    def review_for_synthetic(self,user_id,account_id,*,revision,phrase):
        if (phrase!=_MANUAL_PHRASE or
            not isinstance(revision,int) or isinstance(revision,bool) or
            revision<1):
            raise OfflineRecoveryDenied("Manual synthetic recovery not authorized")
        shadow_storage.require_isolated_source(self.path)
        with account_scope._db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            self._check(con,user_id,account_id)
            changed=con.execute("""UPDATE tenant_test_recovery
                SET state='CLEARED_SYNTHETIC_ONLY', revision=revision+1
                WHERE user_id=? AND account_id=? AND revision=?
                AND state='PAUSED'""",
                (user_id,account_id,revision)).rowcount
            if changed!=1:
                raise OfflineRecoveryDenied("Stale or missing synthetic recovery review")
        return RecoveryStatus("CLEARED_SYNTHETIC_ONLY",revision+1)

    def ensure_test_replay_allowed(self,user_id,account_id):
        status=self.status(user_id,account_id)
        if status.state=="PAUSED":
            raise OfflineRecoveryDenied("Account paused until manual synthetic review")
        return status

    def resume_real_worker(self,*_args,**_kwargs):
        raise OfflineRecoveryDenied("Production worker activation prohibited")

    def connect_public(self,*_args,**_kwargs):
        raise OfflineRecoveryDenied("Public connection activation prohibited")

    def submit_order(self,*_args,**_kwargs):
        raise OfflineRecoveryDenied("Trading prohibited")
