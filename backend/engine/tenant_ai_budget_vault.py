"""Dormant per-member AI BYOK key vault and local budget accounting.

Does not contact AI providers, run jobs, spend funds, modify brokerage data,
or expose decrypted keys to HTTP clients. Future paid requests require
independent explicit consent, provider rights and an execution adapter.
Never falls back to the legacy owner's OPENAI_API_KEY or Public key.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING

from cryptography.fernet import Fernet, InvalidToken

from . import identity_auth, ai_analysis

class TenantAIDenied(PermissionError):
    """Generic errors intentionally do not reveal member or key existence."""


def _db(path):
    db = sqlite3.connect(str(path), timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=30000")
    return db


def setup(path):
    """Additive only, not auto-called by the legacy personal owner service."""
    with _db(path) as con:
        required = {"tenant_users", "tenant_identities",
                    "tenant_identity_sessions"}
        tables = {r["name"] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not required.issubset(tables):
            raise RuntimeError("Independent identity schema required")
        con.execute("""CREATE TABLE IF NOT EXISTS tenant_ai_profiles (
            user_id TEXT PRIMARY KEY REFERENCES tenant_users(user_id),
            mode TEXT NOT NULL DEFAULT 'none' CHECK(mode IN ('none','byok')),
            depth TEXT NOT NULL DEFAULT 'basic'
                CHECK(depth IN ('basic','balanced','deep')),
            monthly_budget_micro_usd INTEGER NOT NULL DEFAULT 0
                CHECK(monthly_budget_micro_usd BETWEEN 0 AND 1000000000),
            provider TEXT NOT NULL DEFAULT 'OpenAI' CHECK(provider='OpenAI'),
            key_ciphertext BLOB,
            key_version INTEGER NOT NULL DEFAULT 0 CHECK(key_version>=0),
            updated_at INTEGER NOT NULL,
            CHECK(mode='byok' OR key_ciphertext IS NULL)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS tenant_ai_reservations (
            request_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES tenant_ai_profiles(user_id),
            month TEXT NOT NULL,
            model TEXT NOT NULL,
            key_version INTEGER NOT NULL CHECK(key_version>=0),
            status TEXT NOT NULL CHECK(status IN ('reserved','complete','uncertain')),
            held_micro_usd INTEGER NOT NULL CHECK(held_micro_usd>=0),
            actual_micro_usd INTEGER CHECK(actual_micro_usd>=0),
            created_at INTEGER NOT NULL,
            settled_at INTEGER,
            FOREIGN KEY(user_id) REFERENCES tenant_users(user_id)
        )""")
        con.execute("""CREATE INDEX IF NOT EXISTS idx_tenant_ai_budget_owner_month
            ON tenant_ai_reservations(user_id,month,status)""")


def _now(now=None):
    if now is None:
        return datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise TenantAIDenied("UTC time required")
    return now.astimezone(timezone.utc)


def _budget(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or not 0 <= amount <= 1000:
            raise ValueError
        micros = amount * Decimal(1_000_000)
        if micros != micros.to_integral_value():
            raise ValueError
        return int(micros)
    except (ValueError, InvalidOperation, TypeError):
        raise TenantAIDenied("Monthly budget must be precise and nonnegative") from None


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _principal_in_lock(con, token, csrf):
    """Reverify active identity, revoked sessions and CSRF inside mutation lock."""
    if (not isinstance(token, str) or not 25 < len(token) < 256 or
            not isinstance(csrf, str) or not 20 < len(csrf) < 256):
        raise TenantAIDenied("Identity session unavailable")
    row = con.execute("""SELECT s.user_id,s.csrf_hash FROM tenant_identity_sessions s
        JOIN tenant_identities i ON i.user_id=s.user_id
        JOIN tenant_users u ON u.user_id=s.user_id
        WHERE s.token_hash=? AND s.expires_at>?
          AND s.credential_version=i.credential_version
          AND u.disabled_at IS NULL""", (_digest(token), int(time.time()))).fetchone()
    if not row or not hmac.compare_digest(row["csrf_hash"], _digest(csrf)):
        raise TenantAIDenied("Identity session unavailable")
    return row["user_id"]


def _active_profile(con, user):
    return con.execute("SELECT * FROM tenant_ai_profiles WHERE user_id=?",
                       (user,)).fetchone()


def _used(con, user, month):
    result = 0
    for r in con.execute("""SELECT status,held_micro_usd,actual_micro_usd
        FROM tenant_ai_reservations WHERE user_id=? AND month=?""", (user, month)):
        # Unknown cost holds retain the full reservation. If the trusted
        # usage fixture exceeds preflight, preserve the larger measured cost
        # while refusing to call the reservation a clean completion.
        actual = r["actual_micro_usd"]
        result += (int(actual) if r["status"] == "complete" and actual is not None
                   else max(int(r["held_micro_usd"]), int(actual or 0)))
    return result


class TenantAIBudgetVault:
    """Member-owned encrypted key and spending preferences; no provider calls."""

    def __init__(self, path, identities, *, credential_key):
        if not isinstance(identities, identity_auth.IdentityStore):
            raise TypeError("Independent identity store required")
        self.path = str(path)
        if identities.path != self.path:
            raise ValueError("AI vault and identity store must share tenant database")
        if not isinstance(credential_key, str):
            raise ValueError("Dedicated AI credential encryption key required")
        try:
            self.cipher = Fernet(credential_key.encode("ascii"))
        except (ValueError, TypeError):
            raise ValueError("Invalid AI-only encryption key") from None
        self.identities = identities

    def _read_user(self, token, csrf):
        principal = self.identities.principal(token, csrf)
        if principal is None:
            raise TenantAIDenied("Identity session unavailable")
        return principal["user_id"]

    def status(self, token, csrf, *, now=None):
        uid = self._read_user(token, csrf)
        month = _now(now).strftime("%Y-%m")
        with _db(self.path) as con:
            row = _active_profile(con, uid)
            used = _used(con, uid, month)
            pending = con.execute("""SELECT COUNT(*) FROM tenant_ai_reservations
                WHERE user_id=? AND month=? AND status IN ('reserved','uncertain')""",
                (uid, month)).fetchone()[0]
        budget = int(row["monthly_budget_micro_usd"]) if row else 0
        return {
            "mode": row["mode"] if row else "none",
            "analysisDepth": row["depth"] if row else "basic",
            "provider": "OpenAI",
            "monthlyBudgetMicroUsd": budget,
            "locallyCountedMicroUsd": used,
            "remainingMicroUsd": max(0, budget - used),
            "pendingOrUncertainCount": pending,
            "providerKeyConfigured": bool(row and row["key_ciphertext"]),
            "providerKeyReturned": False,
            "ownerKeyFallback": False,
            "managedBillingActivated": False,
            "providerBillingCapGuaranteed": False,
            "month": month,
        }

    def set_policy(self, token, csrf, *, mode, monthly_budget_usd, depth="basic"):
        if mode not in ("none", "byok") or depth not in (
                "basic", "balanced", "deep"):
            # Managed credits are expressly NOT enabled for this phase.
            raise TenantAIDenied("AI mode or analysis depth unavailable")
        budget = _budget(monthly_budget_usd)
        with _db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            uid = _principal_in_lock(con, token, csrf)
            existing = _active_profile(con, uid)
            if existing is None:
                con.execute("""INSERT INTO tenant_ai_profiles
                    (user_id,mode,depth,monthly_budget_micro_usd,updated_at)
                    VALUES(?,?,?,?,?)""",
                    (uid, mode, depth, budget, int(time.time())))
            else:
                # A reduced cap must never conceal outstanding reservations.
                used = _used(con, uid, _now().strftime("%Y-%m"))
                if mode == "byok" and budget < used:
                    raise TenantAIDenied("Budget below existing counted usage")
                con.execute("""UPDATE tenant_ai_profiles
                    SET mode=?,depth=?,monthly_budget_micro_usd=?,
                        key_ciphertext=CASE WHEN ?='none' THEN NULL ELSE key_ciphertext END,
                        key_version=key_version+CASE WHEN ?='none' THEN 1 ELSE 0 END,
                        updated_at=?
                    WHERE user_id=?""", (mode, depth, budget,
                                       mode, mode, int(time.time()), uid))
        return {"mode": mode, "analysisDepth": depth,
                "monthlyBudgetMicroUsd": budget,
                "providerKeyReturned": False,
                "managedBillingActivated": False}

    def put_key(self, token, csrf, secret, *, consent):
        if consent is not True or not isinstance(secret, str) or (
                not 20 <= len(secret) <= 256) or not secret.startswith("sk-") or (
                any(ord(c) < 33 or ord(c) > 126 for c in secret)):
            raise TenantAIDenied("Explicit consent and valid provider key required")
        # No persistent unencrypted copy, logging or echoed response.
        with _db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            uid = _principal_in_lock(con, token, csrf)
            row = _active_profile(con, uid)
            if not row or row["mode"] != "byok":
                raise TenantAIDenied("BYOK must be explicitly selected")
            sealed = self.cipher.encrypt(json.dumps({
                "owner": uid, "provider": "OpenAI", "secret": secret
            }, separators=(",", ":")).encode("utf-8"))
            con.execute("""UPDATE tenant_ai_profiles
                SET key_ciphertext=?,key_version=key_version+1,updated_at=?
                WHERE user_id=?""", (sealed, int(time.time()), uid))
        return {"providerKeyConfigured": True, "providerKeyReturned": False,
                "provider": "OpenAI", "verifiedWithProvider": False,
                "managedBillingActivated": False}

    def disconnect_key(self, token, csrf):
        with _db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            uid = _principal_in_lock(con, token, csrf)
            row = _active_profile(con, uid)
            if row is None:
                raise TenantAIDenied("AI provider connection unavailable")
            con.execute("""UPDATE tenant_ai_profiles
                SET key_ciphertext=NULL,mode='none',
                    monthly_budget_micro_usd=0,key_version=key_version+1,
                    updated_at=? WHERE user_id=?""", (int(time.time()), uid))
        return {"providerKeyConfigured": False, "mode": "none",
                "providerKeyReturned": False}

    def reserve_simulated(self, token, csrf, *, model,
                          input_tokens_bound, max_output_tokens, now=None):
        """Synthetic local admission only; NEVER calls a provider or bills anyone."""
        current = _now(now)
        try:
            charge = ai_analysis._charge_micro(
                input_tokens_bound, max_output_tokens, model, current)
        except ai_analysis.AIError:
            raise TenantAIDenied("Model pricing or budget unavailable") from None
        month = current.strftime("%Y-%m")
        with _db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            uid = _principal_in_lock(con, token, csrf)
            row = _active_profile(con, uid)
            if not row or row["mode"] != "byok" or not row["key_ciphertext"]:
                raise TenantAIDenied("Member-owned API billing not enabled")
            if charge + _used(con, uid, month) > row["monthly_budget_micro_usd"]:
                raise TenantAIDenied("Member monthly local budget unavailable")
            request_id = str(uuid.uuid4())
            con.execute("""INSERT INTO tenant_ai_reservations
                (request_id,user_id,month,model,key_version,status,
                 held_micro_usd,created_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                (request_id, uid, month, model, row["key_version"],
                 "reserved", charge, int(current.timestamp())))
        return {"requestId": request_id, "ownerScoped": True,
                "heldMicroUsd": charge, "paidRequestExecuted": False,
                "providerKeyReturned": False}

    def settle_simulated(self, token, csrf, request_id, *, input_tokens,
                         output_tokens, uncertain=False, now=None):
        """Reconcile a synthetic ledger fixture, not a provider invoice."""
        try:
            rid = str(uuid.UUID(request_id))
        except (ValueError, AttributeError, TypeError):
            raise TenantAIDenied("AI reservation unavailable") from None
        current = _now(now)
        with _db(self.path) as con:
            con.execute("BEGIN IMMEDIATE")
            uid = _principal_in_lock(con, token, csrf)
            row = con.execute("""SELECT model,status,held_micro_usd FROM tenant_ai_reservations
                WHERE request_id=? AND user_id=?""", (rid, uid)).fetchone()
            if row is None or row["status"] != "reserved":
                raise TenantAIDenied("AI reservation unavailable")
            if uncertain:
                cost = None
                state = "uncertain"
            else:
                try:
                    cost = ai_analysis._charge_micro(
                        input_tokens, output_tokens, row["model"], current)
                except ai_analysis.AIError:
                    raise TenantAIDenied("AI usage reconciliation unavailable") from None
                # Over-preflight usage cannot silently finalize below the
                # measured synthetic cost; hold the larger amount as uncertain.
                state = ("uncertain" if cost > row["held_micro_usd"]
                         else "complete")
            changed = con.execute("""UPDATE tenant_ai_reservations
                SET status=?,actual_micro_usd=?,settled_at=?
                WHERE request_id=? AND user_id=? AND status='reserved'""",
                (state, cost, int(current.timestamp()), rid, uid)).rowcount
            if changed != 1:
                raise TenantAIDenied("AI reservation unavailable")
        return {"state": state, "actualMicroUsd": cost,
                "overageDetected": cost is not None and
                                   cost > row["held_micro_usd"],
                "paidRequestExecuted": False,
                "providerBillingCapGuaranteed": False}
