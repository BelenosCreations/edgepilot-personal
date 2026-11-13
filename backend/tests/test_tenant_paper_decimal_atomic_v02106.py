"""v0.2.106 offline fractional-Decimal accounting + sticky stop research.

No licensed observations, broker calls, tenant records or production routes.
"""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
import uuid

from engine import tenant_paper_decimal_atomic_rehearsal as decimal_atomic


def identity():
    return str(uuid.uuid4())


class DecimalAtomicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(
            dir="/dev/shm",prefix="edgepilot-decimal-v02106-")
        self.path = Path(self.temp.name)/"fixture.db"
        self.old = Path(self.temp.name)/"old.db"
        self.key, self.anchor = os.urandom(32), os.urandom(32)
        self.u1,self.u2 = identity(), identity()
        self.a1,self.a2,self.a3 = identity(), identity(), identity()
        decimal_atomic.create_decimal_fixture(self.path)
        for user, account in ((self.u1,self.a1),(self.u1,self.a2),(self.u2,self.a3)):
            self.register(user,account)

    def tearDown(self):
        self.temp.cleanup()

    def register(self,user,account,**values):
        options={"initial_cash_cents":10000,"protected_pct":90,
                 "spend_cap_cents":2000,"per_trade_cap_cents":800,
                 "max_loss_cents":14}
        options.update(values)
        return decimal_atomic.register_decimal_account(
            self.path,hmac_key=self.key,principal_user_id=user,
            account_id=account,**options)

    def fill(self, side="BUY", *, user=None,account=None,request=None,**values):
        options={"asset_class":"stock","symbol":"TEST","quantity":"0.5",
                 "assumed_unit_price":"2.00","fee_per_unit":"0.02",
                 "slippage_per_unit":"0.01"}
        options.update(values)
        return decimal_atomic.decimal_fill(self.path,hmac_key=self.key,
            principal_user_id=user or self.u1, account_id=account or self.a1,
            request_id=request or identity(),side=side,**options)

    def state(self,*,user=None,account=None,key=None):
        return decimal_atomic.inspect_decimal_account(
            self.path,hmac_key=key or self.key,
            principal_user_id=user or self.u1,account_id=account or self.a1)

    def pin(self):
        return decimal_atomic.make_decimal_checkpoint(
            self.path,hmac_key=self.key,anchor_key=self.anchor,epoch=2)

    def test_fractional_buy_sell_and_rounding_match_decimal_ledger(self):
        buy=self.fill(quantity="0.125",assumed_unit_price="2.00",
                      fee_per_unit="0.02",slippage_per_unit="0.01")
        self.assertEqual(buy["cashCents"],9974)  # ceil(0.125 * 2.03 * 100)
        self.assertEqual(self.state()["positions"],[["stock","TEST","0.125",26,0]])
        sell=self.fill("SELL",quantity="0.05",assumed_unit_price="1.99",
                       fee_per_unit="0.02",slippage_per_unit="0.01")
        self.assertEqual(sell["realizedDeltaCents"],-2)
        self.assertEqual(self.state()["positions"],[["stock","TEST","0.075",15,-2]])
        self.assertEqual(sell["cashCents"],9983)
        done=self.fill("SELL",quantity="0.075",assumed_unit_price="1.99")
        self.assertEqual(done["realizedDeltaCents"],-1)
        self.assertEqual(self.state()["positions"],[["stock","TEST","0",0,-3]])
        self.assertEqual(done["cashCents"],9997)

    def test_sticky_historical_stop_and_liquidation(self):
        self.fill(quantity="2")
        self.fill(symbol="GAIN",quantity="1",assumed_unit_price="1.00",
                  fee_per_unit="0",slippage_per_unit="0")
        self.fill("SELL",quantity="1",assumed_unit_price="1.99")
        result=self.fill("SELL",quantity="1",assumed_unit_price="1.99")
        self.assertEqual(result["realizedCents"],-14)
        self.assertTrue(result["stopped"])
        with self.assertRaises(decimal_atomic.DecimalAtomicDenied):
            self.fill(symbol="NEW",quantity="0.01")
        gain=self.fill("SELL",symbol="GAIN",quantity="1",
                       assumed_unit_price="3.00",fee_per_unit="0",
                       slippage_per_unit="0")
        self.assertEqual(gain["realizedCents"],186)
        self.assertEqual(gain["worstRealizedCents"],-14)
        self.assertTrue(gain["stopped"])
        with self.assertRaises(decimal_atomic.DecimalAtomicDenied):
            self.fill(quantity="0.01")

    def test_idempotency_is_scoped_and_original_balance_remains_historical(self):
        req=identity()
        first=self.fill(request=req)
        self.assertFalse(first["duplicate"])
        retry=self.fill(request=req,quantity="0.50")
        self.assertTrue(retry["duplicate"])
        self.assertEqual(retry["originalCashAfterCents"],9898)
        with self.assertRaises(decimal_atomic.DecimalAtomicDenied):
            self.fill(request=req,quantity="0.75")
        self.fill()
        later=self.fill(request=req)
        self.assertTrue(later["duplicate"])
        self.assertEqual(later["cashCents"],9796)
        self.assertEqual(later["originalCashAfterCents"],9898)
        self.assertEqual(self.state()["fillCount"],2)
        self.assertEqual(self.state(account=self.a2)["fillCount"],0)

    def test_isolation_policy_and_invalid_decimal_or_short_sales(self):
        self.fill()
        self.assertEqual(self.state(account=self.a2)["cashCents"],10000)
        self.assertEqual(self.state(user=self.u2,account=self.a3)["cashCents"],10000)
        for user,account in ((self.u1,self.a3),(self.u2,self.a1)):
            with self.assertRaises(decimal_atomic.DecimalAtomicDenied):
                self.fill(user=user,account=account)
        for options in ({"quantity":"-1"},{"quantity":"NaN"},
                        {"quantity":float("inf")},{"quantity":"0.0000000000000000001"},
                        {"fee_per_unit":"-1"},{"slippage_per_unit":"Infinity"},
                        {"assumed_unit_price":"0"},{"asset_class":"prediction"}):
            with self.subTest(options=options):
                with self.assertRaises(decimal_atomic.DecimalAtomicDenied):
                    self.fill(**options)
        with self.assertRaises(decimal_atomic.DecimalAtomicDenied):
            self.fill("SELL",quantity="0.500000000000000001")
        with self.assertRaises(decimal_atomic.DecimalAtomicDenied):
            self.register(self.u1,self.a1,protected_pct=0)
        with self.assertRaises(decimal_atomic.DecimalAtomicDenied):
            self.register(self.u1,identity(),protected_pct=100)
        self.assertEqual(self.state()["fillCount"],1)

    def test_failed_transaction_rolls_back_everything_and_can_retry(self):
        before=self.pin()
        req=identity()
        with self.assertRaises(decimal_atomic.DecimalAtomicDenied):
            self.fill(request=req,_fail_before_commit=True)
        self.assertEqual(self.state()["fillCount"],0)
        self.assertTrue(decimal_atomic.verify_decimal_checkpoint(
            self.path,hmac_key=self.key,anchor_key=self.anchor,
            externally_trusted_latest_checkpoint=before)["checkpointVerified"])
        self.fill(request=req)
        with self.assertRaises(decimal_atomic.DecimalAtomicDenied):
            decimal_atomic.verify_decimal_checkpoint(
                self.path,hmac_key=self.key,anchor_key=self.anchor,
                externally_trusted_latest_checkpoint=before)

    def test_concurrent_distinct_requests_and_same_request(self):
        def attempt(_):
            try:
                self.fill(quantity="1",fee_per_unit="0",slippage_per_unit="0")
                return True
            except decimal_atomic.DecimalAtomicDenied:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            accepted=list(pool.map(attempt,range(12)))
        self.assertEqual(sum(accepted),5)
        self.assertEqual(self.state()["positions"],[["stock","TEST","5",1000,0]])
        req=identity()
        with ThreadPoolExecutor(max_workers=6) as pool:
            outcomes=list(pool.map(lambda _:self.fill("SELL",request=req,
                quantity="0.01",assumed_unit_price="1.99",
                fee_per_unit="0",slippage_per_unit="0"),range(8)))
        self.assertEqual(sum(not o["duplicate"] for o in outcomes),1)
        self.assertEqual(self.state()["fillCount"],6)

    def test_tamper_wrong_key_and_pinned_rollback_fail_closed(self):
        old=self.pin()
        shutil.copyfile(self.path,self.old)
        self.old.chmod(0o600)
        self.fill()
        current=self.pin()
        with self.assertRaises(decimal_atomic.DecimalAtomicDenied):
            decimal_atomic.verify_decimal_checkpoint(
                self.old,hmac_key=self.key,anchor_key=self.anchor,
                externally_trusted_latest_checkpoint=current)
        with self.assertRaises(decimal_atomic.DecimalAtomicDenied):
            self.state(key=os.urandom(32))
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE decimal_positions SET basis=basis+1 WHERE account_id=?",
                       (self.a1,))
        with self.assertRaises(decimal_atomic.DecimalAtomicDenied):
            self.state()
        with self.assertRaises(decimal_atomic.DecimalAtomicDenied):
            self.fill()
        self.assertEqual(old["epoch"],2)

    def test_reject_existing_untrusted_database_and_unsafe_paths(self):
        with self.assertRaises(decimal_atomic.DecimalAtomicDenied):
            decimal_atomic.create_decimal_fixture(self.path)
        with self.assertRaises(decimal_atomic.DecimalAtomicDenied):
            decimal_atomic.create_decimal_fixture(Path(self.temp.name)/"../oops.db")
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaises(decimal_atomic.DecimalAtomicDenied):
                decimal_atomic.create_decimal_fixture(Path(other)/"external.db")
        symlink=Path(self.temp.name)/"link.db"
        symlink.symlink_to(self.path)
        with self.assertRaises(decimal_atomic.DecimalAtomicDenied):
            decimal_atomic.inspect_decimal_account(
                symlink,hmac_key=self.key,
                principal_user_id=self.u1,account_id=self.a1)
        with self.assertRaises(decimal_atomic.DecimalAtomicDenied):
            decimal_atomic.verify_decimal_checkpoint(
                self.path,hmac_key=self.key,anchor_key=os.urandom(32),
                externally_trusted_latest_checkpoint=self.pin())


if __name__ == "__main__":
    unittest.main()
