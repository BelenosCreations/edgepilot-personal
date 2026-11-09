"""Persisted observation diagnostics and quote-processing regression tests."""
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from engine import automation, automation_worker, engine_config, observation_health

ROOT=Path(__file__).resolve().parents[2]


class ObservationHealthTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=str(Path(self.temp.name)/'edgepilot.db')
        engine_config.setup(self.path)
        automation.setup(self.path)
        observation_health.setup(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_empty_and_bounded_cycle_journal_survive_reopen(self):
        initial=observation_health.report(self.path)
        self.assertIsNone(initial['lastCycle'])
        self.assertIsNone(initial['lastSuccessfulScanAt'])
        self.assertEqual(initial['last24h']['quotesAccepted'],0)
        observation_health.record_cycle(self.path,mode='observe',state='OK',
            market_session='CLOSED',symbols=['SPY'],accepted=1,quote_age_seconds=1)
        first=observation_health.report(self.path)
        self.assertEqual(first['lastCycle']['symbols'],['SPY'])
        self.assertEqual(first['lastCycle']['marketSession'],'CLOSED')
        self.assertIsNotNone(first['lastSuccessfulScanAt'])
        observation_health.record_cycle(self.path,mode='observe',state='NO_DATA',
            market_session='CLOSED',symbols=['SPY'],rejected=1,issue='Quote invalid')
        follow=observation_health.report(self.path)
        self.assertEqual(follow['lastCycle']['state'],'NO_DATA')
        self.assertEqual(follow['last24h']['quotesAccepted'],1)
        self.assertEqual(follow['last24h']['quotesRejected'],1)
        self.assertEqual(follow['lastSuccessfulScanAt'],first['lastSuccessfulScanAt'])
        # DB setup is safe on process restarts and must not delete cycle history.
        observation_health.setup(self.path)
        self.assertEqual(observation_health.report(self.path)['last24h']['cycles'],2)
        for _ in range(203):
            observation_health.record_cycle(self.path,mode='observe',state='NO_DATA')
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM observation_cycles').fetchone()[0],200)

    def test_reject_invalid_or_sensitive_cycle_metadata(self):
        for settings in ({'mode':'live','state':'OK'},
                         {'mode':'observe','state':'PAPER_ENTRY'},
                         {'mode':'observe','state':'OK','symbols':['../secret']},
                         {'mode':'observe','state':'OK','accepted':-1}):
            with self.subTest(settings=settings),self.assertRaises(ValueError):
                observation_health.record_cycle(self.path,**settings)
        self.assertIsNone(observation_health.report(self.path)['lastCycle'])

    def fake_app(self):
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE scan_config(id INTEGER PRIMARY KEY,symbols TEXT)')
            db.execute('INSERT INTO scan_config VALUES(1,?)',('AAPL',))
            db.execute('CREATE TABLE discovery_config(id INTEGER PRIMARY KEY,mode TEXT,cursor INTEGER,equity_per_scan INTEGER)')
            db.execute('INSERT INTO discovery_config VALUES(1,?,?,?)',('watchlist',0,5))
        def database():
            c=sqlite3.connect(self.path)
            c.row_factory=sqlite3.Row
            return c
        return SimpleNamespace(DB=self.path,database=database,pub=lambda *_:None,
            selected_account=lambda:'private-test-account',
            discovered_market_candidates=lambda *args:(['AAPL'],[],0,0))

    def quote(self):
        t=datetime.now(timezone.utc)
        return {'source':'Public official quote API','market':'stock','symbol':'AAPL',
                'bid':'101.00','ask':'101.02','completeTopOfBook':True,
                'knownStale':False,'quoteAgeSeconds':'5','capturedAt':t.isoformat(),
                'bidTimestamp':(t-timedelta(seconds=5)).isoformat()}

    def test_observe_records_success_then_rejection_without_paper_fills(self):
        app=self.fake_app()
        automation.control(self.path,'start','auto')
        with patch('engine.stock_session.regular_session_state',return_value='CLOSED'),\
             patch('engine.market_snapshot.stock_snapshot',return_value=self.quote()):
            observed=automation_worker.one_cycle(app,'test-worker')
        self.assertEqual(observed['status'],'OBSERVED')
        successful=observation_health.report(self.path)
        self.assertEqual(successful['lastCycle']['quotesAccepted'],1)
        self.assertEqual(successful['lastCycle']['marketSession'],'CLOSED')
        self.assertEqual(successful['lastCycle']['symbols'],['AAPL'])
        self.assertEqual(automation.status(self.path)['paper']['openPositions'],[])
        with patch('engine.stock_session.regular_session_state',return_value='CLOSED'),\
             patch('engine.market_snapshot.stock_snapshot',side_effect=ValueError('broker secret must not leak')):
            missing=automation_worker.one_cycle(app,'test-worker')
        self.assertEqual(missing['status'],'NO_DATA')
        latest=observation_health.report(self.path)
        self.assertEqual(latest['lastCycle']['quotesAccepted'],0)
        self.assertEqual(latest['lastCycle']['quotesRejected'],1)
        self.assertEqual(latest['lastSuccessfulScanAt'],successful['lastSuccessfulScanAt'])
        self.assertNotIn('broker secret',str(latest))
        self.assertTrue(automation.status(self.path)['master']['enabled'])

    def test_paper_closed_session_records_no_simulated_fill(self):
        app=self.fake_app()
        automation.configure(self.path,{
            'mode':'paper','risk_level':'balanced','paper_capital':'1000.00',
            'protected_pct':'50.00','profit_lock_pct':'0.00',
            'compound_pct':'0.00','reserve_profit_pct':'0.00'})
        plan=engine_config.DEFAULTS['auto'].copy()
        plan.update({'stock_allocation':'500.00','max_per_trade':'20.00'})
        engine_config.save(self.path,'auto',plan)
        automation.control(self.path,'start','auto')
        with patch('engine.stock_session.regular_session_state',return_value='CLOSED'):
            result=automation_worker.one_cycle(app,'paper-worker')
        self.assertEqual(result['status'],'MARKET_CLOSED')
        self.assertEqual(observation_health.report(self.path)['lastCycle']['state'],'MARKET_CLOSED')
        self.assertEqual(automation.status(self.path)['paper']['openPositions'],[])
        self.assertIsNone(observation_health.report(self.path)['lastSuccessfulScanAt'])

    def test_observation_panel_uses_text_content_not_html_for_broker_data(self):
        html=(ROOT/'backend/static/index.html').read_text()
        js=(ROOT/'backend/static/assets/app.js').read_text()
        self.assertIn('id="observationHealthPanel"',html)
        for field in ('observationLastSuccess','observationAccepted','observationRejected',
                      'observationMarketSession','observationQuoteAge','observationIssue'):
            self.assertEqual(html.count('id="'+field+'"'),1)
        self.assertIn('renderObservationHealth(data.observationHealth,m)',js)
        self.assertIn('observationHealthBadge',js)
        self.assertIn("lastSuccessfulScanAt",js)
        self.assertIn("quotesRejected",js)
        self.assertIn('textContent',js)
        app=(ROOT/'backend/app.py').read_text()
        self.assertIn("result['observationHealth']=observation_health.report(str(DB))",app)
        self.assertIn("'liveTradingAvailable':False",app)


if __name__=='__main__':
    unittest.main()
