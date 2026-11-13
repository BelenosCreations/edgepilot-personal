"""v0.2.105 — synthetic-only atomic paper fill / realized stop integration.

These are fabricated cents and whole-unit positions; no market observations,
brokerage connectivity, real user accounts or licensed quote storage.
"""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
import uuid

from engine import tenant_paper_atomic_rehearsal as atomic


def ident():
    return str(uuid.uuid4())


class OfflineAtomicPaperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(
            dir="/dev/shm",prefix="edgepilot-atomic-paper-v02105-")
        self.root = Path(self.temp.name)
        self.path = self.root / "fixture.db"
        self.old_snapshot = self.root / "prior.db"
        self.key, self.anchor = os.urandom(32), os.urandom(32)
        self.u1,self.u2 = ident(), ident()
        self.a1,self.a2,self.a3 = ident(),ident(),ident()
        atomic.create_synthetic_atomic_fixture(self.path)
        self.register(self.u1,self.a1)
        self.register(self.u1,self.a2)
        self.register(self.u2,self.a3)

    def tearDown(self):
        self.temp.cleanup()

    def register(self, user, account, *, seed=10000, protected=90,
                 spend=2000, trade=800, stop=14, key=None):
        return atomic.register_synthetic_atomic_account(
            self.path,hmac_key=key or self.key,
            principal_user_id=user,account_id=account,
            initial_cash_cents=seed,protected_pct=protected,
            spend_cap_cents=spend,per_trade_cap_cents=trade,
            max_loss_cents=stop)

    def fill(self, side="BUY", *, user=None, account=None, request=None,
             asset="stock", symbol="TEST", quantity=2, price=200, fee=6,
             fail=False, key=None):
        return atomic.rehearse_synthetic_atomic_fill(
            self.path,hmac_key=key or self.key,
            principal_user_id=user or self.u1,
            account_id=account or self.a1,request_id=request or ident(),
            side=side,asset_class=asset,symbol=symbol,
            quantity_units=quantity,unit_price_cents=price,fee_cents=fee,
            _fail_before_commit=fail)

    def state(self, *, user=None, account=None, key=None):
        return atomic.inspect_synthetic_atomic_account(
            self.path,hmac_key=key or self.key,
            principal_user_id=user or self.u1,account_id=account or self.a1)

    def pin(self):
        return atomic.make_synthetic_atomic_checkpoint(
            self.path,hmac_key=self.key,anchor_key=self.anchor,epoch=1)

    def verify(self, pin=None, *, path=None, key=None, anchor=None):
        return atomic.verify_synthetic_atomic_checkpoint(
            path or self.path,hmac_key=key or self.key,
            anchor_key=anchor or self.anchor,
            externally_trusted_checkpoint=pin or self.pin())

    def test_single_transaction_cost_basis_and_sticky_loss_stop(self):
        self.assertEqual(self.fill()["cashCents"],9594)
        self.assertEqual(self.fill(symbol="SPARE",quantity=1,price=100,fee=0)[
            "cashCents"],9494)
        self.assertEqual(self.fill("SELL",quantity=1,price=199,fee=3)[
            "realizedDeltaCents"],-7)
        result=self.fill("SELL",quantity=1,price=199,fee=3)
        self.assertEqual(result["realizedCents"],-14)
        self.assertEqual(result["worstRealizedCents"],-14)
        self.assertTrue(result["stopped"])
        self.assertEqual(self.state()["cashCents"],9886)
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.fill(quantity=1,price=100,fee=0)
        # Existing assumed positions can still be liquidated while stopped.
        gain=self.fill("SELL",symbol="SPARE",quantity=1,price=200,fee=0)
        self.assertEqual(gain["realizedCents"],86)
        self.assertEqual(gain["worstRealizedCents"],-14)
        self.assertTrue(gain["stopped"])
        snapshot=self.state()
        self.assertEqual(snapshot["assumedFillCount"],5)
        self.assertEqual(snapshot["positions"],
                         [["stock","SPARE",0,0,100],
                          ["stock","TEST",0,0,-14]])
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.fill(quantity=1,price=100,fee=0)

    def test_idempotency_conflict_and_later_historical_balance(self):
        req=ident()
        first=self.fill(request=req)
        retry=self.fill(request=req)
        self.assertFalse(first["duplicate"])
        self.assertTrue(retry["duplicate"])
        self.assertEqual(retry["originalCashAfterCents"],9594)
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.fill(request=req,quantity=1)
        self.fill(quantity=1,price=100,fee=0)
        later=self.fill(request=req)
        self.assertTrue(later["duplicate"])
        self.assertEqual(later["cashCents"],9494)
        self.assertEqual(later["originalCashAfterCents"],9594)
        self.assertEqual(self.state()["assumedFillCount"],2)

    def test_protected_budget_trade_limit_and_no_short_sell(self):
        self.fill()
        self.fill()
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.fill()
        self.assertEqual(self.state()["cashCents"],9188)
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.fill("SELL",quantity=6)
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.fill(quantity=4,price=200,fee=0)
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.fill(symbol="OUTSIDE",quantity=1,price=100,fee=0,
                      account=self.a2,key=os.urandom(32))
        self.assertEqual(self.state()["assumedFillCount"],2)
        self.assertEqual(self.state(account=self.a2)["cashCents"],10000)
        self.assertEqual(self.state(account=self.a3,user=self.u2)[
            "cashCents"],10000)

    def test_cross_user_and_account_isolation(self):
        self.fill()
        self.fill(user=self.u2,account=self.a3,asset="crypto",
                  symbol="BTC",quantity=1,price=300,fee=0)
        self.assertEqual(self.state()["cashCents"],9594)
        self.assertEqual(self.state(account=self.a2)["cashCents"],10000)
        self.assertEqual(self.state(user=self.u2,account=self.a3)[
            "cashCents"],9700)
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.state(user=self.u2,account=self.a1)
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.state(user=self.u1,account=self.a3)
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.fill(user=self.u2,account=self.a1)
        self.assertEqual(self.state()["assumedFillCount"],1)

    def test_transaction_abort_retains_cash_basis_stop_and_request(self):
        saved=self.pin()
        request=ident()
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.fill(request=request,fail=True)
        self.assertEqual(self.state()["assumedFillCount"],0)
        self.assertTrue(self.verify(saved)["checkpointVerified"])
        succeeded=self.fill(request=request)
        self.assertFalse(succeeded["duplicate"])
        self.assertEqual(self.state()["assumedFillCount"],1)
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.verify(saved)

    def test_concurrent_distinct_requests_cannot_overspend(self):
        def make_buy(_):
            try:
                self.fill(quantity=1,price=200,fee=0)
                return True
            except atomic.AtomicPaperDenied:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(make_buy,range(12)))
        self.assertEqual(sum(results),5)
        self.assertEqual(self.state()["assumedFillCount"],5)
        self.assertEqual(self.state()["cashCents"],9000)
        self.assertEqual(self.state()["positions"][0],
                         ["stock","TEST",5,1000,0])

    def test_concurrent_same_request_commits_only_once(self):
        req=ident()
        def once(_):
            return self.fill(request=req,quantity=1,price=200,fee=0)
        with ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(once,range(10)))
        self.assertEqual(sum(not r["duplicate"] for r in results),1)
        self.assertEqual(self.state()["assumedFillCount"],1)
        self.assertEqual(self.state()["cashCents"],9800)

    def test_stale_whole_fixture_and_tampered_state_are_refused(self):
        before=self.pin()
        shutil.copy2(self.path,self.old_snapshot)
        self.fill()
        latest=self.pin()
        self.assertTrue(self.verify(latest)["checkpointVerified"])
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.verify(latest,path=self.old_snapshot)
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.verify(before)
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.verify(latest,anchor=os.urandom(32))
        # An old pin is valid ONLY if independently retained as the latest;
        # the module cannot detect rollback of both disk and external pin.
        self.assertTrue(self.verify(before,path=self.old_snapshot)[
            "checkpointVerified"])
        with sqlite3.connect(self.path) as db:
            db.execute("""UPDATE offline_atomic_positions SET basis_cents=1
                WHERE user_id=? AND account_id=?""",(self.u1,self.a1))
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.state()
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.pin()

    def test_tampered_journal_and_missing_account_refused(self):
        self.fill()
        original=self.pin()
        with sqlite3.connect(self.path) as db:
            db.execute("""UPDATE offline_atomic_events SET fee_cents=4
                WHERE user_id=? AND account_id=?""",(self.u1,self.a1))
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.state()
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.verify(original)
        with sqlite3.connect(self.path) as db:
            db.execute("""UPDATE offline_atomic_events SET fee_cents=6
                WHERE user_id=? AND account_id=?""",(self.u1,self.a1))
            db.execute("""DELETE FROM offline_atomic_wallets
                WHERE user_id=? AND account_id=?""",(self.u2,self.a3))
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.verify(original)
        self.assertEqual(self.state()["assumedFillCount"],1)

    def test_reseed_policy_change_invalid_inputs_and_key_refusal(self):
        self.assertFalse(self.register(self.u1,self.a1)["registered"])
        for kwargs in ({"seed":20000},{"protected":99},{"stop":30}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(atomic.AtomicPaperDenied):
                    self.register(self.u1,self.a1,**kwargs)
        for kwargs in (
            {"side":"OPEN"}, {"asset":"prediction"}, {"symbol":"bad"},
            {"quantity":0},{"quantity":True},{"price":0},{"fee":-1},
            {"quantity":10000001},{"price":100000000000},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(atomic.AtomicPaperDenied):
                    self.fill(**kwargs)
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.state(key=os.urandom(32))
        with self.assertRaises(atomic.AtomicPaperDenied):
            self.fill("SELL")
        self.assertEqual(self.state()["assumedFillCount"],0)

    def test_tmpfs_only_no_production_imports_or_migrations(self):
        root=Path(__file__).resolve().parents[1]
        for filename in ("app.py","engine/tenant_paper_ledger.py",
                         "engine/tenant_paper_latch_rehearsal.py"):
            content=(root/filename).read_text()
            self.assertNotIn("tenant_paper_atomic_rehearsal",content)
        with tempfile.TemporaryDirectory() as disk:
            with self.assertRaises(atomic.AtomicPaperDenied):
                atomic.create_synthetic_atomic_fixture(Path(disk)/"unsafe.db")
            with self.assertRaises(atomic.AtomicPaperDenied):
                atomic.inspect_synthetic_atomic_account(
                    Path(disk)/"unsafe.db",hmac_key=self.key,
                    principal_user_id=self.u1,account_id=self.a1)
        with self.assertRaises(atomic.AtomicPaperDenied):
            atomic.create_synthetic_atomic_fixture(self.path)
        self.assertFalse(self.state()["executionEnabled"])


if __name__=="__main__":
    unittest.main()
