"""Test-only Public access-token/account-list contract using recorded responses.

Follows documented Public endpoints:
  POST /userapiauthservice/personal/access-tokens (secret -> accessToken)
  GET  /userapigateway/trading/account (Bearer accessToken -> accounts[])
No network transport, requests library, HTTP sessions, real Public secrets,
trading capability, account enrollment, or production database usage.
Passing a replay shows simulated *credential-access matching*, NOT verified
legal ownership, proof from Public, or authorization to activate an account.
"""
from __future__ import annotations

from dataclasses import dataclass
from cryptography.fernet import Fernet, InvalidToken
from . import account_scope, shadow_storage
from .tenant_foundation import TenantAccessError

AUTH_PATH="/userapiauthservice/personal/access-tokens"
ACCOUNTS_PATH="/userapigateway/trading/account"
SYNTHETIC_SECRET_PREFIX="SYNTHETIC-"
MAX_ACCOUNTS=25


class PublicPreflightDenied(RuntimeError):
    """Failure codes never contain raw account IDs or credentials."""
    def __init__(self,code):
        if code not in frozenset((
            "CREDENTIAL_NOT_SYNTHETIC","AUTH_REJECTED","PROVIDER_RATE_LIMIT",
            "PROVIDER_UNAVAILABLE","BAD_PROVIDER_RESPONSE","ACCOUNT_NOT_ACCESSIBLE",
            "ISOLATED_FIXTURE_REQUIRED",
        )):
            code="BAD_PROVIDER_RESPONSE"
        self.code=code
        super().__init__(code)


@dataclass(frozen=True)
class RecordedResponse:
    status:int
    payload:object


@dataclass(frozen=True)
class ReadOnlyEvidence:
    fake_credential_access_matches:bool=True
    provider_account_list_matched:bool=True
    verified_by_real_public:bool=False
    verified_legal_owner:bool=False
    real_credentials_used:bool=False
    external_network_requests:int=0
    authorized_for_trading:bool=False
    account_activated:bool=False


class RecordedPublicTransport:
    """A fully in-memory replacement of two documented Public API calls.

    It is intentionally NOT an HTTP client. Only synthetic secrets are
    accepted. Nothing performs DNS resolution or socket I/O.
    """

    def __init__(self,records):
        if not isinstance(records,dict) or len(records)>30:
            raise TypeError("Controlled response transcript required")
        self._records={}
        for secret,record in records.items():
            if (not isinstance(secret,str) or
                not secret.startswith(SYNTHETIC_SECRET_PREFIX) or
                not 20<=len(secret)<=256 or
                not isinstance(record,dict) or
                set(record)!={"auth","accounts"} or
                type(record["auth"]) is not RecordedResponse or
                type(record["accounts"]) is not RecordedResponse):
                raise TypeError("Only explicit synthetic Public transcripts accepted")
            self._records[secret]=record
        self._access={}
        self.network_requests=0
        self.recorded_calls=[]

    def exchange_access_token(self,secret,*,path=AUTH_PATH,validity_minutes=5):
        if (path!=AUTH_PATH or validity_minutes!=5 or
            not isinstance(secret,str) or
            not secret.startswith(SYNTHETIC_SECRET_PREFIX)):
            raise PublicPreflightDenied("CREDENTIAL_NOT_SYNTHETIC")
        self.recorded_calls.append(("POST",AUTH_PATH))
        record=self._records.get(secret)
        if record is None:
            return RecordedResponse(401,{})
        response=record["auth"]
        if response.status==200 and isinstance(response.payload,dict):
            token=response.payload.get("accessToken")
            # Tokens are synthetic and are not logged or exposed to callers.
            if isinstance(token,str) and token.startswith("SYNTHETIC-TOKEN-"):
                if token in self._access and self._access[token]!=secret:
                    raise PublicPreflightDenied("BAD_PROVIDER_RESPONSE")
                self._access[token]=secret
        return response

    def list_authenticated_accounts(self,token,*,path=ACCOUNTS_PATH):
        if (path!=ACCOUNTS_PATH or not isinstance(token,str) or
            not token.startswith("SYNTHETIC-TOKEN-") or
            token not in self._access):
            raise PublicPreflightDenied("AUTH_REJECTED")
        self.recorded_calls.append(("GET",ACCOUNTS_PATH))
        return self._records[self._access[token]]["accounts"]

    def submit_order(self,*_args,**_kwargs):
        raise PublicPreflightDenied("CREDENTIAL_NOT_SYNTHETIC")

    def transfer_funds(self,*_args,**_kwargs):
        raise PublicPreflightDenied("CREDENTIAL_NOT_SYNTHETIC")


