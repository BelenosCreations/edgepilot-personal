"""Atomic encrypted *synthetic* Public credential rotation rehearsal.

A connection may back multiple accounts: every affected account must have
its own current session-scoped, offline-only consent before rotation.
Rotating revokes ALL consents for that connection and pauses ALL its accounts.
No real Public key rotation, provider revocation, external calls or live use.
"""
from __future__ import annotations

import hashlib

from cryptography.fernet import Fernet, InvalidToken

from . import account_scope, shadow_storage
from .tenant_foundation import TenantAccessError
from .identity_auth import IdentityStore
from .tenant_public_offline_consent import OfflineConsentCeremony, OfflineConsentDenied
from .tenant_public_safety_state import OfflinePersistentSafety, SafetyGateDenied


class SyntheticRotationDenied(RuntimeError):
    _CODES=frozenset(("INVALID_SYNTHETIC_SECRET","STALE_GENERATION",
                      "MISSING_ACCOUNT_APPROVAL","CONNECTION_UNAVAILABLE"))
    def __init__(self,code):
        self.code=code if code in self._CODES else "CONNECTION_UNAVAILABLE"
        super().__init__(self.code)


class OfflineCredentialRotation:
    def __init__(self,path,key,identities,consents,safety):
        self.path=str(path)
        shadow_storage.require_isolated_source(self.path)
        if (type(identities) is not IdentityStore or
            type(consents) is not OfflineConsentCeremony or
            type(safety) is not OfflinePersistentSafety):
            raise TypeError("Verified isolated security components required")
        if any(x.path!=self.path for x in (identities,consents,safety)):
            raise ValueError("Security components must share same offline database")
        try:
            self.cipher=Fernet(key)
        except (ValueError,TypeError):
            raise SyntheticRotationDenied("INVALID_SYNTHETIC_SECRET") from None
        self.identities=identities
        self.consents=consents
        self.safety=safety

    def setup(self):
        shadow_storage.require_isolated_source(self.path)
        with account_scope._db(self.path) as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS tenant_test_connection_generation(
                connection_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                generation INTEGER NOT NULL CHECK(generation>=1),
                PRIMARY KEY(connection_id,user_id),
                FOREIGN KEY(connection_id,user_id)
                  REFERENCES tenant_connections(connection_id,user_id)
            );
            CREATE TABLE IF NOT EXISTS tenant_test_rotation_audit(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                connection_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                generation INTEGER NOT NULL,
                outcome TEXT NOT NULL DEFAULT 'SYNTHETIC_ROTATED'
                  CHECK(outcome='SYNTHETIC_ROTATED'),
                FOREIGN KEY(connection_id,user_id)
                  REFERENCES tenant_connections(connection_id,user_id)
            );
            """)

    @staticmethod
    def _valid_secret(value):
        return (isinstance(value,str) and
                value.startswith("SYNTHETIC-") and
                24<=len(value)<=256 and value.isascii() and
                all(33<=ord(c)<=126 for c in value))

    def _context(self,con,user_id,account_id):
        account_scope.AccountScopeStore._check(con,user_id,account_id)
        row=con.execute("""SELECT c.connection_id,c.credential_ciphertext
            FROM tenant_connections c JOIN tenant_accounts a
              ON a.connection_id=c.connection_id AND a.user_id=c.user_id
            WHERE a.user_id=? AND a.account_id=? AND a.provider='public'
              AND a.disabled_at IS NULL AND c.revoked_at IS NULL""",
            (user_id,account_id)).fetchone()
        if row is None:
            raise TenantAccessError("Account unavailable")
        return row

    def generation(self,token,account_id):
        shadow_storage.require_isolated_source(self.path)
        principal=self.identities.principal(token)
        if principal is None:
            raise OfflineConsentDenied("UNAUTHENTICATED")
        with account_scope._db(self.path) as con:
            row=self._context(con,principal["user_id"],account_id)
            generation=con.execute("""SELECT generation FROM tenant_test_connection_generation
                WHERE connection_id=? AND user_id=?""",
                (row["connection_id"],principal["user_id"])).fetchone()
            return generation["generation"] if generation else 0

    def rotate_synthetic(self,token,csrf,account_id,*,approval_ids,
                         expected_generation,new_synthetic_secret):
        if not self._valid_secret(new_synthetic_secret):
            raise SyntheticRotationDenied("INVALID_SYNTHETIC_SECRET")
        if type(expected_generation) is not int or expected_generation<0:
            raise SyntheticRotationDenied("STALE_GENERATION")
        principal=self.identities.principal(token,csrf=csrf)
        if principal is None:
            raise OfflineConsentDenied("UNAUTHENTICATED")
        user_id=principal["user_id"]
        if not isinstance(approval_ids,dict):
            raise SyntheticRotationDenied("MISSING_ACCOUNT_APPROVAL")
        shadow_storage.require_isolated_source(self.path)
        with account_scope._db(self.path) as con:
            context=self._context(con,user_id,account_id)
            accounts=[r["account_id"] for r in con.execute("""
                SELECT account_id FROM tenant_accounts
                WHERE user_id=? AND connection_id=? ORDER BY account_id""",
                (user_id,context["connection_id"]))]
        if set(approval_ids)!=set(accounts):
            raise SyntheticRotationDenied("MISSING_ACCOUNT_APPROVAL")
        # Consent is independently scoped to each affected account and the
        # same session. Prior approval is not authorization for real Public.
        for aid in accounts:
            self.consents.assert_confirmed(token,aid,approval_ids[aid])
        with account_scope._db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            self.safety._global(con)
            current=self._context(con,user_id,account_id)
            if current["connection_id"]!=context["connection_id"]:
                raise SyntheticRotationDenied("CONNECTION_UNAVAILABLE")
            current_accounts={r["account_id"] for r in con.execute("""
                SELECT account_id FROM tenant_accounts
                WHERE user_id=? AND connection_id=?""",
                (user_id,current["connection_id"]))}
            if current_accounts!=set(accounts):
                raise SyntheticRotationDenied("MISSING_ACCOUNT_APPROVAL")
            row=con.execute("""SELECT generation FROM tenant_test_connection_generation
                WHERE connection_id=? AND user_id=?""",
                (current["connection_id"],user_id)).fetchone()
            previous=row["generation"] if row else 0
            if previous!=expected_generation:
                raise SyntheticRotationDenied("STALE_GENERATION")
            for aid in accounts:
                account_scope.AccountScopeStore._check(con,user_id,aid)
                approved=con.execute("""SELECT 1 FROM tenant_test_public_consents
                    WHERE consent_id=? AND user_id=? AND account_id=?
                      AND token_hash=? AND state='CONFIRMED_OFFLINE'
                      AND expires_at>?""",(
                    approval_ids[aid],user_id,aid,
                    hashlib.sha256(token.encode()).hexdigest(),
                    self.consents._now())).fetchone()
                if approved is None:
                    raise SyntheticRotationDenied("MISSING_ACCOUNT_APPROVAL")
            try:
                old_secret=self.cipher.decrypt(current["credential_ciphertext"]).decode("utf-8")
            except (InvalidToken,UnicodeDecodeError,ValueError,TypeError):
                raise SyntheticRotationDenied("INVALID_SYNTHETIC_SECRET") from None
            if not self._valid_secret(old_secret) or old_secret==new_synthetic_secret:
                raise SyntheticRotationDenied("INVALID_SYNTHETIC_SECRET")
            ciphertext=self.cipher.encrypt(new_synthetic_secret.encode("utf-8"))
            changed=con.execute("""UPDATE tenant_connections
                SET credential_ciphertext=? WHERE connection_id=? AND user_id=?
                  AND revoked_at IS NULL AND credential_ciphertext=?""",
                (ciphertext,current["connection_id"],user_id,current["credential_ciphertext"])).rowcount
            if changed!=1:
                raise SyntheticRotationDenied("CONNECTION_UNAVAILABLE")
            con.execute("""INSERT INTO tenant_test_connection_generation
                (connection_id,user_id,generation) VALUES(?,?,?)
                ON CONFLICT(connection_id,user_id) DO UPDATE
                SET generation=excluded.generation""",
                (current["connection_id"],user_id,expected_generation+1))
            for aid in accounts:
                con.execute("""UPDATE tenant_test_public_consents
                    SET state='REVOKED',revision=revision+1
                    WHERE user_id=? AND account_id=? AND state<>'REVOKED'""",
                    (user_id,aid))
                con.execute("""INSERT INTO tenant_test_safety_pauses
                    (user_id,account_id,paused,revision) VALUES(?,?,1,1)
                    ON CONFLICT(user_id,account_id) DO UPDATE
                    SET paused=1,revision=revision+1""",(user_id,aid))
            con.execute("""INSERT INTO tenant_test_rotation_audit
                (connection_id,user_id,generation) VALUES(?,?,?)""",
                (current["connection_id"],user_id,expected_generation+1))
        return {"syntheticGeneration":expected_generation+1,
                "affectedAccountCount":len(accounts),
                "affectedAccountsPaused":True,"priorApprovalsRevoked":True,
                "providerCredentialActuallyRotated":False,
                "livePublicApproved":False,"tradingEnabled":False}

    def rotate_real_credential(self,*args,**kwargs):
        raise SyntheticRotationDenied("CONNECTION_UNAVAILABLE")
