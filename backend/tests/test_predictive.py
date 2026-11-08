import unittest
from datetime import date,timedelta
from engine.predictive import parse_daily_csv,backtest

def history(n=140,up=True):
    # Explicitly synthetic: test validates mechanics, not market predictions.
    start=date(2025,1,1)
    rows=['date,open,close']
    for i in range(n):
        price=100+i*.1 if up else 100-i*.1
        rows.append(f'{start+timedelta(days=i)},{price:.4f},{price+.05:.4f}')
    return '\n'.join(rows)

class PredictiveTests(unittest.TestCase):
    def test_parse_and_split(self):
        bars=parse_daily_csv(history());out=backtest(bars)
        self.assertTrue(out['outOfSample']['trades']>0)
        self.assertFalse(out['eligibleForTrading'])
        self.assertEqual(out['bars'],140)
    def test_reject_bad_input(self):
        for csv in ('date,close\n2026-01-01,1','date,open,close\n2026-01-01,0,1',history(10)):
            with self.assertRaises(ValueError):parse_daily_csv(csv)
    def test_no_positive_momentum_no_trades(self):
        out=backtest(parse_daily_csv(history(up=False)));self.assertEqual(out['outOfSample']['trades'],0)
    def test_costs_reduce_result(self):
        bars=parse_daily_csv(history());a=backtest(bars,cost_bps=0);b=backtest(bars,cost_bps=100)
        self.assertLess(b['outOfSample']['compoundedNetReturnPct'],a['outOfSample']['compoundedNetReturnPct'])
    def test_no_lookahead_when_future_modified(self):
        b=parse_daily_csv(history());a=backtest(b);c=[dict(x) for x in b];c[-1]['close']=1_000_000
        d=backtest(c);self.assertEqual(a['sampleTrades'],d['sampleTrades'])
    def test_invalid_parameters(self):
        b=parse_daily_csv(history())
        with self.assertRaises(ValueError):backtest(b,lookback=1)
        with self.assertRaises(ValueError):backtest(b,cost_bps=-1)
