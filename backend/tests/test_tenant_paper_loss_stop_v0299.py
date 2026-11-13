"""v0.2.99: offline-only tenant-scoped sticky realized paper loss research."""
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from cryptography.fernet import Fernet
from engine import tenant_foundation, tenant_paper_ledger as paper
from engine import tenant_paper_loss_stop as stop

NOW = "2026-11-12T20:00:00Z"


def quote(*, cheap=False):
    return {
        "assetClass": "stock", "symbol": "OFFLINE.TEST",
        "rights": {"provider": "SYNTHETIC-ONLY", "analysis": True,
                   "cache": True, "redistribute": False,
                   "coverageVerified": True},
        "observedAt": "2026-11-12T19:59:55Z",
        "receivedAt": "2026-11-12T19:59:58Z",
        "bid": "0.99" if cheap else "1.99",
        "ask": "1.00" if cheap else "2.00",
        "last": "1.00" if cheap else "2.00",
        "volume": "100", "state": "open",
    }


class OfflinePaperLossStopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(
            prefix="edgepilot-stop-v0299-", dir="/dev/shm")
        self.path = Path(self.tmp.name) / "fixture.db"
        tenant_foundation.setup(self.path)
        store = tenant_foundation.TenantStore(
            self.path, credential_key=Fernet.generate_key())
        self.owner = store.provision_user("Owner", "owner")
        self.member = store.provision_user("Family", "member")
        owner_connection = store.add_connection(
            self.owner, "SYNTHETIC-OWNER-NO-BROKER-123456789")
        member_connection = store.add_connection(
            self.member, "SYNTHETIC-FAMILY-NO-BROKER-123456789")
        self.primary = store.link_account(
            self.owner, owner_connection, "PAPER-OWNER-1", "Main")
        self.alternate = store.link_account(
            self.owner, owner_connection, "PAPER-OWNER-2", "Alt")
        self.foreign = store.link_account(
            self.member, member_connection, "PAPER-MEMBER", "Other")
        paper.prepare(self.path)
        for user, account, cash in (
            (self.owner, self.primary, "100.00"),
            (self.owner, self.alternate, "50.00"),
            (self.member, self.foreign, "25.00"),
        ):
            paper.open_wallet(self.path, principal_user_id=user,
                              account_id=account, initial_paper_cash=cash)

    def tearDown(self):
        self.tmp.cleanup()

    def fill(self, side, quantity, *, cheap=False, user=None, account=None):
        return paper.record_paper_fill(
            self.path, principal_user_id=user or self.owner,
            account_id=account or self.primary,
            request_id=str(uuid.uuid4()), side=side,
            observation=quote(cheap=cheap), now=NOW,
            quantity=quantity, fee_per_unit="0.02",
            slippage_per_unit="0.01", protected_pct="80",
            spend_cap="100", per_trade_cap="20")

    def inspect(self, limit="0.10", *, user=None, account=None, path=None):
        return stop.inspect_realized_paper_loss_stop(
            path or self.path, principal_user_id=user or self.owner,
            account_id=account or self.primary, max_realized_loss=limit)

    def test_sticky_historical_stop_does_not_reset_after_later_gain(self):
        self.fill("BUY", "2")
        before = self.inspect("0.01")
        self.assertEqual(before["worstHistoricalCumulativeRealizedPnL"], "0.00")
        self.assertFalse(before["historicalStopBreached"])
        self.fill("SELL", "1")
        first = self.inspect("0.07")
        self.assertEqual(first["currentCumulativeRealizedPnL"], "-0.07")
        self.assertEqual(first["worstHistoricalCumulativeRealizedPnL"], "-0.07")
        self.assertTrue(first["wouldBlockNewAssumedFills"])
        self.assertFalse(self.inspect("0.08")["historicalStopBreached"])
        self.fill("SELL", "1")
        second = self.inspect("0.10")
        self.assertEqual(second["worstHistoricalCumulativeRealizedPnL"], "-0.14")
        self.assertTrue(second["historicalStopBreached"])
        # The *dormant* fill writer is deliberately NOT connected to this
        # helper. Demonstrate a later winning synthetic sale cannot untrip
        # the history-derived status. This does NOT authorize production use.
        self.fill("BUY", "1", cheap=True)
        self.fill("SELL", "1")
        recovered = self.inspect("0.10")
        self.assertEqual(recovered["currentCumulativeRealizedPnL"], "0.79")
        self.assertEqual(recovered["worstHistoricalCumulativeRealizedPnL"], "-0.14")
        self.assertTrue(recovered["historicalStopBreached"])
        self.assertFalse(recovered["actualTradeAllowed"])
        self.assertFalse(recovered["assumedFillAuthorized"])

    def test_exact_limits_and_independent_account_identity(self):
        self.fill("BUY", "2")
        self.fill("SELL", "1")
        self.fill("BUY", "1", account=self.alternate)
        self.fill("BUY", "1", user=self.member, account=self.foreign)
        self.assertEqual(self.inspect("0.07")["assumedFillsReviewed"], 2)
        self.assertEqual(self.inspect("0.07", account=self.alternate)[
            "currentCumulativeRealizedPnL"], "0.00")
        self.assertEqual(self.inspect("0.07", user=self.member,
                                      account=self.foreign)[
            "currentCumulativeRealizedPnL"], "0.00")
        with self.assertRaises(stop.PaperLossStopDenied):
            self.inspect("0.07", user=self.member)
        with self.assertRaises(stop.PaperLossStopDenied):
            self.inspect("0.07", account=self.foreign)
        for limit in ("0", "0.001", "-1", "NaN", "Infinity",
                      "1000000001", "", None, True, 0.1):
            with self.subTest(limit=limit):
                with self.assertRaises(stop.PaperLossStopDenied):
                    self.inspect(limit)

    def test_audit_refuses_tampering_and_non_tmpfs_paths(self):
        self.fill("BUY", "2")
        self.fill("SELL", "1")
        with sqlite3.connect(self.path) as db:
            rowid, delta = db.execute("""SELECT rowid,signed_cash_change_cents
                FROM tenant_paper_events ORDER BY rowid LIMIT 1""").fetchone()
            db.execute("""UPDATE tenant_paper_events
                SET signed_cash_change_cents=? WHERE rowid=?""",
                (delta + 1, rowid))
        with self.assertRaises(stop.PaperLossStopDenied):
            self.inspect()
        with sqlite3.connect(self.path) as db:
            db.execute("""UPDATE tenant_paper_events
                SET signed_cash_change_cents=? WHERE rowid=?""",
                (delta, rowid))
        self.assertEqual(self.inspect()["assumedFillsReviewed"], 2)
        with tempfile.TemporaryDirectory() as outside:
            with self.assertRaises(stop.PaperLossStopDenied):
                self.inspect(path=Path(outside) / "not-a-synthetic-fixture.db")
        source = (Path(__file__).resolve().parents[1] / "app.py").read_text()
        self.assertNotIn("tenant_paper_loss_stop", source)
        self.assertNotIn("/api/identity/paper/loss-stop", source)


if __name__ == "__main__":
    unittest.main()
