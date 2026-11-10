"""Regression: Observation Health refreshes only in the foreground at a safe read-only cadence."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
HTML=(ROOT/'backend/static/index.html').read_text(encoding='utf-8')
JS=(ROOT/'backend/static/assets/app.js').read_text(encoding='utf-8')
APP=(ROOT/'backend/app.py').read_text(encoding='utf-8')


class ObservationRefreshTests(unittest.TestCase):
    def test_foreground_observation_refresh_is_rate_limited(self):
        self.assertIn('const OBSERVATION_AUTO_REFRESH_MS=120000',JS)
        self.assertIn('function shouldAutoRefreshObservationHealth()',JS)
        self.assertIn("document.visibilityState==='visible'",JS)
        self.assertIn("!!$('dash')?.classList.contains('active')",JS)
        self.assertIn('Date.now()-observationLastStatusRefreshAt>=OBSERVATION_AUTO_REFRESH_MS',JS)
        self.assertIn("setInterval(refreshObservationHealthAutomatically,30000)",JS)
        self.assertIn("document.addEventListener('visibilitychange'",JS)
        self.assertIn("if(document.visibilityState==='visible')refreshObservationHealthAutomatically()",JS)
        self.assertIn('observationScheduledRefreshBusy=true',JS)
        self.assertIn('observationScheduledRefreshBusy=false',JS)

    def test_display_timestamp_and_manual_button_preserved(self):
        self.assertEqual(HTML.count('id="observationAutoRefresh"'),1)
        self.assertIn('every 2 minutes while Overview is visible',HTML)
        self.assertIn('observationLastStatusRefreshAt=Date.now()',JS)
        self.assertIn("new Date(observationLastStatusRefreshAt).toLocaleTimeString()",JS)
        self.assertIn('onclick="loadAutomationStatus()">Refresh observation health',HTML)
        self.assertIn('await loadAutomationStatus(false)',JS)

    def test_status_only_and_trading_still_disabled(self):
        self.assertIn("const data=await api('automation/status')",JS)
        interval=JS.split('async function refreshObservationHealthAutomatically()',1)[1].split('// A hosted PWA',1)[0]
        self.assertNotIn("api('scanner/run'",interval)
        self.assertNotIn("api('automation/auto/start'",interval)
        self.assertNotIn("api('funds/",interval)
        self.assertIn("'liveTradingAvailable':False",APP)
        self.assertIn("0.2.21-public-https-wire-inactive",APP)


if __name__=='__main__':
    unittest.main()
