import tempfile, os, unittest
from datetime import date, timedelta
from engine import public_history

def response(n=80):
    start=date(2025,1,2)
    bars=[]
    for i in range(n):
        d=start+timedelta(days=i)
        p=100+i*.2
        bars.append({'timestamp':d.isoformat()+'T16:00:00-05:00','open':f'{p:.4f}','close':f'{p+.1:.4f}', 'high':f'{p+.3:.4f}', 'low':f'{p-.1:.4f}', 'volume':1000+i})
    return {'symbol':'SPY','regularMarket':{'bars':bars}}

class PublicHistoryTests(unittest.TestCase):
    def test_normalize(self):
        rows=public_history.normalize(response())
        self.assertEqual(len(rows),80)
        self.assertEqual(rows[0]['date'],'2025-01-02')
    def test_bad_bar(self):
        p=response();p['regularMarket']['bars'][0]['close']='NaN'
        with self.assertRaises(ValueError):public_history.normalize(p)
    def test_duplicate_date(self):
        p=response();p['regularMarket']['bars'][1]['timestamp']=p['regularMarket']['bars'][0]['timestamp']
        with self.assertRaises(ValueError):public_history.normalize(p)
    def test_short_data(self):
        with self.assertRaises(ValueError):public_history.normalize(response(10))
    def test_invalid_period_and_symbol(self):
        self.assertEqual(public_history.clean_symbol('spy'),'SPY')
        with self.assertRaises(ValueError):public_history.clean_symbol('../abc')
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):public_history.fetch_history(os.path.join(td,'x.db'),lambda *a:None,'SPY','DAY')
    def test_cached_and_refresh(self):
        with tempfile.TemporaryDirectory() as td:
            db=os.path.join(td,'db.sqlite');public_history.setup(db)
            calls=[]
            def broker(method,path):
                calls.append((method,path));return response()
            a=public_history.fetch_history(db,broker,'SPY','YEAR');b=public_history.fetch_history(db,broker,'SPY','YEAR')
            self.assertFalse(a['cacheHit']);self.assertTrue(b['cacheHit']);self.assertEqual(len(calls),1)
            self.assertIn('/historicdata/EQUITY/SPY/YEAR/ONE_DAY',calls[0][1])
            c=public_history.fetch_history(db,broker,'SPY','YEAR',refresh=True)
            self.assertFalse(c['cacheHit']);self.assertEqual(len(calls),2)
    def test_failed_refresh_preserves_old_cache(self):
        with tempfile.TemporaryDirectory() as td:
            db=os.path.join(td,'db.sqlite');public_history.setup(db)
            public_history.fetch_history(db,lambda *args:response(),'SPY')
            def fail(*args):raise RuntimeError('connection failed')
            with self.assertRaises(RuntimeError):public_history.fetch_history(db,fail,'SPY',refresh=True)
            hit=public_history.fetch_history(db,fail,'SPY')
            self.assertTrue(hit['cacheHit'])
    def test_symbol_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            db=os.path.join(td,'db.sqlite');public_history.setup(db)
            with self.assertRaises(ValueError):public_history.fetch_history(db,lambda *args:{**response(),'symbol':'QQQ'},'SPY')

if __name__=='__main__':unittest.main()
