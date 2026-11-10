"""Identity-scoped, non-executing tenant watchlist editing.

Only an authenticated EdgePilot principal may replace the watchlist of a
linked account they own. Edits do NOT start market scans, broker calls,
paper trading, live trading, or the legacy single-owner worker.
"""
from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
import uuid

from . import account_scope, tenant_monitor_blueprint


class WatchlistDenied(PermissionError):
    """Deliberately uniform denial for missing, revoked, or foreign accounts."""


class WatchlistInvalid(ValueError):
    """Invalid nonsecret symbol list; never echo raw caller input."""


def _uuid(value):
    if not isinstance(value, str):
        raise WatchlistDenied("Account unavailable")
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError("Noncanonical account identifier")
    except ValueError:
        raise WatchlistDenied("Account unavailable") from None
    return value


def _symbols(values):
    if type(values) is not list or len(values) > tenant_monitor_blueprint._MAX_WATCHLIST:
        raise WatchlistInvalid("Invalid watchlist")
    normalized = []
    for value in values:
        if (not isinstance(value, str) or
                tenant_monitor_blueprint._SYMBOL.fullmatch(value) is None or
                value in normalized):
            raise WatchlistInvalid("Invalid watchlist")
        normalized.append(value)
    if len(",".join(normalized)) > 512:
        raise WatchlistInvalid("Invalid watchlist")
    return normalized


class TenantWatchlistEditor:
    """Transaction-bound authorization for owner-only, inactive settings."""

    def __init__(self, path, identity_store):
        self.path = str(path)
        self.identity_store = identity_store

    def replace(self, identity_token, csrf, account_id, symbols):
        account_id = _uuid(account_id)
        accepted = _symbols(symbols)
        try:
            with account_scope._db(self.path) as db:
                # Recheck live session, user and connection after acquiring
                # the write lock. A concurrent logout/revoke serializes here.
                db.execute("BEGIN IMMEDIATE")
                principal = self.identity_store.principal(identity_token, csrf)
                if principal is None:
                    raise WatchlistDenied("Account unavailable")
                user_id = principal["user_id"]
                try:
                    account_scope.AccountScopeStore._check(db, user_id, account_id)
                except account_scope.TenantAccessError:
                    raise WatchlistDenied("Account unavailable") from None
                state = db.execute("""SELECT requested_mode,worker_enabled,
                    paper_enabled,live_enabled FROM tenant_runtime_status
                    WHERE user_id=? AND account_id=?""",
                    (user_id, account_id)).fetchone()
                if state and (state["requested_mode"] != "observe" or
                              state["worker_enabled"] or state["paper_enabled"] or
                              state["live_enabled"]):
                    raise WatchlistDenied("Account unavailable")
                db.execute("""INSERT INTO tenant_account_settings
                    (account_id,user_id,setting_key,setting_value)
                    VALUES(?,?,'watchlist_csv',?)
                    ON CONFLICT(account_id,user_id,setting_key)
                    DO UPDATE SET setting_value=excluded.setting_value""",
                    (account_id, user_id, ",".join(accepted)))
                db.execute("""INSERT INTO tenant_audit_events
                    (created_at,user_id,account_id,action)
                    VALUES(?,?,?,'ACCOUNT_SETTING_CHANGED')""",
                    (datetime.now(timezone.utc).isoformat(), user_id, account_id))
        except sqlite3.Error:
            raise WatchlistDenied("Account unavailable") from None
        return {
            "accountId": account_id,
            "watchlist": accepted,
            "saved": True,
            "readOnlyMonitoring": True,
            "workerActive": False,
            "brokerRequestsAllowed": False,
            "paperEnabled": False,
            "liveTradingEnabled": False,
            "fundTransfersEnabled": False,
        }
