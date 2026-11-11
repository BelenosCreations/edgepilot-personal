"""Dormant, explicitly NON-billing per-member commercial tier intent.

Separates untrusted requested tier labels from actual granted entitlements.
No subscription, paid access, AI allowance, provider credential, real
account, HTTP endpoint, trade or money movement can be activated here.
Future commercial terms and Play policy need independent authorization.
"""
from __future__ import annotations

import hashlib
import hmac
import sqlite3
import time

from . import identity_auth

TIER_CONCEPTS = frozenset(("free", "plus", "pro", "custom"))


class EntitlementDenied(PermissionError):
    """Do not reveal whether a foreign member identity exists."""


def _db(path):
    db = sqlite3.connect(str(path), timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=30000")
    return db


def setup(path):
    """Additive only; no production app initialization or tenant activation."""
    with _db(path) as con:
        present = {r["name"] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"tenant_users", "tenant_identities",
                "tenant_identity_sessions"}.issubset(present):
            raise RuntimeError("Verified independent identity schema required")
        con.execute("""CREATE TABLE IF NOT EXISTS tenant_tier_intents (
            user_id TEXT PRIMARY KEY REFERENCES tenant_users(user_id),
            requested_tier TEXT NOT NULL DEFAULT 'free'
                CHECK(requested_tier IN ('free','plus','pro','custom')),
            changed_at INTEGER NOT NULL
        )""")


def _member_in_lock(db, token, csrf):
    if (not isinstance(token, str) or not 25 < len(token) < 256 or
            not isinstance(csrf, str) or not 20 < len(csrf) < 256):
        raise EntitlementDenied("Member plan unavailable")
    hash_text = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()
    record = db.execute("""SELECT s.user_id,s.csrf_hash FROM
        tenant_identity_sessions s
        JOIN tenant_identities i ON i.user_id=s.user_id
        JOIN tenant_users u ON u.user_id=s.user_id
        WHERE s.token_hash=? AND s.expires_at>?
          AND s.credential_version=i.credential_version
          AND u.disabled_at IS NULL""",
        (hash_text(token), int(time.time()))).fetchone()
    if record is None or not hmac.compare_digest(
            record["csrf_hash"], hash_text(csrf)):
        raise EntitlementDenied("Member plan unavailable")
    return record["user_id"]


def _response(requested):
    """Never turn a selected label into paid access or owner-funded AI."""
    return {
        "requestedTierConcept": requested,
        "effectiveTier": "free",
        "tierActive": requested == "free",
        "premiumGrantVerified": False,
        "paymentAuthorizationRecorded": False,
        "subscriptionActive": False,
        "managedAiCreditsActive": False,
        "ownerFundedAiAllocationActive": False,
        "aiKeyOrBudgetChanged": False,
        "marketDataRightsChanged": False,
        "publicConnectionChanged": False,
        "realTradingPermissionsChanged": False,
        "commercialDistributionEnabled": False,
        "upgradeAvailableNow": False,
        "readOnlyPreview": True,
    }


class DormantTenantTierIntent:
    """Authenticated tenant-only preference, not a commercial plan manager."""

    def __init__(self, path, identities):
        if (not isinstance(identities, identity_auth.IdentityStore) or
                str(path) != identities.path):
            raise ValueError("Same independent identity database required")
        self.path = str(path)

    def status(self, token, csrf):
        with _db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            uid = _member_in_lock(con, token, csrf)
            row = con.execute("""SELECT requested_tier
                FROM tenant_tier_intents WHERE user_id=?""", (uid,)).fetchone()
            return _response(row["requested_tier"] if row else "free")

    def choose_for_future_review(self, token, csrf, requested_tier):
        """Never fetch a payment method, call billing or grant paid capacity."""
        if (type(requested_tier) is not str or
                requested_tier not in TIER_CONCEPTS):
            raise EntitlementDenied("Unapproved tier selection")
        with _db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            uid = _member_in_lock(con, token, csrf)
            con.execute("""INSERT INTO tenant_tier_intents
                (user_id,requested_tier,changed_at) VALUES(?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET
                    requested_tier=excluded.requested_tier,
                    changed_at=excluded.changed_at""",
                (uid, requested_tier, int(time.time())))
        return _response(requested_tier)

    def grant_paid_tier(self, *args, **kwargs):
        """Explicitly unavailable until an authorized, audited billing release."""
        raise EntitlementDenied("Paid subscriptions are not activated")
