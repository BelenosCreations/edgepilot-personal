import os,tempfile,unittest
from engine import order_audit

class AuditTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=os.path.join(self.tmp.name,'audit.db');order_audit.setup(self.db)
 def tearDown(self):self.tmp.cleanup()
 def order(self, status='PARTIALLY_FILLED',qty='1',trades=None):
  return {'orderId':'o1','instrument':{'symbol':'ABC'},'status':status,'side':'BUY',
  'createdAt':'2026-11-08T01:00:00Z','filledQuantity':qty,
  'trades':trades if trades is not None else [self.trade()]}
 def trade(self,tid='t1',quantity='1',price='10'):
  return {'tradeId':tid,'quantity':quantity,'price':price,'side':'BUY','timestamp':'2026-11-08T01:01:00Z','instrument':{'symbol':'ABC'}}
 def test_idempotency(self):
  x=order_audit.observe(self.db,'a',[self.order()]);self.assertEqual(x['newTrades'],1)
  y=order_audit.observe(self.db,'a',[self.order()]);self.assertEqual(y['newTrades'],0)
  v=order_audit.overview(self.db,'a');self.assertEqual(len(v['trades']),1);self.assertEqual(v['trades'][0]['origin'],'UNVERIFIED');self.assertFalse(v['ledgerPostingEnabled'])
 def test_partial_fill_updates(self):
  order_audit.observe(self.db,'a',[self.order()]);
  x=order_audit.observe(self.db,'a',[self.order('FILLED','2',[self.trade(),self.trade('t2','1','11')])]);self.assertEqual(x['newTrades'],1)
  self.assertEqual(len(order_audit.overview(self.db,'a')['trades']),2)
 def test_trade_conflict_rolls_back(self):
  order_audit.observe(self.db,'a',[self.order()]);
  with self.assertRaisesRegex(ValueError,'conflict'):
   order_audit.observe(self.db,'a',[self.order('FILLED','2',[self.trade(price='11'),self.trade('t2')])])
  self.assertEqual(len(order_audit.overview(self.db,'a')['trades']),1)
 def test_invalid_batch_no_partial_commit(self):
  good=self.order();bad={**self.order(), 'orderId':'o2','filledQuantity':'-1'}
  with self.assertRaises(ValueError):order_audit.observe(self.db,'a',[good,bad])
  self.assertEqual(len(order_audit.overview(self.db,'a')['orders']),0)
 def test_incomplete_trade_details_flags(self):
  order_audit.observe(self.db,'a',[self.order(qty='2')]);
  self.assertTrue(any(a['kind']=='INCOMPLETE_TRADES' for a in order_audit.overview(self.db,'a')['alerts']))
 def test_terminal_mutation_blocks(self):
  order_audit.observe(self.db,'a',[self.order('FILLED')]);
  with self.assertRaises(ValueError):order_audit.observe(self.db,'a',[self.order('CANCELLED')])
 def test_unproven_execution_never_posts_money_ledger(self):
  order_audit.observe(self.db,'a',[self.order()]);
  with order_audit.connection(self.db) as c:
   self.assertEqual(c.execute('SELECT count(*) FROM broker_fills').fetchone()[0] if c.execute("SELECT count(*) FROM sqlite_master WHERE name='broker_fills'").fetchone()[0] else 0,0)
 def test_duplicate_trade_id_across_orders_rejected(self):
  second=self.order();second['orderId']='o2'
  with self.assertRaisesRegex(ValueError,'duplicate'):
   order_audit.observe(self.db,'a',[self.order(),second])
if __name__=='__main__':unittest.main()
