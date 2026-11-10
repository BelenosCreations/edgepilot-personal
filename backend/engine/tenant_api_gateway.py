"""Inactive, session-scoped account selection and read-only API boundary.

No HTTP routes, imports from the live app, brokerage calls, user enrollment,
worker activation, order entry or fund movement. All user IDs are derived from
verified identity sessions, NEVER supplied by clients.

This is a future application-service layer, not a completed multi-tenant API.
Actual legacy HTTP route conversion remains a separate cutover blocker.
"""
from __future__ import annotations

import hashlib
import hmac
import sqlite3
import time

from . import account_scope, tenant_history, tenant_history_details
from .tenant_foundation import TenantAccessError

class AccountSelectionError(TenantAccessError):
    """No private identity or account information in error messages."""


def _hash_token(token):
    if not isinstance(token, str) or not 25 < len(token) < 256:
        raise AccountSelectionError("Identity session unavailable")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _require_identifier(value):
    if not isinstance(value,str) or not 1 <= len(value) <= 128 or not value.isascii():
        raise AccountSelectionError("Account unavailable")
    return value


def setup(path):
    """Opt-in schema for tests and a future reviewed tenant-only service.

    It never alters old selected_account, legacy cookies, Public connection,
    worker settings, or Android state. Each device session has its own row.
    """
    with account_scope._db(path) as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS tenant_session_account_selection (
            token_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            selected_at INTEGER NOT NULL,
            FOREIGN KEY(token_hash) REFERENCES
                tenant_identity_sessions(token_hash) ON DELETE CASCADE,
            FOREIGN KEY(account_id,user_id) REFERENCES
                tenant_accounts(account_id,user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_tenant_session_selection_user
            ON tenant_session_account_selection(user_id,account_id);
        CREATE TRIGGER IF NOT EXISTS tenant_selection_session_owner_insert
        BEFORE INSERT ON tenant_session_account_selection
        WHEN NOT EXISTS (
            SELECT 1 FROM tenant_identity_sessions
            WHERE token_hash=NEW.token_hash AND user_id=NEW.user_id
        )
        BEGIN SELECT RAISE(ABORT,'Session owner mismatch'); END;
        CREATE TRIGGER IF NOT EXISTS tenant_selection_session_owner_update
        BEFORE UPDATE ON tenant_session_account_selection
        WHEN NOT EXISTS (
            SELECT 1 FROM tenant_identity_sessions
            WHERE token_hash=NEW.token_hash AND user_id=NEW.user_id
        )
        BEGIN SELECT RAISE(ABORT,'Session owner mismatch'); END;
        """)


class DormantAccountGateway:
    """Session-authenticated account routing, without any live HTTP wiring.

    One user's multiple phone sessions select accounts independently.
    A session selection never changes legacy global account settings.
    """

    def __init__(self, path, identity_store):
        self.path = str(path)
        self.identity_store = identity_store
        self._accounts = account_scope.AccountScopeStore(path,identity_store)
        self._history = tenant_history.DormantHistoryReader(path,identity_store)
        self._details = tenant_history_details.DormantDetailsReader(path,identity_store)

    def _require_session(self, con, token, *, csrf=None, now=None):
        now = int(time.time() if now is None else now)
        token_hash = _hash_token(token)
        principal = self.identity_store.principal(token, csrf=csrf, now=now)
        if principal is None or not principal.get("user_id"):
            raise AccountSelectionError("Identity session unavailable")
        # Recheck the session against this transaction, including password
        # version / disable / expiry, so a stale selection cannot be reused.
        row=con.execute("""SELECT s.user_id,s.csrf_hash
            FROM tenant_identity_sessions s
            JOIN tenant_identities i ON i.user_id=s.user_id
            JOIN tenant_users u ON u.user_id=s.user_id
            WHERE s.token_hash=? AND s.expires_at>?
              AND s.credential_version=i.credential_version
              AND u.disabled_at IS NULL""",(token_hash,now)).fetchone()
        if not row or row["user_id"]!=principal["user_id"]:
            raise AccountSelectionError("Identity session unavailable")
        if csrf is not None:
            if not isinstance(csrf,str) or not hmac.compare_digest(
                row["csrf_hash"],hashlib.sha256(csrf.encode("utf-8")).hexdigest()):
                raise AccountSelectionError("Identity CSRF verification failed")
        return row["user_id"],token_hash

    def list_accounts(self, token):
        """Only explicitly active, verified-session-owned account metadata."""
        with account_scope._db(self.path) as con:
            user_id,_=self._require_session(con,token)
            return [dict(r) for r in con.execute("""SELECT a.account_id,a.label,a.provider
                FROM tenant_accounts a
                JOIN tenant_users u ON u.user_id=a.user_id
                JOIN tenant_connections c ON c.connection_id=a.connection_id
                  AND c.user_id=a.user_id
                WHERE a.user_id=? AND a.disabled_at IS NULL AND
                  u.disabled_at IS NULL AND c.revoked_at IS NULL
                ORDER BY a.created_at,a.account_id""",(user_id,))]

    def select_account(self, token, csrf, account_id):
        """Use identity CSRF token. Does not select any live broker account."""
        account_id = _require_identifier(account_id)
        if not isinstance(csrf,str):
            raise AccountSelectionError("Identity CSRF verification failed")
        with account_scope._db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            user_id,token_hash=self._require_session(con,token,csrf=csrf)
            account_scope.AccountScopeStore._check(con,user_id,account_id)
            con.execute("""INSERT INTO tenant_session_account_selection
                (token_hash,user_id,account_id,selected_at)
                VALUES(?,?,?,?)
                ON CONFLICT(token_hash) DO UPDATE
                SET user_id=excluded.user_id,account_id=excluded.account_id,
                    selected_at=excluded.selected_at""",
                (token_hash,user_id,account_id,int(time.time())))
        return {"selectedAccountId":account_id,"selectionIsSessionOnly":True,
                "legacyAccountUnchanged":True,"brokerRequestMade":False,
                "workerActivated":False,"canTrade":False}

    def selected_account(self, token):
        """No automatic fallback to first or globally selected account."""
        with account_scope._db(self.path) as con:
            user_id,token_hash=self._require_session(con,token)
            row=con.execute("""SELECT account_id FROM
                tenant_session_account_selection
                WHERE token_hash=? AND user_id=?""",
                (token_hash,user_id)).fetchone()
            if row is None:
                return None
            # Disabled account / revoked connection never results in stale
            # selection being returned, nor fallback to another account.
            account_scope.AccountScopeStore._check(con,user_id,row["account_id"])
            return row["account_id"]

    def clear_selection(self, token, csrf):
        if not isinstance(csrf,str):
            raise AccountSelectionError("Identity CSRF verification failed")
        with account_scope._db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            user_id,token_hash=self._require_session(con,token,csrf=csrf)
            con.execute("""DELETE FROM tenant_session_account_selection
                WHERE user_id=? AND token_hash=?""",(user_id,token_hash))
        return {"selectionCleared":True,"legacyAccountUnchanged":True}

    def account_summary(self, token, account_id):
        """Read explicitly specified account only after session/owner checks."""
        account_id=_require_identifier(account_id)
        with account_scope._db(self.path) as con:
            user_id,_=self._require_session(con,token)
            account_scope.AccountScopeStore._check(con,user_id,account_id)
        return self._accounts.account_summary(token,account_id)

    def selected_summary(self, token):
        account_id=self.selected_account(token)
        if account_id is None:
            raise AccountSelectionError("No account selected in this session")
        return self.account_summary(token,account_id)

    def history_summary(self, token, account_id):
        account_id=_require_identifier(account_id)
        with account_scope._db(self.path) as con:
            user_id,_=self._require_session(con,token)
            account_scope.AccountScopeStore._check(con,user_id,account_id)
        return self._history.summary(token,account_id)

    def selected_history_summary(self, token):
        account_id=self.selected_account(token)
        if account_id is None:
            raise AccountSelectionError("No account selected in this session")
        return self.history_summary(token,account_id)

    def details_summary(self, token, account_id):
        account_id=_require_identifier(account_id)
        with account_scope._db(self.path) as con:
            user_id,_=self._require_session(con,token)
            account_scope.AccountScopeStore._check(con,user_id,account_id)
        return self._details.summary(token,account_id)

    def page_history(self, token, account_id, *, before_id=None, limit=50):
        account_id=_require_identifier(account_id)
        with account_scope._db(self.path) as con:
            user_id,_=self._require_session(con,token)
            account_scope.AccountScopeStore._check(con,user_id,account_id)
        return self._history.page(token,account_id,before_id=before_id,limit=limit)

    def blocked_operation(self,*_args,**_kwargs):
        """Explicit no-trading fail closed for future misuse."""
        raise AccountSelectionError("Tenant execution and funds operations are disabled")
