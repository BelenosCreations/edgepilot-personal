import os, tempfile, unittest
from engine import ledger, risk

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=os.path.join(self.tmp.name,'ledger.db');ledger.setup(self.path)
        self.base=dict(account='acct1',symbol='ABC',timestamp='2026-11-08T11:00:00Z')
    def tearDown(self):self.tmp.cleanup()
    def fill(self,**kw):
        data={**self.base,'fill_id':'fill1','side':'BUY','quantity':'2','price':'10','fee':'.10','source':'EDGEPILOT',**kw}
        return ledger.ingest_fill(self.path,**data)
    def test_duplicate_idempotency(self):
        self.fill(); self.assertTrue(self.fill()['duplicate']);self.assertEqual(ledger.summary(self.path)['openCostBasis'],'20.10')
        with self.assertRaisesRegex(ValueError,'Conflicting'): self.fill(price='11')
    def test_proceeds_not_profit(self):
        self.fill()
        x=self.fill(fill_id='fill2',side='SELL',quantity='2',price='12',fee='.10')
        self.assertEqual(x['realized_pnl'],'3.80')
        self.assertEqual(ledger.summary(self.path)['openCostBasis'],'0.00')
    def test_partial_external_sell_requires_decision(self):
        self.fill()
        x=self.fill(fill_id='fill2',side='SELL',quantity='1',price='11',fee='.10',source='EXTERNAL')
        self.assertTrue(x['requires_repurchase_decision'])
        s=ledger.summary(self.path);self.assertEqual(s['positions'][0]['quantity'],'1');self.assertEqual(len(s['pendingDecisions']),1)
    def test_oversell_rollback(self):
        self.fill()
        with self.assertRaisesRegex(ValueError,'exceeds'):self.fill(fill_id='fill2',side='SELL',quantity='3')
        with ledger.open_db(self.path) as c:self.assertEqual(c.execute('SELECT count(*) FROM broker_fills').fetchone()[0],1)
    def test_external_buy_not_attributed(self):
        self.fill(fill_id='f2',source='EXTERNAL')
        self.assertEqual(ledger.summary(self.path)['openCostBasis'],'0.00')

class RiskTests(unittest.TestCase):
    def args(self,**overrides):
        p=dict(public_equity='160',independent_equity='100',balance_source='independent',protected_pct='50',spend_cap='75',per_trade_cap='5',broker_buying_power='70',attributed_exposure='20',other_exposure='10',open_orders='5',unreconciled_orders='0',fresh=True,reconciled=True)
        p.update(overrides);return p
    def test_independent_and_existing_exposure(self):
        x=risk.buying_capacity(**self.args());self.assertEqual(x['riskBudget'],'50.00');self.assertEqual(x['remainingToRisk'],'15.00');self.assertEqual(x['singleTradeLimit'],'5.00')
    def test_public_balance(self):
        x=risk.buying_capacity(**self.args(balance_source='public'));self.assertEqual(x['riskBudget'],'75.00')
    def test_stale_data_fails_closed(self):
        with self.assertRaises(risk.RiskBlocked):risk.buying_capacity(**self.args(fresh=False))
    def test_below_allocation_fails_closed(self):
        with self.assertRaises(risk.RiskBlocked):risk.buying_capacity(**self.args(public_equity='90'))
    def test_protection_100_pct(self):
        x=risk.buying_capacity(**self.args(protected_pct='100'));self.assertEqual(x['remainingToRisk'],'0.00')
    def test_sale_prompt_blocks(self):
        with self.assertRaises(risk.RiskBlocked):risk.buying_capacity(**self.args(pending_external_sale=True))

if __name__=='__main__':unittest.main()
