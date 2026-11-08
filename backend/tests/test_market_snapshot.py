import unittest
from engine.market_snapshot import stock_snapshot,prediction_snapshot,text_context

class MarketSnapshotTests(unittest.TestCase):
 def test_stock_spread(self):
  def source(method,path,body):
   self.assertEqual(method,'POST');self.assertEqual(body['instruments'][0]['symbol'],'AAPL')
   return {'quotes':[{'instrument':{'symbol':'AAPL','type':'EQUITY'},'outcome':'SUCCESS','bid':'100.00','ask':'100.05','volume':1000,'bidTimestamp':'2026-01-01T00:00:00Z'}]}
  s=stock_snapshot(source,'account-test','aapl',now='fixed')
  self.assertEqual(s['spread'],'0.05');self.assertEqual(s['spreadPctOfAsk'],'0.0500');self.assertTrue(s['completeTopOfBook'])
  self.assertNotIn('account-test',text_context(s))
 def test_stock_invalid_or_crossed(self):
  with self.assertRaises(ValueError):stock_snapshot(lambda *x: None,'account','../../secret')
  s=stock_snapshot(lambda *x:{'quotes':[{'instrument':{'symbol':'AAPL','type':'EQUITY'},'outcome':'SUCCESS','bid':'3','ask':'2'}]},'acct','AAPL')
  self.assertFalse(s['completeTopOfBook'])
 def test_missing_quote(self):
  with self.assertRaises(ValueError):stock_snapshot(lambda *x:{'quotes':[]},'acct','AAPL')
 def test_prediction(self):
  data={'eventSymbol':'KALSHI.X','title':'An event','outcomes':[{'title':'Yes outcome','state':'STATE_OPEN','trading':'BUY_AND_SELL','contracts':[{'symbol':'CONTRACT','bid':'0.45','ask':'0.47'}]}]}
  s=prediction_snapshot(lambda *x:data,'KALSHI.X','CONTRACT',now='fixed')
  self.assertTrue(s['openForTrading']);self.assertEqual(s['spread'],'0.02')
  self.assertNotIn('account',text_context(s))
 def test_prediction_halt(self):
  data={'eventSymbol':'KALSHI.X','halted':True,'outcomes':[{'state':'STATE_OPEN','trading':'BUY_AND_SELL','contracts':[{'symbol':'C','bid':'0.3','ask':'0.4'}]}]}
  self.assertFalse(prediction_snapshot(lambda *x:data,'KALSHI.X','C')['openForTrading'])
 def test_predictions_require_matching_contract(self):
  with self.assertRaises(ValueError):prediction_snapshot(lambda *x:{'eventSymbol':'KALSHI.X','outcomes':[]},'KALSHI.X','C')

if __name__=='__main__':unittest.main()
