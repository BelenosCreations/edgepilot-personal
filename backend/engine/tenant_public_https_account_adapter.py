"""Inactive account-bound read-only Public HTTPS adapter integration.

Even though the HTTP wire implementation can be tested end-to-end with
fake connections, network is HARD-DISABLED in v0.2.21. Only encrypted
synthetic credentials inside /dev/shm are accepted. No live Public
connection, real account verification, order, bank transfer or enrollment.
"""
from __future__ import annotations

from dataclasses import dataclass
from cryptography.fernet import Fernet, InvalidToken
from . import account_scope, shadow_storage
from .tenant_foundation import TenantAccessError
from .tenant_public_access_controller import ReadOnlyAccessController, PublicAccessDenied
from .tenant_public_https_wire import (
    StrictPublicHTTPS,PublicWireDenied,prepare_token_request,
    prepare_accounts_request,
)
from .tenant_public_readonly_preflight import _validated_account_ids,PublicPreflightDenied


class OfflineHTTPSDenied(RuntimeError):
    """Constant error: never includes provider data or user secrets."""
    _CODES=frozenset((
        "NETWORK_DISABLED","INVALID_FIXTURE","ACCOUNT_UNAVAILABLE",
        "AUTH_REJECTED","RATE_LIMITED","PROVIDER_UNAVAILABLE","BAD_RESPONSE",
    ))
    def __init__(self,code):
        self.code=code if code in self._CODES else "BAD_RESPONSE"
        super().__init__(self.code)


@dataclass(frozen=True)
class OfflineHTTPEvidence:
    synthetic_credential_access_matched:bool=True
    account_scope_verified:bool=True
    real_public_network_calls:int=0
    provider_ownership_verified:bool=False
    real_credential_used:bool=False
    trading_enabled:bool=False
    funds_enabled:bool=False
    worker_started:bool=False


class OfflinePublicHTTPSAccountVerifier:
    """The only v0.2.21 integration uses socket-free fake connections.

    A future change must approve real networking independently. The real
    HTTPS transport method intentionally cannot transmit.
    """

    def __init__(self,path,credential_key,wire,controller,fake_connection_factory):
        if type(wire) is not StrictPublicHTTPS or type(controller) is not ReadOnlyAccessController:
            raise TypeError("Only reviewed offline HTTPS components are allowed")
        if not callable(fake_connection_factory):
            raise TypeError("Synthetic connection factory required")
        self.path=str(path)
        shadow_storage.require_isolated_source(self.path)
        try:
            self._cipher=Fernet(credential_key)
        except (ValueError,TypeError):
            raise OfflineHTTPSDenied("INVALID_FIXTURE") from None
        self.wire=wire
        self.controller=controller
        self._fake_connection_factory=fake_connection_factory

    def _require_account(self,user_id,account_id):
        shadow_storage.require_isolated_source(self.path)
        if (not isinstance(user_id,str) or not isinstance(account_id,str)
            or not 1<=len(user_id)<=128 or not 1<=len(account_id)<=128):
            raise TenantAccessError("Account unavailable")
        with account_scope._db(self.path) as con:
            account_scope.AccountScopeStore._check(con,user_id,account_id)
            row=con.execute("""SELECT a.provider_account_ref,
                    c.credential_ciphertext
                FROM tenant_accounts a
                JOIN tenant_connections c
                  ON c.connection_id=a.connection_id AND c.user_id=a.user_id
                WHERE a.account_id=? AND a.user_id=? AND a.provider='public'
                  AND a.disabled_at IS NULL AND c.revoked_at IS NULL""",
                (account_id,user_id)).fetchone()
            if row is None:
                raise TenantAccessError("Account unavailable")
            return row["provider_account_ref"],row["credential_ciphertext"]

    @staticmethod
    def _map_failure(error):
        if isinstance(error,PublicWireDenied):
            return {
                "AUTH_REJECTED":"AUTH_REJECTED",
                "RATE_LIMITED":"RATE_LIMITED",
                "PROVIDER_UNAVAILABLE":"PROVIDER_UNAVAILABLE",
                "NETWORK_DISABLED":"NETWORK_DISABLED",
            }.get(error.code,"BAD_RESPONSE")
        return "BAD_RESPONSE"

    def check_synthetic(self,user_id,account_id):
        if self.controller.is_stopped():
            raise PublicAccessDenied("EMERGENCY_STOP")
        reference,ciphertext=self._require_account(user_id,account_id)
        if self.controller.paused(user_id,account_id):
            raise PublicAccessDenied("ACCOUNT_PAUSED")
        try:
            secret=self._cipher.decrypt(ciphertext).decode("utf-8")
        except (InvalidToken,UnicodeDecodeError,ValueError,TypeError):
            self.controller.block_account(user_id,account_id)
            raise OfflineHTTPSDenied("INVALID_FIXTURE") from None
        if not secret.startswith("SYNTHETIC-") or not 20<=len(secret)<=256:
            self.controller.block_account(user_id,account_id)
            raise OfflineHTTPSDenied("INVALID_FIXTURE")
        try:
            self.controller.acquire(user_id,account_id)
            auth_request=prepare_token_request(secret)
            auth=self.wire.send_synthetic_on_fake(
                auth_request,self._fake_connection_factory("POST"))
            token=auth.body.get("accessToken")
            if (not isinstance(token,str) or
                not token.startswith("SYNTHETIC-TOKEN-") or len(token)>256):
                raise OfflineHTTPSDenied("BAD_RESPONSE")
            # Verify owner and connection have not changed since the POST.
            new_ref,_=self._require_account(user_id,account_id)
            if new_ref!=reference:
                raise TenantAccessError("Account unavailable")
            self.controller.acquire(user_id,account_id)
            accounts=self.wire.send_synthetic_on_fake(
                prepare_accounts_request(token),
                self._fake_connection_factory("GET"))
            try:
                account_ids=_validated_account_ids(accounts.body)
            except PublicPreflightDenied:
                raise OfflineHTTPSDenied("BAD_RESPONSE") from None
            if reference not in account_ids:
                raise OfflineHTTPSDenied("ACCOUNT_UNAVAILABLE")
            final_ref,_=self._require_account(user_id,account_id)
            if final_ref!=reference or self.controller.is_stopped():
                raise PublicAccessDenied("EMERGENCY_STOP")
            return OfflineHTTPEvidence()
        except (PublicWireDenied,OfflineHTTPSDenied) as error:
            self.controller.block_account(user_id,account_id)
            code=self._map_failure(error) if isinstance(error,PublicWireDenied) else error.code
            raise OfflineHTTPSDenied(code) from None
        # Revocation, request budgets and emergency stops already fail closed;
        # no automatic retry or resume occurs.

    def check_real(self,*_args,**_kwargs):
        raise OfflineHTTPSDenied("NETWORK_DISABLED")

    def submit_order(self,*_args,**_kwargs):
        raise OfflineHTTPSDenied("NETWORK_DISABLED")

    def transfer_funds(self,*_args,**_kwargs):
        raise OfflineHTTPSDenied("NETWORK_DISABLED")
