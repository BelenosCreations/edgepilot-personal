"""v0.2 durable automation, paper risk and emergency protection tests."""
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from engine import automation, engine_config


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=os.path.join(self.temp.name,'auto.db')
        engine_config.setup(self.path)
        automation.setup(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def paper_config(self,capital='2000.00',level='balanced'):
        return {'mode':'paper','risk_level':level,'paper_capital':capital,
                'protected_pct':'50.00','profit_lock_pct':'0.00',
                'compound_pct':'0.00','reserve_profit_pct':'0.00'}

    def auto_plan(self,alloc='1000.00',cap='50.00'):
        plan=engine_config.DEFAULTS['auto'].copy()
        plan.update({'stock_allocation':alloc,'max_per_trade':cap,
                     'rolling_loss_stop':'15.00','loss_stop':'100.00','stock_loss_stop':'25.00'})
        engine_config.save(self.path,'auto',plan)
        return plan

    def quote(self, bid='101.00',ask='101.02'):
        t=datetime.now(timezone.utc)
        return {'source':'Public official quote API','market':'stock','symbol':'AAPL',
                'completeTopOfBook':True,'knownStale':False,'quoteAgeSeconds':'5',
                'bid':bid,'ask':ask,'capturedAt':t.isoformat(),
                'bidTimestamp':(t-timedelta(seconds=5)).isoformat()}

    def seed_trend(self):
        t=datetime.now(timezone.utc)
        with automation.db(self.path) as c:
            for seconds,bid in [(180,'99.00'),(90,'100.00')]:
                c.execute('''INSERT INTO automation_quotes
                    (engine,symbol,asset_class,captured_at,bid,ask,provider_timestamp)
                    VALUES('auto','AAPL','stock',?,?,?,?)''',
                    ((t-timedelta(seconds=seconds)).isoformat(),bid,str(float(bid)+.02),t.isoformat()))

    def test_safe_defaults_and_live_mode_denied(self):
        st=automation.status(self.path)
        self.assertFalse(st['master']['enabled'])
        self.assertEqual(st['master']['mode'],'observe')
        self.assertFalse(st['master']['liveTradingAvailable'])
        self.assertTrue(all(x['state']=='stopped' for x in st['engines'].values()))
        with self.assertRaisesRegex(ValueError,'Live mode unavailable'):
            automation.configure(self.path,{**self.paper_config(),'mode':'live'})

    def test_dollar_validation_and_profile_limits(self):
        for key,value in [('paper_capital','NaN'),('paper_capital','-1'),
                          ('protected_pct','100.00'),('compound_pct','100.00')]:
            data=self.paper_config();data[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                automation.configure(self.path,data)
        with self.assertRaisesRegex(ValueError,'complete known'):
            automation.configure(self.path,{'mode':'paper'})
        data=self.paper_config();data['risk_level']='aggressive'
        s=automation.configure(self.path,data)
        self.assertEqual(s['riskProfile']['riskPct'],'1.00')

    def test_paper_start_requires_config_and_virtual_capital(self):
        with self.assertRaisesRegex(ValueError,'positive virtual paper'):
            automation.configure(self.path,{**self.paper_config(),'paper_capital':'0.00'})
            automation.control(self.path,'start','auto')
        automation.configure(self.path,self.paper_config())
        with self.assertRaisesRegex(ValueError,'Save this engine plan'):
            automation.control(self.path,'start','auto')
        self.auto_plan()
        started=automation.control(self.path,'start','auto')
        self.assertEqual(started['engines']['auto']['state'],'running')
        self.assertEqual(started['master']['mode'],'paper')
        self.assertFalse(started['master']['liveTradingAvailable'])
        with self.assertRaisesRegex(ValueError,'settlement-safe'):
            automation.control(self.path,'start','fifteen')

    def test_observe_records_real_quotes_but_never_paper_orders(self):
        automation.control(self.path,'start','auto')
        result=automation.process_quote(self.path,'auto',self.quote())
        self.assertEqual(result['action'],'OBSERVE')
        self.assertEqual(automation.status(self.path)['paper']['recentTrades'],[])
        self.assertEqual(automation.status(self.path)['paper']['openPositions'],[])

    def test_paper_momentum_entry_marks_and_exit_are_simulated(self):
        automation.configure(self.path,self.paper_config())
        self.auto_plan()
        automation.control(self.path,'start','auto')
        self.seed_trend()
        entry=automation.process_quote(self.path,'auto',self.quote())
        self.assertEqual(entry['action'],'PAPER_ENTRY')
        self.assertGreater(float(entry['qty']),0)
        paper=automation.status(self.path)['paper']
        self.assertEqual(len(paper['openPositions']),1)
        self.assertLessEqual(float(paper['exposure']),10.0)
        out=automation.process_quote(self.path,'auto',self.quote('106.00','106.02'))
        self.assertEqual(out['action'],'PAPER_EXIT')
        after=automation.status(self.path)['paper']
        self.assertEqual(len(after['openPositions']),0)
        self.assertEqual(len(after['recentTrades']),1)
        self.assertEqual(after['recentTrades'][0]['strategy'],'unvalidated_momentum')

    def test_never_use_unverified_or_stale_quotes(self):
        automation.configure(self.path,self.paper_config())
        self.auto_plan()
        automation.control(self.path,'start','auto')
        for changed in ({'knownStale':True},{'quoteAgeSeconds':None},
                        {'source':'unknown'},{'bid':'110','ask':'100'},
                        {'quoteAgeSeconds':'999'}):
            q={**self.quote(),**changed}
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                automation.process_quote(self.path,'auto',q)
        self.assertEqual(automation.status(self.path)['paper']['openPositions'],[])

    def test_emergency_stop_persists_and_latches_all_engines(self):
        automation.control(self.path,'start','auto')
        automation.control(self.path,'start','micro')
        out=automation.control(self.path,'emergency')
        self.assertEqual(out['master']['emergency'],1)
        self.assertFalse(out['master']['enabled'])
        self.assertTrue(all(x['state']=='paused' for x in out['engines'].values()))
        with self.assertRaisesRegex(ValueError,'Emergency Stop'):
            automation.control(self.path,'start','auto')
        fresh=automation.status(self.path)
        self.assertEqual(fresh['master']['emergency'],1)
        reset=automation.control(self.path,'reset_emergency')
        self.assertEqual(reset['master']['emergency'],0)
        self.assertEqual(reset['engines']['auto']['state'],'paused')

    def test_double_worker_is_rejected_until_lease_expires(self):
        self.assertTrue(automation.acquire_lease(self.path,'workerA'))
        self.assertTrue(automation.acquire_lease(self.path,'workerA'))
        self.assertFalse(automation.acquire_lease(self.path,'workerB'))
        with automation.db(self.path) as c:
            c.execute('UPDATE automation_worker_lease SET expires_at=? WHERE id=1',
                      ((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),))
        self.assertTrue(automation.acquire_lease(self.path,'workerB'))

    def test_fail_closed_pauses_all_and_preserves_paper_records(self):
        automation.configure(self.path,self.paper_config())
        self.auto_plan()
        automation.control(self.path,'start','auto')
        automation.fail_closed(self.path,'Market quotes unavailable')
        st=automation.status(self.path)
        self.assertEqual(st['engines']['auto']['state'],'paused')
        self.assertEqual(st['master']['enabled'],0)
        self.assertIn('Market quotes',st['master']['last_error'])

    def test_profile_changes_do_not_auto_arm_broker_or_erase_pnl(self):
        self.auto_plan()
        self.assertFalse(automation.status(self.path)['master']['liveTradingAvailable'])
        automation.configure(self.path,self.paper_config())
        automation.control(self.path,'start','auto')
        automation.control(self.path,'pause','auto')
        after=automation.status(self.path)
        self.assertFalse(after['master']['enabled'])
        self.assertFalse(after['master']['liveTradingAvailable'])
        self.assertEqual(after['engines']['auto']['state'],'paused')


if __name__=='__main__':
    unittest.main()
