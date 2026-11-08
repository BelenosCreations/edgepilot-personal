import unittest
from engine import discovery as d
class DiscoveryTests(unittest.TestCase):
 def test_equities(self):
  raw={'instruments':[{'instrument':{'symbol':'SPY','type':'EQUITY'},'trading':'BUY_AND_SELL'}, {'instrument':{'symbol':'ABC','type':'EQUITY'},'trading':'LIQUIDATION_ONLY'}, {'instrument':{'symbol':'SPY','type':'EQUITY'},'trading':'BUY_AND_SELL'}, {'instrument':{'symbol':'OPT','type':'OPTION'},'trading':'BUY_AND_SELL'}]}
  self.assertEqual(d.equity_symbols(raw),['SPY'])
 def test_rotation(self):
  a,c=d.select_window(['A','B','C','D'],0,2);b,n=d.select_window(['A','B','C','D'],c,2)
  self.assertEqual(a,['A','B']);self.assertEqual(b,['C','D']);self.assertEqual(n,0)
 def test_modes(self):
  self.assertEqual(d.mode_sources('automatic',['A'],['B']),['A'])
  self.assertEqual(d.mode_sources('hybrid',['A'],['B','A']),['A','B'])
  self.assertEqual(d.mode_sources('watchlist',['A'],['B']),['B'])
 def test_events(self):
  data={'content':[{'eventSymbol':'E1','resolved':False,'halted':False},{'eventSymbol':'E2','resolved':True},{'eventSymbol':'E3','halted':True}]}
  self.assertEqual([x['event'] for x in d.prediction_events(data)],['E1'])
 def test_contracts(self):
  data={'outcomes':[{'state':'STATE_OPEN','trading':'BUY_AND_SELL','contracts':[{'symbol':'YES'},{'symbol':'NO'}]}, {'state':'STATE_CLOSED','trading':'BUY_AND_SELL','contracts':[{'symbol':'BAD'}]}]}
  self.assertEqual(d.contract_candidates(data),['YES','NO'])
 def test_invalid(self):
  with self.assertRaises(ValueError):d.validate_mode('all_in')
  with self.assertRaises(ValueError):d.equity_symbols({})
if __name__=='__main__':unittest.main()
