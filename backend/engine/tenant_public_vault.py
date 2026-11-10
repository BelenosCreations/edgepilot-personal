"""Identity-scoped encrypted Public credentials for a future shared EdgePilot.

User ownership is derived ONLY from a verified identity session, never a
client userId. No HTTP call, provider account lookup, broker trade, funds
movement or legacy owner key. Supports explicit offline connection lifecycle.
"""
from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
import uuid

from cryptography.fernet import InvalidToken

from . import identity_auth, tenant_foundation


class TenantVaultDenied(PermissionError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _uuid(value):
    if not isinstance(value,str) or len(value)!=36:
        raise TenantVaultDenied("Connection unavailable")
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError
    except ValueError:
        raise TenantVaultDenied("Connection unavailable") from None
    return value


def setup(path):
    """Additive, opt-in audit schema. No changes to legacy broker_credentials."""
    with tenant_foundation._open(path) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS tenant_public_vault_events(
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES tenant_users(user_id),
            connection_id TEXT NOT NULL,
            event TEXT NOT NULL CHECK(event IN('ROTATE','REVOKE')),
            happened_at TEXT NOT NULL,
            FOREIGN KEY(connection_id,user_id)
                REFERENCES tenant_connections(connection_id,user_id)
        )""")
        db.execute("""CREATE INDEX IF NOT EXISTS idx_tenant_vault_events_user
            ON tenant_public_vault_events(user_id,happened_at)""")
        db.execute("""CREATE TRIGGER IF NOT EXISTS no_tenant_vault_event_delete
            BEFORE DELETE ON tenant_public_vault_events
            BEGIN SELECT RAISE(ABORT,'audit append-only'); END""")
        db.execute("""CREATE TRIGGER IF NOT EXISTS no_tenant_vault_event_rewrite
            BEFORE UPDATE ON tenant_public_vault_events
            BEGIN SELECT RAISE(ABORT,'audit append-only'); END""")


class TenantPublicVault:
    """An identity-only facade over tenant_foundation encrypted credentials."""

    def __init__(self, path, identity_store, credential_key=None):
        if not isinstance(identity_store,identity_auth.IdentityStore):
            raise TypeError("Independent identity session validation required")
        self.path=str(path)
        if identity_store.path!=self.path:
            raise ValueError("Credential repository must share identity database")
        self.identities=identity_store
        self.tenants=tenant_foundation.TenantStore(
            self.path,credential_key=credential_key)

    def _principal(self, identity_token, csrf=None):
        user=self.identities.principal(identity_token,csrf)
        if user is None:
            raise TenantVaultDenied("Not authenticated")
        return user["user_id"]

    @staticmethod
    def _secret(secret):
        if (not isinstance(secret,str) or
            not 20<=len(secret.strip())<=2048 or
            any(char in secret for char in "\x00\r\n") or
            secret.strip()=="PLACE_PUBLIC_SECRET_HERE"):
            raise TenantVaultDenied("Credential format invalid")
        return secret.strip()

    def list_connections(self, identity_token):
        user_id=self._principal(identity_token)
        with tenant_foundation._open(self.path) as db:
            rows=db.execute("""SELECT connection_id,created_at,revoked_at
                FROM tenant_connections
                WHERE user_id=? AND provider='public'
                ORDER BY created_at,connection_id""",
                (user_id,)).fetchall()
        return {"connections":[{
            "connectionId":row["connection_id"],
            "createdAt":row["created_at"],
            "status":"revoked" if row["revoked_at"] else "stored_unverified",
            "provider":"public",
        } for row in rows], "secretsReturned":False, "realOrdersEnabled":False}

    def save(self, identity_token, csrf, secret):
        user_id=self._principal(identity_token,csrf)
        secret=self._secret(secret)
        try:
            connection_id=self.tenants.add_connection(user_id,secret)
        except (ValueError,RuntimeError,tenant_foundation.TenantAccessError):
            raise TenantVaultDenied("Credential could not be stored securely") from None
        return {"connectionId":connection_id,"status":"stored_unverified",
                "secretReturned":False,"realOrdersEnabled":False}

    def _rotate_or_revoke(self, identity_token, csrf, connection_id, secret=None):
        owner=self._principal(identity_token,csrf)
        conn_id=_uuid(connection_id)
        event="REVOKE" if secret is None else "ROTATE"
        ciphertext=None
        if event=="ROTATE":
            value=self._secret(secret)
            try:
                ciphertext=self.tenants._fernet().encrypt(value.encode("utf-8"))
            except (ValueError,RuntimeError):
                raise TenantVaultDenied("Credential could not be stored securely") from None
        with tenant_foundation._open(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("""SELECT connection_id FROM tenant_connections
                WHERE connection_id=? AND user_id=? AND provider='public'
                  AND revoked_at IS NULL""",
                (conn_id,owner)).fetchone()
            if row is None:
                raise TenantVaultDenied("Connection unavailable")
            if event=="ROTATE":
                db.execute("""UPDATE tenant_connections SET credential_ciphertext=?
                    WHERE connection_id=? AND user_id=? AND revoked_at IS NULL""",
                    (ciphertext,conn_id,owner))
            else:
                db.execute("""UPDATE tenant_connections SET revoked_at=?
                    WHERE connection_id=? AND user_id=? AND revoked_at IS NULL""",
                    (_now(),conn_id,owner))
            # A rotated key may point to a different provider account.
            # Existing bindings are no longer verified and cannot be reused.
            db.execute("""UPDATE tenant_accounts SET disabled_at=?
                WHERE connection_id=? AND user_id=? AND disabled_at IS NULL""",
                (_now(),conn_id,owner))
            db.execute("""INSERT INTO tenant_public_vault_events
                (user_id,connection_id,event,happened_at) VALUES(?,?,?,?)""",
                (owner,conn_id,event,_now()))
        return {"status":"revoked" if event=="REVOKE" else "stored_unverified",
                "boundAccountsDisabled":True,"secretsReturned":False,
                "realOrdersEnabled":False}

    def rotate(self, identity_token, csrf, connection_id, secret):
        # A missing/null rotation secret is invalid, never a disconnect.
        self._secret(secret)
        return self._rotate_or_revoke(identity_token,csrf,connection_id,secret)

    def disconnect(self, identity_token, csrf, connection_id):
        return self._rotate_or_revoke(identity_token,csrf,connection_id)

    def _credential_for_provider_only(self, identity_token, connection_id):
        """Internal broker adapter ONLY. Never return this value to HTTP/UI.

        Later production adapter must enforce provider allowlist, per-owner
        request budget, account link verification and global emergency stop.
        """
        owner=self._principal(identity_token)
        conn_id=_uuid(connection_id)
        with tenant_foundation._open(self.path) as db:
            row=db.execute("""SELECT credential_ciphertext FROM tenant_connections
                WHERE connection_id=? AND user_id=? AND provider='public'
                AND revoked_at IS NULL""",(conn_id,owner)).fetchone()
        if row is None:
            raise TenantVaultDenied("Connection unavailable")
        try:
            return self.tenants._fernet().decrypt(row["credential_ciphertext"]).decode("utf-8")
        except (InvalidToken,RuntimeError,UnicodeError,ValueError,TypeError):
            raise TenantVaultDenied("Connection unavailable") from None
