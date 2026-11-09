"""v0.2 responsive controls and safety boundary regression tests."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HTML=(ROOT/'backend/static/index.html').read_text(encoding='utf-8')
JS=(ROOT/'backend/static/assets/app.js').read_text(encoding='utf-8')
APP=(ROOT/'backend/app.py').read_text(encoding='utf-8')

class AutomationDashboardTests(unittest.TestCase):
    def test_command_center_has_three_modes_but_live_locked(self):
        self.assertIn('id="automationCommandCenter"',HTML)
        self.assertIn('<option value="live" disabled>',HTML)
        self.assertIn('id="automationRiskLevel"',HTML)
        self.assertIn('id="automationPaperCapital"',HTML)
        self.assertIn('id="automationEmergencyReset"',HTML)
        self.assertIn('id="automationPerformance"',HTML)
        self.assertIn('id="paperExposure"',HTML)

    def test_auto_is_continuous_with_three_independent_loss_limits(self):
        section=HTML.split('<section class="section" id="auto">',1)[1].split('</section>',1)[0]
        self.assertNotIn('id="autoMaxTrades"',section)
        self.assertNotIn('Maximum trades per session',section)
        for key in ('autoRollingLoss','autoStockLoss','autoCryptoLoss','autoMaxOpen'):
            self.assertIn('id="'+key+'"',section)
        self.assertIn('Continuous',section)
        self.assertNotIn("max_trades:'autoMaxTrades'",JS)
        for key in ('rolling_loss_stop','stock_loss_stop','crypto_loss_stop'):
            self.assertIn(key+':',JS)

    def test_safe_manual_engine_controls_and_navigation(self):
        for engine in ('auto','micro','fifteen'):
            section=HTML.split('<section class="section" id="'+engine+'">',1)[1].split('</section>',1)[0]
            self.assertIn('automationEngineAction(\''+engine+'\',\'start\')',section)
            self.assertIn('automationEngineAction(\''+engine+'\',\'pause\')',section)
        self.assertIn("confirmation:mode==='paper'?'START PAPER':'START OBSERVE'",JS)
        self.assertIn("api('automation/emergency/reset','POST'",JS)
        self.assertIn("api('automation/status')",JS)
        self.assertIn('function saveAutomationMaster()',JS)
        self.assertIn('function loadAutomationStatus(',JS)

    def test_real_money_orders_remain_physically_disabled(self):
        self.assertIn("raise ValueError('Real-money execution disabled: broker fill reconciliation incomplete')",APP)
        self.assertIn("return {'settings':settings(),'broker':b",APP)
        self.assertIn("'liveTradingAvailable':False",APP)
        self.assertIn('automation_worker.start_web_worker',APP)

if __name__=='__main__':
    unittest.main()
