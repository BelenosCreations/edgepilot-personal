"""Two-step, authenticated, session-bound approval for *offline tests only*.

This does not authorize real Public API calls. Every approval is explicitly
marked NON-LIVE and is rejected if the simulated global kill switch is on.
No Flask endpoint imports this module; only synthetic /dev/shm tests call it.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from . import account_scope, shadow_storage
from .identity_auth import IdentityStore
from .tenant_foundation import TenantAccessError
from .tenant_public_safety_state import OfflinePersistentSafety, SafetyGateDenied

EXPIRES_SECONDS=600
CONFIRM_TEXT="I APPROVE SYNTHETIC PUBLIC READ ONLY FOR THIS ACCOUNT"
SCOPE="SYNTHETIC_PUBLIC_ACCOUNT_LIST_ONLY"


class OfflineConsentDenied(RuntimeError):
    _CODES=frozenset(("UNAUTHENTICATED","BAD_CSRF","ACCOUNT_UNAVAILABLE",
                      "STALE_APPROVAL","EXPIRED","INVALID_CONFIRMATION"))
    def __init__(self,code):
        self.code=code if code in self._CODES else "STALE_APPROVAL"
        super().__init__(self.code)


class OfflineConsentCeremony:
    def __init__(self,path,identity_store,safety,*,clock=None):
        self.path=str(path)
        shadow_storage.require_isolated_source(self.path)
        if type(identity_store) is not IdentityStore or type(safety) is not OfflinePersistentSafety:
            raise TypeError("Verified test-only identity and safety required")
        if identity_store.path!=self.path or safety.path!=self.path:
            raise ValueError("Identity/safety source mismatch")
        self.identity_store=identity_store
        self.safety=safety
        self.clock=clock or time.time

    def setup(self):
        shadow_storage.require_isolated_source(self.path)
        with account_scope._db(self.path) as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS tenant_test_public_consents(
                consent_id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL,
                user_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                scope TEXT NOT NULL CHECK(scope='SYNTHETIC_PUBLIC_ACCOUNT_LIST_ONLY'),
                state TEXT NOT NULL CHECK(state IN
                  ('REQUESTED','CONFIRMED_OFFLINE','REVOKED')),
                revision INTEGER NOT NULL CHECK(revision>=1),
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                FOREIGN KEY(token_hash) REFERENCES
                  tenant_identity_sessions(token_hash) ON DELETE CASCADE,
                FOREIGN KEY(account_id,user_id)
                  REFERENCES tenant_accounts(account_id,user_id)
            );
            CREATE INDEX IF NOT EXISTS idx_test_consent_scope
                ON tenant_test_public_consents(user_id,account_id,state);
            """)

    def _principal(self,token,csrf):
        # Authentication and CSRF are required at *both* steps.
        if not isinstance(csrf,str):
            raise OfflineConsentDenied("BAD_CSRF")
        principal=self.identity_store.principal(token,csrf=csrf,now=int(self.clock()))
        if principal is None:
            raise OfflineConsentDenied("UNAUTHENTICATED")
        return principal["user_id"]

    def _now(self):
        value=self.clock()
        if type(value) not in (int,float) or not 0<=value<=253402300799:
            raise OfflineConsentDenied("STALE_APPROVAL")
        return int(value)

    def request(self,token,csrf,account_id):
        shadow_storage.require_isolated_source(self.path)
        now=self._now()
        user_id=self._principal(token,csrf)
        self.safety.require_ready(user_id,account_id)
        consent_id=secrets.token_urlsafe(24)
        with account_scope._db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            account_scope.AccountScopeStore._check(con,user_id,account_id)
            # Do not permit a stale/detached owner association.
            session=con.execute("""SELECT user_id FROM tenant_identity_sessions
                WHERE token_hash=? AND expires_at>?""",
                (hashlib.sha256(token.encode()).hexdigest(),now)).fetchone()
            if not session or session["user_id"]!=user_id:
                raise OfflineConsentDenied("UNAUTHENTICATED")
            con.execute("""INSERT INTO tenant_test_public_consents
                (consent_id,token_hash,user_id,account_id,scope,state,
                 revision,created_at,expires_at)
                VALUES(?,?,?,?,?,'REQUESTED',1,?,?)""",
                (consent_id,hashlib.sha256(token.encode()).hexdigest(),user_id,
                 account_id,SCOPE,now,now+EXPIRES_SECONDS))
        return {"approvalId":consent_id,"revision":1,"expiresAt":now+EXPIRES_SECONDS,
                "scope":SCOPE,"offlineOnly":True,
                "livePublicApproved":False,"tradingApproved":False}

    def confirm(self,token,csrf,consent_id,*,revision,confirmation):
        if (confirmation!=CONFIRM_TEXT or type(revision) is not int or revision!=1
            or not isinstance(consent_id,str) or len(consent_id)>128):
            raise OfflineConsentDenied("INVALID_CONFIRMATION")
        now=self._now()
        user_id=self._principal(token,csrf)
        shadow_storage.require_isolated_source(self.path)
        with account_scope._db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            row=con.execute("""SELECT user_id,account_id,token_hash,expires_at,
                revision,state FROM tenant_test_public_consents
                WHERE consent_id=?""",(consent_id,)).fetchone()
            if not row or row["user_id"]!=user_id or not hmac.compare_digest(
                row["token_hash"],hashlib.sha256(token.encode()).hexdigest()):
                raise OfflineConsentDenied("STALE_APPROVAL")
            account_scope.AccountScopeStore._check(con,user_id,row["account_id"])
            self.safety.require_ready(user_id,row["account_id"])
            if row["expires_at"]<=now:
                raise OfflineConsentDenied("EXPIRED")
            changed=con.execute("""UPDATE tenant_test_public_consents
                SET state='CONFIRMED_OFFLINE',revision=revision+1
                WHERE consent_id=? AND user_id=? AND token_hash=?
                AND state='REQUESTED' AND revision=? AND expires_at>?""",
                (consent_id,user_id,row["token_hash"],revision,now)).rowcount
            if changed!=1:
                raise OfflineConsentDenied("STALE_APPROVAL")
        return {"confirmedOffline":True,"revision":2,"livePublicApproved":False,
                "tradingApproved":False,"fundsApproved":False}

    def assert_confirmed(self,token,account_id,consent_id):
        shadow_storage.require_isolated_source(self.path)
        if not isinstance(consent_id,str):
            raise OfflineConsentDenied("STALE_APPROVAL")
        user_id=self.identity_store.principal(token,now=self._now())
        if user_id is None:
            raise OfflineConsentDenied("UNAUTHENTICATED")
        user_id=user_id["user_id"]
        self.safety.require_ready(user_id,account_id)
        with account_scope._db(self.path) as con:
            row=con.execute("""SELECT 1 FROM tenant_test_public_consents
                WHERE consent_id=? AND user_id=? AND account_id=?
                  AND token_hash=? AND state='CONFIRMED_OFFLINE'
                  AND expires_at>?""",
                (consent_id,user_id,account_id,
                 hashlib.sha256(token.encode()).hexdigest(),self._now())).fetchone()
            if row is None:
                raise OfflineConsentDenied("STALE_APPROVAL")
        return {"offlineConsentVerified":True,"livePublicApproved":False}

    def revoke_for_account(self,user_id,account_id):
        """Internal-only, never exposed over Flask in v0.2.22."""
        shadow_storage.require_isolated_source(self.path)
        with account_scope._db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            account_scope.AccountScopeStore._check(con,user_id,account_id)
            con.execute("""UPDATE tenant_test_public_consents
                SET state='REVOKED',revision=revision+1
                WHERE user_id=? AND account_id=? AND state<>'REVOKED'""",
                (user_id,account_id))
        return {"offlineApprovalsRevoked":True,"livePublicApproved":False}

    def approve_live_public(self,*args,**kwargs):
        raise OfflineConsentDenied("INVALID_CONFIRMATION")
