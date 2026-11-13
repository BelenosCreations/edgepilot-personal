"""Exercise the read-only bridge with real identity sessions and fictional data."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

from cryptography.fernet import Fernet
from engine import identity_auth, tenant_foundation
from engine import tenant_paper_authenticated_preflight as preflight
from engine import tenant_paper_ledger as ledger


def evidence(bid="1.99", ask="2.00", *, age=2):
    now = datetime.now(timezone.utc)
    return {
        "assetClass": "stock", "symbol": "OFFLINE.TEST",
        "rights": {"provider": preflight.SYNTHETIC_PROVIDER, "analysis": True,
                   "cache": True, "redistribute": False, "coverageVerified": True},
        "observedAt": (now - timedelta(seconds=age)).isoformat(),
        "receivedAt": (now - timedelta(seconds=1)).isoformat(),
        "bid": bid, "ask": ask, "last": ask, "volume": "100", "state": "open",
    }


class AuthenticatedPaperPreflightTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir="/dev/shm")
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "fixture.db"
        preflight.create_fixture(self.path)
        self.fixture_vault_key = Fernet.generate_key()
        tenants = tenant_foundation.TenantStore(self.path, self.fixture_vault_key)
        self.auth = identity_auth.IdentityStore(self.path)
        self.owner, self.owner_conn, self.account, self.session = self.provision(
            tenants, "owner")
        self.member, self.member_conn, self.other, self.other_session = self.provision(
            tenants, "member")
        self.alternate = tenants.link_account(
            self.owner, self.owner_conn, "offline-owner-second", "Second")
        self.seed(self.owner, self.alternate)

    def provision(self, tenants, role):
        user = tenants.provision_user(role, role)
        connection = tenants.add_connection(user, "fixture-broker-placeholder-for-" + role)
        account = tenants.link_account(user, connection, "offline-" + role, role)
        password = "fixture-password-for-" + role
        self.auth.provision(user, role, password)
        session = self.auth.authenticate(role, password, role)
        self.seed(user, account)
        return user, connection, account, session

    def seed(self, user, account):
        ledger.open_wallet(self.path, principal_user_id=user, account_id=account,
                           initial_paper_cash="100.00")

    def params(self, **overrides):
        return {"account_id": self.account, "request_id": str(uuid.uuid4()),
                "side": "BUY", "observation": evidence(), "quantity": "0.5",
                "fee_per_unit": "0.02", "slippage_per_unit": "0.01",
                "protected_pct": "98.5", "spend_cap": "10", "per_trade_cap": "2",
                **overrides}

    def inspect(self, *, session=None, **params):
        session = self.session if session is None else session
        return preflight.inspect_fill(
            self.path, session_token=session["token"], csrf=session["csrf"],
            max_realized_loss="0.54", **params)

    def append(self, params):
        return ledger.record_paper_fill(self.path, principal_user_id=self.owner,
                                        now=datetime.now(timezone.utc), **params)

    def test_fractional_projection_matches_ledger_and_retry_scope(self):
        params = self.params()
        initial_bytes = self.path.read_bytes()
        projection = self.inspect(**params)
        self.assertEqual(self.path.read_bytes(), initial_bytes)
        self.assertEqual(projection["projectedBasisCents"], 102)
        self.assertEqual(projection["projectedQuantity"], "0.5")
        self.assertEqual(projection["projectedCashCents"], 9898)
        self.assertFalse(projection["assumedFillAuthorized"])
        self.assertFalse(projection["licensedObservationVerified"])
        self.assertEqual(self.append(params)["paperCash"], "98.98")

        retry = self.inspect(**params)
        self.assertTrue(retry["duplicate"])
        self.assertEqual(retry["originalCashAfterCents"], 9898)
        self.assertNotIn("projectedCashCents", retry)
        with self.assertRaises(preflight.PaperPreflightDenied):
            self.inspect(**{**params, "quantity": "0.50"})
        with self.assertRaises(preflight.PaperPreflightDenied):
            self.inspect(**self.params())  # Prior exposure consumes fractional cap.
        self.assertFalse(self.inspect(**{**params, "account_id": self.alternate})["duplicate"])
        self.assertFalse(self.inspect(session=self.other_session,
                                      **{**params, "account_id": self.other})["duplicate"])

    def test_historical_loss_survives_gains_and_existing_holdings_can_close(self):
        self.append(self.params(quantity="1", protected_pct="90", per_trade_cap="3"))
        losing = self.params(side="SELL", observation=evidence("0.99", "1.00"))
        # ceil(203 * .5) basis = 102, floor((.99 - .03) * .5 * 100) = 48.
        projected = self.inspect(**losing)
        self.assertEqual(projected["projectedRealizedCents"], -54)
        self.assertEqual(projected["projectedBasisCents"], 101)
        self.assertTrue(projected["projectedStopBreached"])
        self.append(losing)
        with self.assertRaises(preflight.PaperPreflightDenied):
            self.inspect(**self.params(protected_pct="90"))
        self.assertTrue(self.inspect(**losing)["duplicate"])
        profitable = self.params(side="SELL", observation=evidence("9", "9.01"),
                                 quantity="0.25")
        projected = self.inspect(**profitable)
        self.assertGreater(projected["projectedRealizedCents"], 0)
        self.assertTrue(projected["projectedStopBreached"])
        self.append(profitable)
        status = self.inspect(**self.params(side="SELL", quantity="0.25"))
        self.assertEqual(status["worstRealizedCents"], -54)
        self.assertTrue(status["historicalStopBreached"])
        self.assertEqual(status["projectedQuantity"], "0")
        self.assertEqual(status["projectedBasisCents"], 0)

    def test_identity_and_observation_fail_closed(self):
        params = self.params()
        for token, csrf, account in (
                (self.session["token"], None, self.account),
                (self.session["token"], self.other_session["csrf"], self.account),
                (self.other_session["token"], self.other_session["csrf"], self.account),
                (self.session["token"], self.session["csrf"], self.other)):
            with self.subTest(account=account), self.assertRaises(preflight.PaperPreflightDenied):
                self.inspect(session={"token": token, "csrf": csrf},
                             **{**params, "account_id": account})
        good = evidence()
        for bad in (evidence(age=3601), evidence(age=-5), {**good, "rights": {**good["rights"], "cache": False}},
                    {**good, "rights": {**good["rights"], "provider": "Public"}}):
            with self.assertRaises(preflight.PaperPreflightDenied):
                self.inspect(**{**params, "observation": bad})
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE tenant_users SET disabled_at='fixture' WHERE user_id=?",
                       (self.member,))
            db.execute("UPDATE tenant_accounts SET disabled_at='fixture' WHERE account_id=?",
                       (self.alternate,))
        for session, account in ((self.other_session, self.other), (self.session, self.alternate)):
            with self.assertRaises(preflight.PaperPreflightDenied):
                self.inspect(session=session, **{**params, "account_id": account})
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE tenant_identities SET credential_version=credential_version+1 "
                       "WHERE user_id=?", (self.owner,))
        with self.assertRaises(preflight.PaperPreflightDenied):
            self.inspect(**params)
        fresh_session = self.auth.authenticate("owner", "fixture-password-for-owner", "owner")
        self.assertFalse(self.inspect(session=fresh_session, **params)["duplicate"])
        self.auth.revoke(fresh_session["token"])
        with self.assertRaises(preflight.PaperPreflightDenied):
            self.inspect(session=fresh_session, **params)

    def test_revocation_committed_before_waiting_preflight_acquires_lock(self):
        ready = threading.Event()
        original = preflight.isolated._file

        def checked_file(path):
            resolved = original(path)
            ready.set()
            return resolved

        with ThreadPoolExecutor(max_workers=1) as pool, sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE tenant_connections SET revoked_at='fixture' WHERE connection_id=?",
                       (self.owner_conn,))
            with patch.object(preflight.isolated, "_file", side_effect=checked_file):
                pending = pool.submit(self.inspect, **self.params())
                self.assertTrue(ready.wait(timeout=5))
                self.assertFalse(pending.done())
                db.commit()
                with self.assertRaises(preflight.PaperPreflightDenied):
                    pending.result(timeout=5)
        self.assertEqual(ledger.snapshot(self.path, principal_user_id=self.member,
                                         account_id=self.other)["assumedFills"], 0)

    def test_interrupted_audit_rolls_back_and_releases_lock(self):
        params = self.params()
        before = self.path.read_bytes()
        with patch.object(preflight.recovery, "audit_tenant_paper_ledger",
                          side_effect=InterruptedError):
            with self.assertRaises(preflight.PaperPreflightDenied):
                self.inspect(**params)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.append(params)["paperCash"], "98.98")
        self.assertTrue(self.inspect(**params)["duplicate"])

    def test_unmarked_file_tamper_and_audit_failure_leave_no_changes(self):
        with self.assertRaises(FileExistsError):
            preflight.create_fixture(self.path)
        params = self.params()
        link = self.path.with_name("link.db")
        link.symlink_to(self.path)
        with self.assertRaises(preflight.PaperPreflightDenied):
            preflight.inspect_fill(
                link, session_token=self.session["token"], csrf=self.session["csrf"],
                max_realized_loss="0.54", **params)
        self.append(params)
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE tenant_paper_positions SET cost_basis_cents=0")
        before = self.path.read_bytes()
        with self.assertRaises(preflight.PaperPreflightDenied):
            self.inspect(**params)
        self.assertEqual(self.path.read_bytes(), before)
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TABLE offline_paper_preflight")
        with self.assertRaises(preflight.PaperPreflightDenied):
            self.inspect(**params)
