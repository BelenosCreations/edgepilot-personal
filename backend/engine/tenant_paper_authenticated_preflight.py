"""Inactive, read-only Decimal paper integration for marked tmpfs fixtures."""
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
import hmac
import os
from pathlib import Path
import sqlite3
from urllib.parse import quote as url_quote

from . import identity_auth, shadow_storage, tenant_foundation
from . import tenant_paper_decimal_atomic_rehearsal as decimal_atomic
from . import tenant_paper_latch_rehearsal as isolated
from . import tenant_paper_ledger as ledger
from . import tenant_paper_loss_stop as loss_stop
from . import tenant_paper_recovery_audit as recovery

_MARKER = "EDGEPILOT-OFFLINE-AUTHENTICATED-PAPER-v1"
SYNTHETIC_PROVIDER = "SYNTHETIC_AUTHENTICATED_PAPER_FIXTURE"


class PaperPreflightDenied(ValueError):
    """Sanitized identity, fixture, observation or accounting refusal."""


def create_fixture(path):
    """Create a new synthetic tenant schema on verified tmpfs."""
    root = shadow_storage.memory_root()
    target = Path(path)
    parent = target.parent.resolve(strict=True)
    if parent != root and root not in parent.parents:
        raise PaperPreflightDenied("Offline paper fixture required")
    target = parent / target.name
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                 0o600)
    os.close(fd)
    try:
        tenant_foundation.setup(target)
        identity_auth.setup(target)
        ledger.prepare(target)
        with closing(tenant_foundation._open(target)) as db, db:
            db.execute("CREATE TABLE offline_paper_preflight (label TEXT PRIMARY KEY)")
            db.execute("INSERT INTO offline_paper_preflight VALUES (?)", (_MARKER,))
    except Exception:
        target.unlink()
        raise


def inspect_fill(path, *, session_token, csrf, account_id, request_id, side,
                 observation, quantity, fee_per_unit, slippage_per_unit,
                 protected_pct, spend_cap, per_trade_cap, max_realized_loss):
    """Evaluate a fictional proposal in a single transaction and always roll back.

    Identity comes from the existing server session tables. All policy arguments
    are hypothetical scenario inputs. No quote, token, or proposal is persisted.
    """
    denied = "Offline paper preflight unavailable"
    try:
        source = isolated._file(path)
        uri = "file:" + url_quote(str(source), safe="/") + "?mode=rw"
        with closing(sqlite3.connect(uri, uri=True, timeout=15)) as db:
            db.row_factory = sqlite3.Row
            if db.execute("PRAGMA journal_mode").fetchone()[0].lower() != "delete":
                raise PaperPreflightDenied(denied)
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("PRAGMA query_only=ON")
                marker = db.execute("SELECT label FROM offline_paper_preflight").fetchall()
                if [row["label"] for row in marker] != [_MARKER]:
                    raise PaperPreflightDenied(denied)
                now = datetime.now(timezone.utc)
                if not isinstance(csrf, str):
                    raise PaperPreflightDenied(denied)
                principal = identity_auth.IdentityStore._principal_in(
                    db, session_token, csrf=csrf, now=int(now.timestamp()))
                if principal is None:
                    raise PaperPreflightDenied(denied)
                user, account = ledger._scope(db, principal["user_id"], account_id)
                if db.execute("""SELECT 1 FROM tenant_paper_events
                    WHERE provider IS NOT ? LIMIT 1""", (SYNTHETIC_PROVIDER,)).fetchone():
                    raise PaperPreflightDenied(denied)
                verified = recovery.audit_tenant_paper_ledger(db)
                if not verified["paperSchemaPresent"]:
                    raise PaperPreflightDenied(denied)
                wallet = db.execute("""SELECT seeded_cents,cash_cents
                    FROM tenant_paper_wallets WHERE user_id=? AND account_id=?""",
                    (user, account)).fetchone()
                if wallet is None:
                    raise PaperPreflightDenied(denied)

                loss = loss_stop._stop_cents(max_realized_loss)
                events = db.execute("""SELECT side,asset_class,symbol,quantity,
                    signed_cash_change_cents FROM tenant_paper_events
                    WHERE user_id=? AND account_id=? ORDER BY rowid""", (user, account))
                realized, worst, _ = loss_stop._replay_realized(events)

                # Use the server clock after lock acquisition and historical replay.
                now = datetime.now(timezone.utc)
                if identity_auth.IdentityStore._principal_in(
                        db, session_token, csrf=csrf, now=int(now.timestamp())) is None:
                    raise PaperPreflightDenied(denied)
                key, quote, qty, fee, slip, pct, spend, trade, change, digest = (
                    ledger._prepare_fill(
                        request_id, side, observation, now, quantity, fee_per_unit,
                        slippage_per_unit, protected_pct, spend_cap, per_trade_cap))
                if quote.rights.provider != SYNTHETIC_PROVIDER:
                    raise PaperPreflightDenied(denied)
                prior = db.execute("""SELECT request_sha256,cash_after_cents
                    FROM tenant_paper_events
                    WHERE user_id=? AND account_id=? AND request_id=?""",
                    (user, account, key)).fetchone()
                cash = wallet["cash_cents"]
                result = {"paperOnly": True, "assumedFillAuthorized": False,
                          "licensedObservationVerified": False, "paperCashCents": cash,
                          "realizedCents": realized, "worstRealizedCents": worst,
                          "historicalStopBreached": worst <= -loss,
                          "duplicate": prior is not None}
                if prior is not None:
                    if not hmac.compare_digest(prior["request_sha256"], digest):
                        raise PaperPreflightDenied(denied)
                    return {**result, "originalCashAfterCents": prior["cash_after_cents"]}

                holdings = {
                    (row["asset_class"], row["symbol"]): (
                        row["quantity"], row["cost_basis_cents"], row["realized_cents"])
                    for row in db.execute("""SELECT asset_class,symbol,quantity,
                        cost_basis_cents,realized_cents FROM tenant_paper_positions
                        WHERE user_id=? AND account_id=?""", (user, account))
                }
                # Calculate the dormant ledger's exact cent cap once. Its
                # percentage can be fractional; the v0.2.106 fixture stores whole %.
                seed = wallet["seeded_cents"]
                protected_cap = ledger._cents((Decimal(seed) / 100) * (100 - pct) / 100)
                policy = {"seed": seed, "protected": 0, "loss": loss,
                          "spend": min(protected_cap, ledger._cents(spend)),
                          "trade": ledger._cents(trade)}
                price = quote.ask if side == "BUY" else quote.bid
                ledger._number(price, "synthetic unit price", positive=True)
                ledger._number(fee + slip, "synthetic friction")
                (projected_cash, projected_realized, projected_worst, stopped,
                 position, projected_change, _) = decimal_atomic._step(
                    policy, holdings, cash, realized, worst, result["historicalStopBreached"],
                    side, quote.asset_class, quote.symbol, qty, price, fee, slip)
                if projected_change != change:
                    raise PaperPreflightDenied(denied)
                return {**result, "projectedCashCents": projected_cash,
                        "projectedRealizedCents": projected_realized,
                        "projectedWorstRealizedCents": projected_worst,
                        "projectedStopBreached": bool(stopped),
                        "projectedQuantity": position[0], "projectedBasisCents": position[1]}
            finally:
                db.rollback()
    except (ValueError, TypeError, ArithmeticError, OSError, sqlite3.Error,
            shadow_storage.MemoryStorageError):
        raise PaperPreflightDenied(denied) from None
