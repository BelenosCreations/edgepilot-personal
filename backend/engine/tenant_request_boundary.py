"""Dormant tenant-only request contract; never registered with Flask.

This adapter deliberately has no live HTTP routes. It models a future
separate read-only API by dispatching an explicit allowlist of methods and
canonical path forms to the independently tested DormantAccountGateway.

It does not validate HTTP Origin, TLS, cookie flags, CSRF bootstrap, request
body size, rate limits or end-to-end middleware. Those must be separately
reviewed when the real API is built. No broker requests, trades or transfers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from .tenant_api_gateway import DormantAccountGateway


class TenantRequestDenied(PermissionError):
    """Constant error text: never disclose owner/account existence."""


@dataclass(frozen=True)
class DormantRequest:
    method: str
    path: str
    token: str
    csrf: str | None = None
    payload: dict[str, Any] | None = None
    params: dict[str, Any] | None = None


_SAFE_STATIC={
    ("GET","/tenant/accounts"),
    ("GET","/tenant/selected"),
    ("POST","/tenant/selected"),
    ("DELETE","/tenant/selected"),
}
_ACCOUNT_ROUTE=re.compile(
    r"^/tenant/accounts/([a-f0-9-]{36})/(summary|history|details|references)$"
)
_UUID_RE=re.compile(
    r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$"
)
_KNOWN_METHODS=frozenset(("GET","POST","DELETE"))


def _account_id(raw: Any) -> str:
    if not isinstance(raw,str) or not _UUID_RE.fullmatch(raw):
        raise TenantRequestDenied("Invalid tenant request")
    try:
        if str(UUID(raw))!=raw:
            raise ValueError()
    except (ValueError,AttributeError):
        raise TenantRequestDenied("Invalid tenant request") from None
    return raw


def _empty(value: dict[str, Any] | None) -> None:
    if value is not None and (not isinstance(value,dict) or value):
        raise TenantRequestDenied("Invalid tenant request")


class DormantRequestBoundary:
    """Pure request-to-gateway contract with strict one-account routing.

    Identity comes ONLY from the gateway's trusted IdentityStore via token.
    No caller-provided user_id, provider account ref, action, or mode can be
    dispatched. Unknown/future routes, ambiguous encodings and methods deny.
    """

    def __init__(self,gateway: DormantAccountGateway):
        if not isinstance(gateway,DormantAccountGateway):
            raise TypeError("Verified tenant gateway required")
        self._gateway=gateway

    def dispatch(self,request: DormantRequest) -> dict[str, Any]:
        if not isinstance(request,DormantRequest):
            raise TenantRequestDenied("Invalid tenant request")
        method,path=request.method,request.path
        if (not isinstance(method,str) or method not in _KNOWN_METHODS
            or not isinstance(path,str) or not path.isascii()
            or len(path)>160 or "#" in path or "?" in path or "%" in path
            or "//" in path or ".." in path or "\\" in path):
            raise TenantRequestDenied("Invalid tenant request")
        m=_ACCOUNT_ROUTE.fullmatch(path)
        if (method,path) not in _SAFE_STATIC and not (method=="GET" and m):
            raise TenantRequestDenied("Unknown or prohibited tenant route")
        if path=="/tenant/accounts":
            _empty(request.payload)
            _empty(request.params)
            return {"accounts":self._gateway.list_accounts(request.token),
                    "readOnly":True}
        if path=="/tenant/selected":
            _empty(request.params)
            if method=="GET":
                _empty(request.payload)
                return {"selectedAccountId":self._gateway.selected_account(request.token),
                        "readOnly":True}
            if method=="DELETE":
                _empty(request.payload)
                return self._gateway.clear_selection(request.token,request.csrf)
            if method=="POST":
                if (not isinstance(request.payload,dict) or
                    set(request.payload)!={"account_id"}):
                    raise TenantRequestDenied("Invalid tenant request")
                account_id=_account_id(request.payload["account_id"])
                return self._gateway.select_account(request.token,request.csrf,account_id)
        if m is None:
            raise TenantRequestDenied("Unknown or prohibited tenant route")
        account_id=_account_id(m.group(1))
        view=m.group(2)
        _empty(request.payload)
        if view=="summary":
            _empty(request.params)
            return self._gateway.account_summary(request.token,account_id)
        if view=="history":
            _empty(request.params)
            return self._gateway.history_summary(request.token,account_id)
        if view=="details":
            _empty(request.params)
            return self._gateway.details_summary(request.token,account_id)
        if view=="references":
            params=request.params or {}
            if not isinstance(params,dict) or not set(params).issubset(
                {"before_id","limit"}
            ):
                raise TenantRequestDenied("Invalid tenant request")
            return self._gateway.page_history(request.token,account_id,
                before_id=params.get("before_id"),limit=params.get("limit",50))
        raise TenantRequestDenied("Unknown or prohibited tenant route")

    def submit_order(self,*_args: Any,**_kwargs: Any) -> None:
        raise TenantRequestDenied("Tenant execution is disabled")

    def transfer_funds(self,*_args: Any,**_kwargs: Any) -> None:
        raise TenantRequestDenied("Tenant funds operations are disabled")
