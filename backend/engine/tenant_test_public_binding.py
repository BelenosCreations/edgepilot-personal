"""Controlled, FAKE Public account-binding contract for isolated tests only.

No real Public API traffic, credentials, cryptographic provider attestation,
user enrollment, account creation or trading. A matching fake response proves
only that a test fixture's connection/account mapping is internally consistent,
NOT that an actual person owns a Public brokerage account.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import account_scope, shadow_storage
from .tenant_foundation import TenantAccessError


class FixtureBindingRejected(RuntimeError):
    """Sanitized: never prints account references or credentials."""


@dataclass(frozen=True)
class SyntheticBinding:
    fixture_connection_matches: bool
    fixture_account_matches: bool
    real_public_ownership_verified: bool = False
    broker_credential_used: bool = False
    live_account_activated: bool = False
    provider_network_requests: int = 0
    orders_submitted: int = 0


class FakePublicAccountSource:
    """A controlled in-memory fake. Cannot reach Public or use a credential."""

    def __init__(self, accounts_by_connection):
        if not isinstance(accounts_by_connection,dict):
            raise FixtureBindingRejected("Invalid fake provider fixture")
        cleaned={}
        for connection,refs in accounts_by_connection.items():
            if (not isinstance(connection,str) or not connection or
                not isinstance(refs,(tuple,list)) or len(refs)>25 or
                any(not isinstance(ref,str) or not 1<=len(ref)<=128 for ref in refs)
                or len(set(refs))!=len(refs)):
                raise FixtureBindingRejected("Invalid fake provider fixture")
            cleaned[connection]=frozenset(refs)
        self._accounts=cleaned
        self.network_requests=0

    def fixture_accounts_for(self,connection_id):
        # A deliberate absence of a record fails closed, not a wildcard.
        return self._accounts.get(connection_id,frozenset())


class ControlledFixtureBinding:
    """Explicit user/account/connection validation, no selected_account()."""

    def __init__(self,path,source):
        if type(source) is not FakePublicAccountSource:
            raise FixtureBindingRejected("Only controlled fake source allowed")
        self.path=str(path)
        shadow_storage.require_isolated_source(self.path)
        self.source=source

    def verify_for(self,user_id,account_id):
        shadow_storage.require_isolated_source(self.path)
        if not all(isinstance(x,str) and 1<=len(x)<=128 for x in (user_id,account_id)):
            raise FixtureBindingRejected("Account unavailable")
        with account_scope._db(self.path) as con:
            account_scope.AccountScopeStore._check(con,user_id,account_id)
            row=con.execute("""SELECT a.provider_account_ref,a.connection_id
                FROM tenant_accounts a
                JOIN tenant_connections c
                  ON c.connection_id=a.connection_id AND c.user_id=a.user_id
                WHERE a.user_id=? AND a.account_id=? AND a.provider='public'
                  AND a.disabled_at IS NULL AND c.revoked_at IS NULL""",
                (user_id,account_id)).fetchone()
        if row is None:
            raise FixtureBindingRejected("Account unavailable")
        refs=self.source.fixture_accounts_for(row["connection_id"])
        if row["provider_account_ref"] not in refs:
            raise FixtureBindingRejected("Fake account binding mismatch")
        return SyntheticBinding(
            fixture_connection_matches=True,fixture_account_matches=True)

    def verify_real_ownership(self,*_args,**_kwargs):
        raise FixtureBindingRejected("Real Public ownership verification unavailable")

    def fetch_real_quotes(self,*_args,**_kwargs):
        raise FixtureBindingRejected("Public quote access disabled")

    def submit_order(self,*_args,**_kwargs):
        raise FixtureBindingRejected("Order submission disabled")
