"""User-owned Public READ-ONLY account verification, never legacy globals.

Each call validates a real EdgePilot identity session, decrypts only that
identity's Public secret, exchanges a strictly scoped token, and uses only the
allowlisted account list and portfolio endpoints. Zero order/transfer code.
HTTP activation belongs behind an independent disabled-by-default flag.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
import sqlite3
import time
from urllib.parse import quote

import requests

from . import identity_auth, tenant_foundation, tenant_public_vault

BASE="https://api.public.com"
AUTH_PATH="/userapiauthservice/personal/access-tokens"
LIST_PATH="/userapigateway/trading/account"
ACCOUNT_ID=re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
PER_USER_PER_MINUTE=20
GLOBAL_PER_MINUTE=250
MAX_ACCOUNTS=30
MAX_POSITIONS=100
TIMEOUT=12


class PublicReadUnavailable(RuntimeError):
    """Uninformative provider failure: never return upstream response/keys."""


def _safe_id(value):
    if not isinstance(value,str) or not ACCOUNT_ID.fullmatch(value):
        raise PublicReadUnavailable("Public account unavailable")
    return value


def _decimal(value):
    try:
        n=Decimal(str(value))
        if not n.is_finite() or n < 0:
            raise InvalidOperation
        return str(n.quantize(Decimal("0.01")))
    except (InvalidOperation,ValueError,TypeError,OverflowError):
        raise PublicReadUnavailable("Public portfolio unavailable") from None


def setup(path):
    """Opt-in quota table; not a production ledger, no legacy mutations."""
    with tenant_foundation._open(path) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS tenant_public_read_quota(
            id INTEGER PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES tenant_users(user_id),
            connection_id TEXT NOT NULL,
            attempted_at INTEGER NOT NULL,
            FOREIGN KEY(connection_id,user_id)
                REFERENCES tenant_connections(connection_id,user_id)
        )""")
        db.execute("""CREATE INDEX IF NOT EXISTS idx_tenant_public_read_time
            ON tenant_public_read_quota(attempted_at)""")
        db.execute("""CREATE INDEX IF NOT EXISTS idx_tenant_public_read_user
            ON tenant_public_read_quota(user_id,attempted_at)""")


