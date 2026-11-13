"""v0.2.88: tenant paper simulation is additive, idempotent and isolated."""
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from cryptography.fernet import Fernet

from engine import tenant_foundation
from engine import tenant_paper_ledger as paper


NOW = "2026-11-12T20:00:00Z"


def observation(asset="stock"):
    quote = {
        "assetClass": asset, "symbol": "TEST.1",
        "rights": {"provider": "SYNTHETIC_TEST_FEED", "analysis": True,
                   "cache": True, "redistribute": False,
                   "coverageVerified": True},
        "observedAt": "2026-11-12T19:59:55Z",
        "receivedAt": "2026-11-12T19:59:58Z",
        "bid": "1.99", "ask": "2.00", "last": "2.00",
        "volume": "100", "state": "open",
    }
    if asset == "prediction":
        quote.update({"bid": "0.48", "ask": "0.50", "last": "0.49",
                      "bookDepth": "100",
                      "expiresAt": "2026-11-12T20:15:00Z",
                      "settlementRules": "Synthetic settlement-only contract."})
    return quote


class TenantPaperLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "private-tenant.db")
        tenant_foundation.setup(self.path)
        store = tenant_foundation.TenantStore(
            self.path, credential_key=Fernet.generate_key().decode())
        self.owner = store.provision_user("Owner", role="owner")
        self.other = store.provision_user("Family", role="member")
        conn1 = store.add_connection(self.owner, "SYNTHETIC-OWNER-SECRET-12345678901")
        conn2 = store.add_connection(self.other, "SYNTHETIC-FAMILY-SECRET-1234567890")
        self.account = store.link_account(self.owner, conn1, "PAPER-OWNER-1", "Main")
        self.account_two = store.link_account(
            self.owner, conn1, "PAPER-OWNER-2", "Alternative")
        self.foreign = store.link_account(self.other, conn2, "PAPER-FAMILY-1", "Family")
        paper.prepare(self.path)
        paper.open_wallet(self.path, principal_user_id=self.owner,
                          account_id=self.account, initial_paper_cash="100.00")

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, *, user=None, account=None, request_id=None, side="BUY", **changes):
        params = {
            "principal_user_id": user or self.owner,
            "account_id": account or self.account,
            "request_id": request_id or str(uuid.uuid4()),
            "side": side, "observation": observation(), "now": NOW,
            "quantity": "2", "fee_per_unit": "0.02",
            "slippage_per_unit": "0.01", "protected_pct": "90",
            "spend_cap": "100", "per_trade_cap": "5",
        }
        params.update(changes)
        return paper.record_paper_fill(self.path, **params)

    def summary(self, user=None, account=None):
        return paper.snapshot(self.path,principal_user_id=user or self.owner,
                              account_id=account or self.account)

    def test_synthetic_buy_and_partial_full_sell_are_cash_conservative(self):
        first = self.record()
        self.assertTrue(first["paperOnly"])
        self.assertFalse(first["liveOrderSubmitted"])
        self.assertEqual(first["paperCash"], "95.94")
        current = self.summary()
        self.assertEqual(current["initialPaperCash"], "100.00")
        self.assertEqual(current["remainingPaperCash"], "95.94")
        self.assertEqual(current["assumedFills"], 1)
        self.assertEqual(current["positions"][0]["quantity"], "2")
        self.assertEqual(current["positions"][0]["costBasis"], "4.06")
        sell = self.record(side="SELL", quantity="1")
        self.assertEqual(sell["paperCash"], "97.90")
        self.assertEqual(sell["realizedPaperPnL"], "-0.07")
        self.assertEqual(self.summary()["positions"][0]["costBasis"], "2.03")
        self.record(side="SELL", quantity="1")
        done = self.summary()
        self.assertEqual(done["remainingPaperCash"], "99.86")
        self.assertEqual(done["positions"][0]["quantity"], "0")
        self.assertEqual(done["positions"][0]["realizedPaperPnL"], "-0.14")
        self.assertEqual(done["assumedFills"], 3)
        self.assertFalse(done["orderExecutionEnabled"])

    def test_retry_is_exactly_once_and_conflicting_request_fails_closed(self):
        request_id = str(uuid.uuid4())
        first = self.record(request_id=request_id)
        second = self.record(request_id=request_id)
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(second["paperCash"], "95.94")
        self.assertEqual(self.summary()["assumedFills"], 1)
        with self.assertRaises(paper.PaperLedgerDenied):
            self.record(request_id=request_id, quantity="3")
        self.assertEqual(self.summary()["remainingPaperCash"], "95.94")
        self.assertEqual(self.summary()["assumedFills"], 1)
        # An old idempotency key must return current cash, not mislabel
        # the original historical event balance after a later trade.
        self.record()
        later = self.record(request_id=request_id)
        self.assertEqual(later["paperCash"], "91.88")
        self.assertEqual(later["originalPaperCashAfter"], "95.94")
        self.assertEqual(self.summary()["assumedFills"], 2)

    def test_hard_protected_cash_and_per_trade_policy(self):
        self.record()
        self.record()
        self.assertEqual(self.summary()["remainingPaperCash"], "91.88")
        with self.assertRaises(paper.PaperLedgerDenied):
            self.record()
        self.assertEqual(self.summary()["assumedFills"], 2)
        for changes in [
            {"protected_pct": "100"},
            {"protected_pct": "99"},
            {"per_trade_cap": "1.00"},
            {"spend_cap": "0.01"},
            {"fee_per_unit": "-1"},
            {"slippage_per_unit": None},
            {"quantity": "0"},
            {"quantity": "0.0000000000000000001"},
            {"quantity": float("inf")},
        ]:
            with self.subTest(changes=changes):
                with self.assertRaises(paper.PaperLedgerDenied):
                    self.record(**changes)
        self.assertEqual(self.summary()["assumedFills"], 2)

    def test_no_short_selling_and_no_overstated_sale_proceeds(self):
        with self.assertRaises(paper.PaperLedgerDenied):
            self.record(side="SELL", quantity="1")
        self.record()
        for quantity in ("2.00001", "3", "-1"):
            with self.subTest(quantity=quantity):
                with self.assertRaises(paper.PaperLedgerDenied):
                    self.record(side="SELL", quantity=quantity)
        with self.assertRaises(paper.PaperLedgerDenied):
            self.record(side="SELL", fee_per_unit="5")
        extreme = observation()
        extreme.update({"bid": "999999999", "ask": "999999999",
                        "last": "999999999"})
        with self.assertRaises(paper.PaperLedgerDenied):
            self.record(side="SELL", observation=extreme)
        self.assertEqual(self.summary()["assumedFills"], 1)

    def test_market_licensing_freshness_status_and_contract_model(self):
        for quote, timestamp in [
            ({**observation(), "state": "halted"}, NOW),
            ({**observation(), "observedAt": "2026-11-12T19:55:00Z"}, NOW),
            ({**observation(), "rights": {
                **observation()["rights"], "analysis": False}}, NOW),
            ({**observation(), "rights": {
                **observation()["rights"], "cache": False}}, NOW),
            (observation("prediction"), NOW),
            (observation("crypto"), "2026-11-12T20:03:00Z"),
        ]:
            with self.subTest(quote=quote, timestamp=timestamp):
                with self.assertRaises(paper.PaperLedgerDenied):
                    self.record(observation=quote,now=timestamp)
        self.assertEqual(self.summary()["assumedFills"], 0)

    def test_multiple_members_accounts_and_revoke_are_separate(self):
        with self.assertRaises(paper.PaperLedgerDenied):
            self.summary(user=self.other)
        with self.assertRaises(paper.PaperLedgerDenied):
            self.record(user=self.other)
        paper.open_wallet(self.path, principal_user_id=self.other,
                          account_id=self.foreign, initial_paper_cash="40.00")
        paper.open_wallet(self.path, principal_user_id=self.owner,
                          account_id=self.account_two, initial_paper_cash="25.00")
        self.record()
        self.record(user=self.other,account=self.foreign,quantity="1")
        self.assertEqual(self.summary()["remainingPaperCash"], "95.94")
        self.assertEqual(self.summary(self.other,self.foreign)["remainingPaperCash"],
                         "37.97")
        self.assertEqual(self.summary(account=self.account_two)["remainingPaperCash"],
                         "25.00")
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE tenant_accounts SET disabled_at=? WHERE account_id=?",
                       (NOW,self.account))
        with self.assertRaises(paper.PaperLedgerDenied):
            self.summary()
        with self.assertRaises(paper.PaperLedgerDenied):
            self.record()
        self.assertEqual(self.summary(account=self.account_two)["assumedFills"], 0)

    def test_wallet_not_reseeded_and_paper_tables_not_in_legacy_db(self):
        self.assertFalse(paper.open_wallet(
            self.path, principal_user_id=self.owner,account_id=self.account,
            initial_paper_cash="100.00")["created"])
        for initial in ("100.001", "-3", "NaN", "500.00"):
            with self.subTest(initial=initial):
                with self.assertRaises(paper.PaperLedgerDenied):
                    paper.open_wallet(
                        self.path,principal_user_id=self.owner,
                        account_id=self.account,initial_paper_cash=initial)
        with sqlite3.connect(self.path) as db:
            tables={r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("tenant_paper_events",tables)
        self.assertIn("tenant_paper_positions",tables)
        self.assertNotIn("broker_fills",tables)
        app=(Path(__file__).resolve().parents[1]/"app.py").read_text()
        self.assertNotIn("tenant_paper_ledger", app)
        self.assertNotIn("/api/identity/paper/fill", app)


    def test_legacy_global_db_rejected_before_any_paper_table_is_added(self):
        legacy = str(Path(self.tmp.name) / "old-global.db")
        with sqlite3.connect(legacy) as db:
            db.execute("CREATE TABLE settings(k TEXT PRIMARY KEY, v TEXT)")
            db.execute("INSERT INTO settings VALUES('account_id','KEEP')")
        with self.assertRaises(paper.PaperLedgerDenied):
            paper.prepare(legacy)
        with sqlite3.connect(legacy) as db:
            names = {r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            preserved = db.execute(
                "SELECT v FROM settings WHERE k='account_id'").fetchone()[0]
        self.assertEqual(names, {"settings"})
        self.assertEqual(preserved, "KEEP")


if __name__=="__main__":
    unittest.main()
