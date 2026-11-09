"""Safety regression: automation Start always uses the saved backend mode."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
HTML=(ROOT/'backend/static/index.html').read_text(encoding='utf-8')
JS=(ROOT/'backend/static/assets/app.js').read_text(encoding='utf-8')
APP=(ROOT/'backend/app.py').read_text(encoding='utf-8')


class AutomationSavedModeTests(unittest.TestCase):
    def test_each_engine_has_mode_specific_start_control(self):
        for name in ('auto','micro','fifteen'):
            self.assertEqual(HTML.count('id="automationStart_'+name+'"'),1)
            self.assertIn("automationEngineAction('"+name+"','start')",HTML)
        self.assertNotIn('Start Observe / Paper</button>',HTML)

    def test_unsaved_mode_cannot_start_and_saved_mode_is_visible(self):
        self.assertIn("function updateAutomationStartButtons()",JS)
        self.assertIn("const unsaved=$('automationMode').value!==m.mode",JS)
        self.assertIn("btn.disabled=!!m.emergency||automationSnapshot.engines[name].state==='running'||unsaved",JS)
        self.assertIn("if($('automationMode').value!==m.mode)",JS)
        self.assertIn("Mode change not saved.",JS)
        self.assertIn("'Saved mode: '+m.mode.toUpperCase()",JS)
        self.assertIn("m.mode==='paper'?'Paper':'Observe'",JS)
        self.assertIn("START PAPER",JS)
        self.assertIn("START OBSERVE",JS)

    def test_live_execution_still_hard_blocked(self):
        self.assertIn("Real-money execution disabled: broker fill reconciliation incomplete",APP)
        self.assertIn("'liveTradingAvailable':False",APP)


if __name__=='__main__':
    unittest.main()