def _status_or_error(reply):
    if type(reply) is not RecordedResponse or type(reply.status) is not int:
        raise PublicPreflightDenied("BAD_PROVIDER_RESPONSE")
    if reply.status in (401,403):
        raise PublicPreflightDenied("AUTH_REJECTED")
    if reply.status==429:
        raise PublicPreflightDenied("PROVIDER_RATE_LIMIT")
    if reply.status in (408,500,502,503,504):
        raise PublicPreflightDenied("PROVIDER_UNAVAILABLE")
    if reply.status!=200:
        raise PublicPreflightDenied("BAD_PROVIDER_RESPONSE")
    if not isinstance(reply.payload,dict):
        raise PublicPreflightDenied("BAD_PROVIDER_RESPONSE")
    return reply.payload


def _validated_account_ids(body):
    accounts=body.get("accounts")
    if not isinstance(accounts,list) or not 1<=len(accounts)<=MAX_ACCOUNTS:
        raise PublicPreflightDenied("BAD_PROVIDER_RESPONSE")
    ids=[]
    for account in accounts:
        if not isinstance(account,dict):
            raise PublicPreflightDenied("BAD_PROVIDER_RESPONSE")
        identifier=account.get("accountId")
        if (not isinstance(identifier,str) or not 1<=len(identifier)<=128
            or not identifier.isascii() or identifier.strip()!=identifier
            or any(ord(c)<33 for c in identifier)):
            raise PublicPreflightDenied("BAD_PROVIDER_RESPONSE")
        ids.append(identifier)
    if len(set(ids))!=len(ids):
        raise PublicPreflightDenied("BAD_PROVIDER_RESPONSE")
    return frozenset(ids)


class IsolatedPublicReadOnlyPreflight:
    """Read encrypted *synthetic* credentials only from a verified RAM DB.

    The caller cannot pass a credential or broker account ref; the account
    must already exist, be active, and be bound to its current owner.
    The only accepted transport is the in-memory RecordedPublicTransport.
    """

    def __init__(self,path,credential_key,transport):
        if type(transport) is not RecordedPublicTransport:
            raise TypeError("Only recorded offline Public responses are allowed")
        self.path=str(path)
        shadow_storage.require_isolated_source(self.path)
        try:
            self._cipher=Fernet(credential_key)
        except (ValueError,TypeError):
            raise PublicPreflightDenied("ISOLATED_FIXTURE_REQUIRED") from None
        self._transport=transport

    def check(self,user_id,account_id):
        shadow_storage.require_isolated_source(self.path)
        if (not isinstance(user_id,str) or not isinstance(account_id,str) or
            not 1<=len(user_id)<=128 or not 1<=len(account_id)<=128):
            raise TenantAccessError("Account unavailable")
        with account_scope._db(self.path) as con:
            account_scope.AccountScopeStore._check(con,user_id,account_id)
            row=con.execute("""SELECT a.provider_account_ref, c.credential_ciphertext
                FROM tenant_accounts a
                JOIN tenant_connections c
                  ON c.connection_id=a.connection_id AND c.user_id=a.user_id
                WHERE a.account_id=? AND a.user_id=? AND a.provider='public'
                  AND a.disabled_at IS NULL AND c.revoked_at IS NULL""",
                (account_id,user_id)).fetchone()
        if row is None:
            raise TenantAccessError("Account unavailable")
        try:
            secret=self._cipher.decrypt(row["credential_ciphertext"]).decode("utf-8")
        except (InvalidToken,UnicodeDecodeError,ValueError,TypeError):
            raise PublicPreflightDenied("CREDENTIAL_NOT_SYNTHETIC") from None
        if (not secret.startswith(SYNTHETIC_SECRET_PREFIX) or
            not 20<=len(secret)<=256):
            raise PublicPreflightDenied("CREDENTIAL_NOT_SYNTHETIC")
        # The only paths invoked are the documented token exchange and
        # account listing; transport is *recorded* and never uses requests.
        auth=_status_or_error(self._transport.exchange_access_token(secret))
        token=auth.get("accessToken")
        if (not isinstance(token,str) or
            not token.startswith("SYNTHETIC-TOKEN-") or len(token)>256):
            raise PublicPreflightDenied("BAD_PROVIDER_RESPONSE")
        body=_status_or_error(self._transport.list_authenticated_accounts(token))
        matches=_validated_account_ids(body)
        if row["provider_account_ref"] not in matches:
            raise PublicPreflightDenied("ACCOUNT_NOT_ACCESSIBLE")
        return ReadOnlyEvidence()
