"""Dormant, license-gated cache of non-personal market research features.

NOT an ingest API, a scheduler, a quote feed, a tenant entitlement service, or
an execution path. A trusted internal provider adapter must verify permissions
and timestamps BEFORE calling publish(). No network, AI, order or fund action.
A cached feature is not an executable quote or a trading recommendation.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import time
from datetime import datetime, timezone

from . import account_scope, identity_auth, research_intelligence as research

MAX_SIGNALS = 500
READABLE_ACCOUNT_ASSETS = frozenset(("stock", "etf"))


class SharedResearchDenied(PermissionError):
    """Same refusal for absent, revoked, foreign or out-of-scope accounts."""


def _db(path):
    con = sqlite3.connect(str(path), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=30000")
    return con


def _current(now):
    current = (datetime.now(timezone.utc) if now is None else
               research.utc_time(now, "now") if isinstance(now, str) else now)
    if (not isinstance(current, datetime) or current.tzinfo is None or
            current.utcoffset().total_seconds() != 0):
        raise research.ResearchUnavailable("Explicit UTC evaluation time required")
    return current


def _shareable_rights(value, *, provider=None):
    rights = research.ProviderRights.from_mapping(value)
    if not (rights.allowed_analysis and rights.allowed_cache and
            rights.allowed_redistribution and rights.verified_coverage):
        raise research.ResearchUnavailable("Provider rights do not allow shared research")
    if provider is not None and rights.provider != provider:
        raise research.ResearchUnavailable("Research provider rights changed")
    return rights


def _owner(con, token, csrf):
    """Recheck session and CSRF in the same SQLite transaction as account access."""
    if (not isinstance(token, str) or not 25 < len(token) < 256 or
            not isinstance(csrf, str) or not 20 < len(csrf) < 256):
        raise SharedResearchDenied("Research account unavailable")
    digest = lambda v: hashlib.sha256(v.encode("utf-8")).hexdigest()
    row = con.execute("""SELECT s.user_id,s.csrf_hash FROM tenant_identity_sessions s
        JOIN tenant_identities i ON i.user_id=s.user_id
        JOIN tenant_users u ON u.user_id=s.user_id
        WHERE s.token_hash=? AND s.expires_at>?
          AND s.credential_version=i.credential_version
          AND u.disabled_at IS NULL""",
                      (digest(token), int(time.time()))).fetchone()
    if row is None or not hmac.compare_digest(row["csrf_hash"], digest(csrf)):
        raise SharedResearchDenied("Research account unavailable")
    return row["user_id"]


def setup(path):
    """Additive, explicitly invoked schema; never initializes owner production."""
    with _db(path) as con:
        tables = {row["name"] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        needed = {"tenant_users", "tenant_connections", "tenant_accounts",
                  "tenant_identity_sessions", "tenant_identities",
                  "tenant_account_settings", "tenant_runtime_status"}
        if not needed.issubset(tables):
            raise RuntimeError("Independent tenant and identity schema required")
        con.execute("""CREATE TABLE IF NOT EXISTS shared_research_signals(
            provider TEXT NOT NULL,
            asset_class TEXT NOT NULL,
            symbol TEXT NOT NULL,
            observed_at REAL NOT NULL,
            received_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY(provider,asset_class,symbol)
        )""")
        con.execute("""CREATE INDEX IF NOT EXISTS idx_shared_research_expiry
            ON shared_research_signals(expires_at)""")


class SharedResearchCache:
    """Trusted internal research cache, never mounted as a public HTTP route.

    Only account-neutral features may be published. The cross-user read path
    still validates current rights, active identity, linked-account ownership,
    and each member's own account watchlist. No holdings or personal data are
    ever inserted into the shared table.
    """

    def __init__(self, path, identities):
        if (not isinstance(identities, identity_auth.IdentityStore) or
                str(path) != identities.path):
            raise ValueError("An independent identity store on the same DB is required")
        self.path = str(path)

    def publish(self, payload, *, now=None):
        """Compute only a public spread feature from an authorized observation.

        The calling provider adapter must make a fresh, independently verified
        rights/coverage assertion. Raw caller/user/account identifiers cannot
        be passed in the strictly validated observation schema.
        """
        current = _current(now)
        obs = research.Observation.validate(payload, now=current)
        _shareable_rights(payload["rights"], provider=obs.rights.provider)
        lifespan = research.DEFAULT_STALENESS_SECONDS[obs.asset_class]
        expiry = obs.observed_at.timestamp() + lifespan
        if current.timestamp() >= expiry:
            raise research.ResearchUnavailable("Research signal already expired")
        # Reference-only buy-side quoted spread; not a modeled fill or forecast.
        metric = (obs.ask - obs.bid) / obs.ask * 10000
        signal = {
            "schemaVersion": 1,
            "assetClass": obs.asset_class,
            "symbol": obs.symbol,
            "provider": obs.rights.provider,
            "observedAt": obs.observed_at.isoformat(),
            "receivedAt": obs.received_at.isoformat(),
            "expiresAt": datetime.fromtimestamp(expiry, timezone.utc).isoformat(),
            "feature": "quoted-spread-bps",
            "quotedSpreadBps": str(metric),
            "providerCoverageVerified": True,
            "redistributionAuthorizedAtInsert": True,
            "predictedProbability": None,
            "executableQuote": False,
            "orderAllowed": False,
            "aiCalls": 0,
        }
        with _db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("DELETE FROM shared_research_signals WHERE expires_at<=?",
                        (current.timestamp(),))
            con.execute("""INSERT INTO shared_research_signals
                (provider,asset_class,symbol,observed_at,received_at,
                 expires_at,payload_json)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(provider,asset_class,symbol) DO UPDATE SET
                    observed_at=excluded.observed_at,
                    received_at=excluded.received_at,
                    expires_at=excluded.expires_at,
                    payload_json=excluded.payload_json
                WHERE excluded.observed_at > shared_research_signals.observed_at
            """, (obs.rights.provider, obs.asset_class, obs.symbol,
                  obs.observed_at.timestamp(), obs.received_at.timestamp(),
                  expiry, json.dumps(signal, sort_keys=True, separators=(",", ":"))))
            # Bounded cache; chronological eviction limits retained entries.
            con.execute("""DELETE FROM shared_research_signals
                WHERE rowid IN (SELECT rowid FROM shared_research_signals
                ORDER BY observed_at DESC,provider,asset_class,symbol
                LIMIT -1 OFFSET ?)""", (MAX_SIGNALS,))
        return {"storedOrRefreshed": True, "publicOnly": True,
                "provider": obs.rights.provider, "assetClass": obs.asset_class,
                "symbol": obs.symbol, "providerRequestMade": False, "aiCalls": 0}

    def for_account(self, token, csrf, account_id, *, asset_class, symbol,
                    rights, now=None):
        """Account-specific authorization before reading one shared feature.

        Stock/ETF only until other categories have verified per-user rights.
        There are no active workers and no account-specific feature persistence.
        """
        current = _current(now)
        if (not isinstance(account_id, str) or not 1 <= len(account_id) <= 128 or
                type(asset_class) is not str or
                asset_class not in READABLE_ACCOUNT_ASSETS):
            raise SharedResearchDenied("Research account unavailable")
        try:
            trusted_rights = _shareable_rights(rights)
            symbol = research._text(symbol, "symbol", 96)
        except research.ResearchUnavailable:
            raise SharedResearchDenied("Research account unavailable") from None

        with _db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            uid = _owner(con, token, csrf)
            try:
                account_scope.AccountScopeStore._check(con, uid, account_id)
            except account_scope.TenantAccessError:
                raise SharedResearchDenied("Research account unavailable") from None
            state = con.execute("""SELECT requested_mode,worker_enabled,
                paper_enabled,live_enabled FROM tenant_runtime_status
                WHERE user_id=? AND account_id=?""", (uid, account_id)).fetchone()
            if state and (state["requested_mode"] != "observe" or
                          state["worker_enabled"] or state["paper_enabled"] or
                          state["live_enabled"]):
                raise SharedResearchDenied("Research account unavailable")
            setting = con.execute("""SELECT setting_value FROM tenant_account_settings
                WHERE user_id=? AND account_id=? AND setting_key='watchlist_csv'""",
                (uid, account_id)).fetchone()
            watchlist = (setting["setting_value"].split(",")
                         if setting and setting["setting_value"] else [])
            if symbol not in watchlist:
                raise SharedResearchDenied("Research account unavailable")
            row = con.execute("""SELECT payload_json FROM shared_research_signals
                WHERE provider=? AND asset_class=? AND symbol=?
                    AND observed_at<=? AND expires_at>?""",
                (trusted_rights.provider, asset_class, symbol,
                 current.timestamp(), current.timestamp())).fetchone()
            if row is None:
                raise SharedResearchDenied("Research evidence missing or expired")
            signal = json.loads(row["payload_json"])
        return {"signal": signal, "cacheHit": True,
                "readOnly": True, "sharedOnlyIfLicensed": True,
                "accountAuthorizationVerified": True,
                "brokerRequestMade": False, "aiCalls": 0,
                "liveTradingEnabled": False, "fundTransfersEnabled": False}

    def invalidate_provider(self, provider):
        """Trusted internal policy response when provider permissions are revoked."""
        research._text(provider, "provider")
        with _db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            return con.execute(
                "DELETE FROM shared_research_signals WHERE provider=?",
                (provider,)).rowcount
