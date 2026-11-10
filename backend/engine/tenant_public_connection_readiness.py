"""Explicit pre-connection readiness audit; always denies live Public.

The only positive state is permission to continue *synthetic* tests on a
verified detached tmpfs account. No real provider access, account ownership
verification, credential onboarding, HTTP API routes or production workers.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import account_scope,shadow_storage
from .identity_auth import IdentityStore
from .tenant_public_offline_consent import OfflineConsentCeremony
from .tenant_public_safety_state import OfflinePersistentSafety
from .tenant_public_https_wire import NETWORK_ENABLED
from .tenant_legacy_dependency_audit import inspect_repo


@dataclass(frozen=True)
class PublicConnectionReadiness:
    offline_consent_valid:bool
    account_currently_eligible:bool
    synthetic_safety_ready:bool
    active_distinct_owners:int
    external_terms_review_required:bool=True
    real_access_verified:bool=False
    legal_owner_verified:bool=False
    actual_public_network_authorized:bool=False
    persistent_production_kill_switch_available:bool=False
    production_api_account_isolated:bool=False
    production_worker_account_isolated:bool=False
    real_public_connection_ready:bool=False
    trading_or_funds_enabled:bool=False


class OfflineConnectionReadiness:
    def __init__(self,path,identity_store,consent,safety):
        self.path=str(path)
        shadow_storage.require_isolated_source(self.path)
        if (type(identity_store) is not IdentityStore or
            type(consent) is not OfflineConsentCeremony or
            type(safety) is not OfflinePersistentSafety or
            any(x.path!=self.path for x in (identity_store,consent,safety))):
            raise TypeError("Isolated verified test-only state required")
        self.identity_store=identity_store
        self.consent=consent
        self.safety=safety

    def assess(self,token,account_id,consent_id):
        shadow_storage.require_isolated_source(self.path)
        if NETWORK_ENABLED:
            # Any future network enablement requires separate code review.
            raise RuntimeError("Live network gate must remain disabled")
        principal=self.identity_store.principal(token)
        if principal is None:
            raise PermissionError("Identity unavailable")
        user_id=principal["user_id"]
        self.consent.assert_confirmed(token,account_id,consent_id)
        self.safety.require_ready(user_id,account_id)
        with account_scope._db(self.path) as con:
            account_scope.AccountScopeStore._check(con,user_id,account_id)
            active_owners=con.execute("""SELECT COUNT(DISTINCT a.user_id)
                FROM tenant_accounts a
                JOIN tenant_users u ON u.user_id=a.user_id
                JOIN tenant_connections c ON c.connection_id=a.connection_id
                 AND c.user_id=a.user_id
                WHERE a.disabled_at IS NULL AND u.disabled_at IS NULL
                 AND c.revoked_at IS NULL""").fetchone()[0]
        legacy=inspect_repo()
        if legacy["cutoverReady"] or legacy["legacyHttpRoutesRefactored"] or legacy["legacyWorkerRefactored"]:
            raise RuntimeError("Legacy isolation audit changed; security review required")
        return PublicConnectionReadiness(
            offline_consent_valid=True,
            account_currently_eligible=True,
            synthetic_safety_ready=True,
            active_distinct_owners=active_owners,
        )

    def enable_public(self,*_args,**_kwargs):
        raise PermissionError("Real Public connections require separate approval")
