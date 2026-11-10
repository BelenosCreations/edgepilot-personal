"""Read-only dashboard presentation contract for the 0.19.15.1 mobile patch."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HTML=(ROOT/'backend/static/index.html')
JS=(ROOT/'backend/static/assets/app.js')
APP=(ROOT/'backend/app.py')

class DashboardPresentationTests(unittest.TestCase):
    def test_approved_logo_has_no_redundant_subtitle(self):
        html=HTML.read_text(encoding='utf-8')
        self.assertIn('src="/assets/edgepilot-brand.png"',html)
        self.assertIn('object-fit:contain',html)
        self.assertNotIn('PERSONAL TRADING INSTANCE',html)
        self.assertNotIn('brand-subtitle',html)
        self.assertIn('id="mode"',html)

    def test_distinct_broker_snapshot_fields(self):
        html=HTML.read_text(encoding='utf-8')
        js=JS.read_text(encoding='utf-8')
        for key in ('accountCashBuyingPower','accountHoldingsValue','accountSnapshotNote'):
            self.assertEqual(html.count('id="'+key+'"'),1)
            self.assertIn("$('"+key+"')",js)
        self.assertIn('CASH-ONLY BUYING POWER',html)
        self.assertIn('POSITIONS MARKET VALUE',html)
        self.assertIn('Buying power is not added to total account value.',html)
        self.assertIn('money(b.cashBuyingPower)',js)
        self.assertIn('money(b.positionsExposure)',js)
        self.assertIn("b?money(b.balance):'—'",js)

    def test_public_sync_acknowledge_all_control_is_safe_and_confirmed(self):
        html=HTML.read_text(encoding='utf-8')
        js=JS.read_text(encoding='utf-8')
        self.assertIn('id="syncAcknowledgeAll"',html)
        self.assertIn('disabled onclick="acknowledgeAllSyncAlerts()"',html)
        self.assertIn('id="syncAlertCount"',html)
        self.assertIn('async function acknowledgeAllSyncAlerts()',js)
        self.assertIn("api('sync/alerts/acknowledge-all','POST',{})",js)
        self.assertIn("d.openAlertCount",js)
        self.assertIn("if(!confirm('Acknowledge ALL",js)
        self.assertIn("Historical records retained; no trading actions",js)

    def test_protection_percentage_input_range(self):
        html=HTML.read_text(encoding='utf-8')
        self.assertIn('Protected balance (0–99%)',html)
        self.assertIn('id="pct" type="number" min="0" max="99" step="1"',html)
        self.assertNotIn('Protected balance (1–100%)',html)

    def test_no_new_order_execution_or_secret_fields(self):
        app=APP.read_text(encoding='utf-8')
        self.assertIn("'liveTradingAvailable':False",app)
        self.assertIn('0.2.23-offline-durable-safety-rehearsal-inactive',app)
        html=HTML.read_text(encoding='utf-8')
        self.assertNotIn('value="0.15"',html)

if __name__ == '__main__':
    unittest.main()
