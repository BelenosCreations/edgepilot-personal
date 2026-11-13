"""Manual Public quotes and price history for an authenticated linked account.

The route rechecks its sole-owner gate before and after each ephemeral read.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from contextlib import closing
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import requests

from . import owner_historical_bars, tenant_foundation, tenant_public_live_readonly as public

_TYPES = frozenset({"EQUITY", "CRYPTO"})
_SYMBOL = re.compile(r"^[A-Za-z0-9.^_-]{1,30}$")
_PRICE = re.compile(r"^(?:0|[1-9]\d{0,11})(?:\.\d{1,12})?$")


class OwnerQuoteUnavailable(RuntimeError):
    """Sanitized market-data or account denial."""


def _now(clock):
    when = clock()
    if not isinstance(when, datetime) or when.tzinfo is None:
        raise OwnerQuoteUnavailable("Verified UTC clock required")
    if when.utcoffset().total_seconds() != 0:
        raise OwnerQuoteUnavailable("Verified UTC clock required")
    return when.astimezone(timezone.utc)


def _timestamp(raw, received):
    if not isinstance(raw, str) or len(raw) > 40:
        raise OwnerQuoteUnavailable("Source timestamp unavailable")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise OwnerQuoteUnavailable("Source timestamp unavailable") from None
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise OwnerQuoteUnavailable("Source timestamp unavailable")
    parsed = parsed.astimezone(timezone.utc)
    # Never accept future timestamps, not even in a purported live quote.
    if parsed > received:
        raise OwnerQuoteUnavailable("Source timestamp unavailable")
    return parsed


def _price(raw):
    if not isinstance(raw, str) or not _PRICE.fullmatch(raw):
        raise OwnerQuoteUnavailable("Source price unavailable")
    try:
        value = Decimal(raw)
        if not value.is_finite() or value <= 0:
            raise InvalidOperation
        return str(value)
    except (InvalidOperation, ValueError):
        raise OwnerQuoteUnavailable("Source price unavailable") from None


def _entry(data, symbol, kind, received):
    quotes = data.get("quotes")
    if not isinstance(quotes, list) or len(quotes) != 1:
        raise OwnerQuoteUnavailable("Matching source quote unavailable")
    row = quotes[0]
    if not isinstance(row, dict) or row.get("outcome") != "SUCCESS":
        raise OwnerQuoteUnavailable("Matching source quote unavailable")
    instrument = row.get("instrument")
    if (not isinstance(instrument, dict) or instrument.get("symbol") != symbol
            or instrument.get("type") != kind):
        raise OwnerQuoteUnavailable("Matching source quote unavailable")
    last = _price(row.get("last"))
    last_at = _timestamp(row.get("lastTimestamp"), received)
    bid = ask = None
    bid_at = ask_at = None
    # Do not substitute midpoint/last for missing bid or ask.
    for side in ("bid", "ask"):
        if row.get(side) is not None:
            p = _price(row[side])
            # Public documents some quote samples without bid/ask timestamp.
            # Price remains source-reported, but never gains a freshness claim.
            raw_side_time = row.get(side + "Timestamp")
            at = (_timestamp(raw_side_time, received)
                  if raw_side_time is not None else None)
            if side == "bid":
                bid, bid_at = p, at
            else:
                ask, ask_at = p, at
    if bid is not None and ask is not None and Decimal(bid) > Decimal(ask):
        raise OwnerQuoteUnavailable("Crossed source quote refused")
    ages = [(received - when).total_seconds() for when in (last_at, bid_at, ask_at)
            if when is not None]
    freshness = 45 if kind == "CRYPTO" else 120
    last_fresh = (received-last_at).total_seconds() <= freshness
    both_fresh = (
        bid is not None and ask is not None and bid_at is not None
        and ask_at is not None and
        (received-bid_at).total_seconds() <= freshness and
        (received-ask_at).total_seconds() <= freshness
    )
    return {
        "assetClass": kind, "symbol": symbol,
        "provider": "Public API", "sourcePath": "marketdata quotes",
        "last": last, "lastTimestamp": last_at.isoformat(),
        "bid": bid, "bidTimestamp": bid_at.isoformat() if bid_at else None,
        "ask": ask, "askTimestamp": ask_at.isoformat() if ask_at else None,
        "receivedAt": received.isoformat(),
        "lastFresh": last_fresh, "twoSidedFresh": both_fresh,
        "freshnessWindowSeconds": freshness,
        "sourceReportedOnly": True,
        "readOnly": True, "cacheRightsVerified": False,
        "paperFillEligible": False, "executable": False,
        "ordersEnabled": False, "transfersEnabled": False,
        "warning": "Provider-reported research only. Quote age and market availability can change; not a broker execution price or performance record.",
    }


OWNER_HISTORY_PERIODS = frozenset(("WEEK", "MONTH"))
_MAX_HISTORY_BYTES = 4 * 1024 * 1024


class OwnerMarketQuotes:
    def __init__(self, reader, *, clock=None):
        if not isinstance(reader, public.TenantPublicReadOnly):
            raise TypeError("Verified tenant read-only Public adapter required")
        self.reader = reader
        self.clock = clock if clock is not None else lambda: datetime.now(timezone.utc)

    def one(self, identity_token, internal_account_id, *, symbol, instrument_type):
        if (not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol)
                or not isinstance(instrument_type, str)
                or instrument_type not in _TYPES):
            raise OwnerQuoteUnavailable("Choose a supported Public symbol and type")

        def fetch(reader, token, provider_id):
            response = reader.http.post(
                public.BASE + "/userapigateway/marketdata/" +
                quote(provider_id, safe="") + "/quotes",
                json={"instruments":[{"symbol":symbol,"type":instrument_type}]},
                headers={"Authorization":"Bearer "+token,
                         "Accept":"application/json",
                         "Content-Type":"application/json"},
                timeout=public.TIMEOUT,
            )
            return reader._get_json(response)

        def normalize(payload, received):
            return _entry(payload, symbol, instrument_type, received)

        return self._scoped_read(identity_token, internal_account_id, fetch, normalize)

    def history(self, identity_token, internal_account_id, *, symbol, instrument_type, period):
        if (not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol)
                or not isinstance(instrument_type, str) or instrument_type not in _TYPES
                or not isinstance(period, str) or period not in OWNER_HISTORY_PERIODS):
            raise OwnerQuoteUnavailable("Choose a supported Public symbol and period")

        def fetch(reader, token, _provider_id):
            endpoint = "/userapigateway/historicdata/{}/{}/{}".format(
                instrument_type, quote(symbol, safe=""), period)
            # Public's historical endpoint is token-scoped and has no
            # account parameter. The selected local link is verified separately.
            if instrument_type == "EQUITY" and period == "WEEK":
                endpoint += "?tradingSessionToggle=REGULAR_HOURS"
            with closing(reader.http.get(
                    public.BASE + endpoint,
                    headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                    timeout=public.TIMEOUT, allow_redirects=False, stream=True)) as response:
                if response.status_code != 200:
                    raise OwnerQuoteUnavailable("Verified Public history unavailable")
                payload = bytearray()
                for chunk in response.iter_content(chunk_size=65536):
                    if len(payload) + len(chunk) > _MAX_HISTORY_BYTES:
                        raise OwnerQuoteUnavailable("Verified Public history unavailable")
                    payload.extend(chunk)
            # Keep fractional crypto volume exact when Public sends JSON numbers.
            return json.loads(payload, parse_float=Decimal)

        def normalize(payload, received):
            checked = owner_historical_bars.normalize_bars(
                payload, symbol=symbol, instrument_type=instrument_type,
                period=period, received_at=received)
            return {
                "provider": "Public API", "source": "Get bars v2",
                "symbol": symbol, "assetClass": instrument_type, "period": period,
                "receivedAt": checked["observedAt"], "barCount": checked["barCount"],
                "sourceExpectedBars": checked["sourceExpectedBars"],
                "bars": checked["bars"], "readOnly": True, "dataPersisted": False,
                "ordersEnabled": False, "transfersEnabled": False,
                "paperFillEligible": False,
            }

        return self._scoped_read(identity_token, internal_account_id, fetch, normalize)

    def _scoped_read(self, identity_token, internal_account_id, fetch, normalize):
        reader = self.reader
        try:
            owner = reader._principal(identity_token)
            account_uuid = public.tenant_public_vault._uuid(internal_account_id)
            with tenant_foundation._open(reader.path) as db:
                row = db.execute("""SELECT a.provider_account_ref,a.connection_id
                    FROM tenant_accounts a JOIN tenant_connections c
                      ON c.connection_id=a.connection_id AND c.user_id=a.user_id
                    JOIN tenant_users u ON u.user_id=a.user_id
                    WHERE a.user_id=? AND a.account_id=? AND a.disabled_at IS NULL
                      AND c.revoked_at IS NULL AND u.disabled_at IS NULL
                      AND a.provider='public' AND c.provider='public'""",
                    (owner, account_uuid)).fetchone()
            if row is None:
                raise OwnerQuoteUnavailable("Linked account unavailable")
            connection = row["connection_id"]
            provider_id = public._safe_id(row["provider_account_ref"])
            prior = reader._credential_fingerprint(owner, connection)
            reader._admit(owner, connection)
            token = reader._token(identity_token, connection)
            if provider_id not in {a["accountId"] for a in reader._accounts(token)}:
                raise OwnerQuoteUnavailable("Linked account unavailable")
            payload = fetch(reader, token, provider_id)
            received = _now(self.clock)
            observation = normalize(payload, received)
            if reader._principal(identity_token) != owner:
                raise OwnerQuoteUnavailable("Session changed")
            with tenant_foundation._open(reader.path) as db:
                still = db.execute("""SELECT c.credential_ciphertext
                    FROM tenant_accounts a JOIN tenant_connections c
                      ON c.connection_id=a.connection_id AND c.user_id=a.user_id
                    JOIN tenant_users u ON u.user_id=a.user_id
                    WHERE a.user_id=? AND a.account_id=? AND
                      a.connection_id=? AND a.provider_account_ref=? AND
                      a.provider='public' AND c.provider='public' AND
                      a.disabled_at IS NULL AND c.revoked_at IS NULL AND
                      u.disabled_at IS NULL""",
                    (owner, account_uuid, connection, provider_id)).fetchone()
            if still is None or not hmac.compare_digest(
                hashlib.sha256(bytes(still["credential_ciphertext"])).digest(),
                prior,
            ):
                raise OwnerQuoteUnavailable("Account binding changed")
            return {"accountId":account_uuid, **observation}
        except OwnerQuoteUnavailable:
            raise
        except (public.PublicReadUnavailable, public.tenant_public_vault.TenantVaultDenied,
                requests.RequestException, ValueError, TypeError, KeyError, RecursionError):
            raise OwnerQuoteUnavailable("Verified Public market data unavailable") from None