class TenantPublicReadOnly:
    def __init__(self, path, identity_store, vault, *, http=None, clock=None):
        if not isinstance(identity_store,identity_auth.IdentityStore):
            raise TypeError("Verified identity repository required")
        if not isinstance(vault,tenant_public_vault.TenantPublicVault):
            raise TypeError("User-owned encrypted vault required")
        if str(path)!=identity_store.path or str(path)!=vault.path:
            raise ValueError("Public, identity and vault must share tenant database")
        self.path=str(path)
        self.identities=identity_store
        self.vault=vault
        self.http=http if http is not None else requests
        self.clock=clock if clock is not None else time.time

    def _principal(self,identity_token,csrf=None):
        principal=self.identities.principal(identity_token,csrf)
        if principal is None:
            raise PublicReadUnavailable("Not authenticated")
        return principal["user_id"]

    def _admit(self, owner, connection_id):
        now=int(self.clock())
        if now<=0:
            raise PublicReadUnavailable("Public request unavailable")
        with tenant_foundation._open(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("""SELECT revoked_at FROM tenant_connections
                WHERE connection_id=? AND user_id=? AND provider='public'""",
                (connection_id,owner)).fetchone()
            if row is None or row["revoked_at"] is not None:
                raise PublicReadUnavailable("Public connection unavailable")
            latest=db.execute("SELECT MAX(attempted_at) FROM tenant_public_read_quota").fetchone()[0]
            if latest is not None and now < latest:
                raise PublicReadUnavailable("Public request unavailable")
            db.execute("DELETE FROM tenant_public_read_quota WHERE attempted_at<=?",
                       (now-60,))
            total=db.execute("SELECT COUNT(*) FROM tenant_public_read_quota").fetchone()[0]
            individual=db.execute("""SELECT COUNT(*) FROM tenant_public_read_quota
                WHERE user_id=?""",(owner,)).fetchone()[0]
            if total>=GLOBAL_PER_MINUTE or individual>=PER_USER_PER_MINUTE:
                raise PublicReadUnavailable("Public request limit reached")
            db.execute("""INSERT INTO tenant_public_read_quota
                (user_id,connection_id,attempted_at) VALUES(?,?,?)""",
                (owner,connection_id,now))

    def _get_json(self,response):
        try:
            if int(response.status_code)!=200:
                raise ValueError
            data=response.json()
            if not isinstance(data,dict):
                raise ValueError
            return data
        except (ValueError,TypeError,AttributeError):
            raise PublicReadUnavailable("Public service unavailable") from None

    def _token(self, identity_token, connection_id):
        # Must NOT cache access tokens globally: they belong to a single
        # user's provider credential. No raw key/token is returned to HTTP.
        secret=self.vault._credential_for_provider_only(identity_token,connection_id)
        try:
            response=self.http.post(BASE+AUTH_PATH,
                json={"secret":secret,"validityInMinutes":5},timeout=TIMEOUT)
            value=self._get_json(response).get("accessToken")
            if not isinstance(value,str) or not 20<=len(value)<=4096 or any(
                ch in value for ch in "\r\n\0"):
                raise ValueError
            return value
        except (requests.RequestException,TypeError,ValueError,PublicReadUnavailable):
            raise PublicReadUnavailable("Public authentication unavailable") from None

    def _accounts(self,access_token):
        try:
            response=self.http.get(BASE+LIST_PATH,
                headers={"Authorization":"Bearer "+access_token,
                         "Accept":"application/json"},timeout=TIMEOUT)
            items=self._get_json(response).get("accounts")
            if not isinstance(items,list) or len(items)>MAX_ACCOUNTS:
                raise ValueError
            normalized=[]
            seen=set()
            for item in items:
                if not isinstance(item,dict):
                    raise ValueError
                account=_safe_id(item.get("accountId"))
                if account in seen:
                    raise ValueError
                seen.add(account)
                account_type=item.get("accountType","")
                if not isinstance(account_type,str):
                    account_type=""
                normalized.append({"accountId":account,
                                   "accountType":account_type[:40]})
            return normalized
        except (requests.RequestException,TypeError,ValueError,PublicReadUnavailable):
            raise PublicReadUnavailable("Public account discovery unavailable") from None

    def discover(self, identity_token, connection_id):
        owner=self._principal(identity_token)
        conn=tenant_public_vault._uuid(connection_id)
        self._admit(owner,conn)
        token=self._token(identity_token,conn)
        accounts=self._accounts(token)
        if self._principal(identity_token)!=owner:
            raise PublicReadUnavailable("Session no longer valid")
        # The provider key may be rotated while the HTTPS request is in
        # flight. Recheck the stored ciphertext's active ownership before
        # returning and require a fresh discovery after any later change.
        self.vault._credential_for_provider_only(identity_token,conn)
        return {"connectionId":conn,"accounts":accounts,
                "readOnly":True,"ordersEnabled":False}

    def link_verified(self, identity_token, csrf, connection_id,
                      provider_account_ref, label):
        owner=self._principal(identity_token,csrf)
        conn=tenant_public_vault._uuid(connection_id)
        account=_safe_id(provider_account_ref)
        if not isinstance(label,str) or not 1<=len(label.strip())<=64:
            raise PublicReadUnavailable("Invalid account label")
        listed=self.discover(identity_token,conn)
        if not any(a["accountId"]==account for a in listed["accounts"]):
            raise PublicReadUnavailable("Public account unavailable")
        # The tenant store atomically rejects cross-owner/revoked connections.
        try:
            internal=self.vault.tenants.link_account(owner,conn,account,label)
        except (sqlite3.IntegrityError,tenant_foundation.TenantAccessError,
                ValueError):
            raise PublicReadUnavailable("Public account unavailable") from None
        return {"accountId":internal,"verifiedByPublic":True,
                "readOnly":True,"ordersEnabled":False}

    def portfolio(self,identity_token,internal_account_id):
        owner=self._principal(identity_token)
        account_uuid=tenant_public_vault._uuid(internal_account_id)
        with tenant_foundation._open(self.path) as db:
            row=db.execute("""SELECT a.provider_account_ref,a.connection_id
                FROM tenant_accounts a
                JOIN tenant_connections c
                  ON c.connection_id=a.connection_id AND c.user_id=a.user_id
                WHERE a.user_id=? AND a.account_id=? AND a.disabled_at IS NULL
                AND c.revoked_at IS NULL AND a.provider='public'
                AND c.provider='public'""",
                (owner,account_uuid)).fetchone()
        if row is None:
            raise PublicReadUnavailable("Public account unavailable")
        conn=row["connection_id"]
        provider_id=_safe_id(row["provider_account_ref"])
        self._admit(owner,conn)
        token=self._token(identity_token,conn)
        # Refresh the authoritative provider account list before each
        # portfolio read. An arbitrary guessed provider ID is never fetched.
        if provider_id not in {r["accountId"] for r in self._accounts(token)}:
            raise PublicReadUnavailable("Public account unavailable")
        path="/userapigateway/trading/"+quote(provider_id,safe="")+"/portfolio/v2"
        try:
            response=self.http.get(BASE+path,
                headers={"Authorization":"Bearer "+token,
                         "Accept":"application/json"},timeout=TIMEOUT)
            data=self._get_json(response)
            amount=_decimal(data.get("totalAccountValue"))
            if not isinstance(data.get("positions"),list) or len(data["positions"])>MAX_POSITIONS:
                raise ValueError
            positions=[]
            for item in data["positions"]:
                if not isinstance(item,dict):
                    raise ValueError
                instrument=item.get("instrument") or {}
                if not isinstance(instrument,dict):
                    raise ValueError
                symbol=str(instrument.get("symbol") or item.get("symbol") or "")[:30]
                if not re.fullmatch(r"[A-Za-z0-9.^_-]{1,30}",symbol):
                    raise ValueError
                positions.append({
                    "symbol":symbol,
                    "currentValue":_decimal(item.get("currentValue")),
                    "quantity":str(item.get("quantity","0"))[:40],
                })
        except (requests.RequestException,TypeError,ValueError,PublicReadUnavailable):
            raise PublicReadUnavailable("Public portfolio unavailable") from None
        # Recheck session, connection and account after the HTTPS calls.
        if self._principal(identity_token)!=owner:
            raise PublicReadUnavailable("Session no longer valid")
        with tenant_foundation._open(self.path) as db:
            still_active=db.execute("""SELECT 1 FROM tenant_accounts a
                JOIN tenant_connections c
                  ON c.connection_id=a.connection_id AND c.user_id=a.user_id
                WHERE a.user_id=? AND a.account_id=? AND a.connection_id=?
                  AND a.provider_account_ref=? AND a.disabled_at IS NULL
                  AND c.revoked_at IS NULL""",
                (owner,account_uuid,conn,provider_id)).fetchone()
        if still_active is None:
            raise PublicReadUnavailable("Public account unavailable")
        return {"accountId":account_uuid,"balance":amount,"holdings":positions,
                "readOnly":True,"ordersEnabled":False,"transfersEnabled":False}
