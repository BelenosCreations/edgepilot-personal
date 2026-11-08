import unittest
from datetime import date,timedelta
from engine.walk_forward import validate


def bars(n=450, trend=.001):
    start=date(2024,1,1)
    return [{'date':str(start+timedelta(days=i)),'open':round(100*(1+trend)**i,6),'close':round(100*(1+trend)**(i+.5),6)} for i in range(n)]

class WalkForwardTests(unittest.TestCase):
    def test_expected_nonoverlap_and_no_trade_permission(self):
        r=validate(bars(),training_bars=180,test_bars=60,step_bars=60)
        self.assertEqual(r['evaluatedWindows'],4)
        self.assertFalse(r['eligibleForTrading'])
        times=[(x['testStartDate'],x['testEndDate']) for x in r['folds']]
        self.assertTrue(all(times[i][1]<times[i+1][0] for i in range(len(times)-1)))
    def test_one_fold_flagged(self):
        r=validate(bars(240),training_bars=180,test_bars=60,step_bars=60)
        self.assertIn('Fewer than 3 evaluated walk-forward windows',r['warnings'])
    def test_reject_overlapping_windows(self):
        with self.assertRaises(ValueError):validate(bars(),training_bars=180,test_bars=60,step_bars=30)
    def test_reject_bad_dates(self):
        x=bars();x[30]['date']=x[29]['date']
        with self.assertRaises(ValueError):validate(x)
    def test_no_lookahead_train_choice(self):
        x=bars()
        a=validate(x)
        # Alter last 10 days; first fold's selected model cannot change.
        for d in x[-10:]:d['open']*=1.2;d['close']*=1.2
        b=validate(x)
        self.assertEqual(a['folds'][0]['lookbackSelected'],b['folds'][0]['lookbackSelected'])
    def test_reject_bad_lookback(self):
        with self.assertRaises(ValueError):validate(bars(),lookbacks=[3,3])
    def test_no_trades_negative_market(self):
        r=validate(bars(trend=-.002))
        self.assertFalse(r['eligibleForTrading'])
        self.assertEqual(r['outOfSample']['trades'],0)

if __name__=='__main__':unittest.main()
