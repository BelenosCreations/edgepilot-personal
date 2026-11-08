import unittest
from engine import opportunity_scan as s
class ScannerTests(unittest.TestCase):
 def snapshot(self,market='stock'):
  return {'market':market,'symbol':'SPY' if market=='stock' else 'KALSHI.X', 'bid':'100','ask':'100.05','volume':1000000,'completeTopOfBook':True,'knownStale':False,'quoteAgeSeconds':'12'} if market=='stock' else {'market':'prediction','symbol':'KALSHI.X','bid':'0.59','ask':'0.60','quoteTimestamp':'2026-11-08T12:00:00Z','eventVolume':'20000','completeTopOfBook':True,'openForTrading':True}
 def test_symbols(self):
  self.assertEqual(s.stock_universe('spy, QQQ,spy'),['SPY','QQQ'])
  with self.assertRaises(ValueError):s.stock_universe('../secret')
  with self.assertRaises(ValueError):s.stock_universe(','.join('A'+str(i) for i in range(26)))
 def test_no_stock_return_forecast(self):
  result=s.assess(self.snapshot());self.assertIsNone(result['expectedNetValue']);self.assertFalse(result['eligibleForAutomaticTrading'])
 def test_prediction_assumption_only(self):
  r=s.assess(self.snapshot('prediction'),fair_pct='70')
  self.assertEqual(r['expectedNetValue'],'0.0800');self.assertIn('Manually supplied',r['modelSource'])
 def test_negative_edge(self):
  r=s.assess(self.snapshot('prediction'),fair_pct='55');self.assertEqual(r['classification'],'REJECT_ASSUMPTION_NEGATIVE')
 def test_invalid_and_closed(self):
  a=self.snapshot('prediction');a['openForTrading']=False
  self.assertEqual(s.assess(a,'70')['qualityScore'],0)
  b=self.snapshot();b['knownStale']=True
  self.assertEqual(s.assess(b)['qualityScore'],0)
 def test_missing_quote(self):
  a=self.snapshot();a['ask']=None
  self.assertEqual(s.assess(a)['qualityScore'],0)
 def test_fair_probability_bounds(self):
  with self.assertRaises(ValueError):s.assess(self.snapshot('prediction'),'110')
 def test_ranking(self):
  self.assertEqual([x['qualityScore'] for x in s.rank([{'qualityScore':2},{'qualityScore':90}])],[90,2])
if __name__=='__main__':unittest.main()
