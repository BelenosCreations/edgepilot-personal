"""v0.2.96 exact quote relative-spread research and UTC verification.

Executes the actual shipped browser parser with synthetic observations only.
No real brokerage credentials, HTTP requests, paper fills or orders.
"""
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
JS_FILE = ROOT / "static/assets/owner-dashboard.js"
JS = JS_FILE.read_text(encoding="utf-8")
PAGE = (ROOT / "static/owner-dashboard.html").read_text(encoding="utf-8")


class OwnerRelativeSpreadTests(unittest.TestCase):
    def test_manual_source_only_and_no_paper_capability(self):
        self.assertIn('id="quoteRelativeSpread"', PAGE)
        self.assertIn('el("quoteRelativeSpread").textContent = "Not loaded";', JS)
        self.assertIn('el("quoteRelativeSpread").textContent = q.relativeSpread;', JS)
        self.assertIn("midpoint", PAGE)
        self.assertIn("Fresh at receipt does not mean live now.", PAGE)
        self.assertIn("cacheRightsVerified !== false", JS)
        self.assertIn("paperFillEligible !== false", JS)
        self.assertEqual(JS.count('"/api/identity/public/read/accounts/" +'), 2)
        for banned in ("localStorage", "sessionStorage", "indexedDB",
                       "setInterval(", "setTimeout(", "innerHTML"):
            self.assertNotIn(banned, JS)

    @unittest.skipUnless(shutil.which("node"), "Node runtime required")
    def test_actual_shipped_browser_parser_synthetic_cases(self):
        script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const js = fs.readFileSync(process.argv[1], 'utf8');
const begin = js.indexOf('  const readSourcePrice = raw => {');
const end = js.indexOf('  el("quoteSymbol").addEventListener("input", clearQuote);', begin);
assert.ok(begin > 0 && end > begin);
const functions = Function('quotePricePattern', js.slice(begin, end) +
  '\nreturn {readSourceTime,quotedRelativeSpread,validateQuote};')(
  /^(?:0|[1-9]\d{0,11})(?:\.\d{1,12})?$/
);
const spread = functions.quotedRelativeSpread;
assert.equal(spread('100','101',true), '99.50 bps');
assert.equal(spread('200.11','200.15',true), '2.00 bps');
assert.equal(spread('100.10','100.10',true), '0.00 bps');
assert.equal(spread('0.000000000001','0.000000000003',true),'10000.00 bps');
assert.equal(spread('100.10','100.15',false),'Unavailable');
assert.equal(spread('Not provided by Public','100.15',true),'Unavailable');
assert.throws(() => spread('101','100',true));
assert.throws(() => spread('0','100',true));
assert.equal(functions.readSourceTime('2026-11-12T20:00:00Z'),
  '2026-11-12T20:00:00Z');
assert.equal(functions.readSourceTime('2026-11-12T20:00:00.123456+00:00'),
  '2026-11-12T20:00:00.123456+00:00');
assert.equal(functions.readSourceTime('2024-02-29T20:00:00Z'),
  '2024-02-29T20:00:00Z');
for(const invalid of [
  '2026-11-12T20:00:00', '2026-11-12T20:00:00-05:00',
  '2026-02-29T20:00:00Z', '2026-04-31T20:00:00Z',
  '2026-13-01T20:00:00Z', '2026-11-12T24:00:00Z',
  '2026-11-12T20:60:00Z', '2026-11-12T20:00:61Z',
  '2026-11-12T20:00:00.1234567Z', 0, null, 'not-a-time'
]) assert.throws(() => functions.readSourceTime(invalid), String(invalid));
const id='00000000-0000-0000-0000-000000000001';
const q={accountId:id,symbol:'MSFT',assetClass:'EQUITY',provider:'Public API',
  sourceReportedOnly:true,readOnly:true,cacheRightsVerified:false,
  paperFillEligible:false,executable:false,ordersEnabled:false,
  transfersEnabled:false,lastFresh:false,twoSidedFresh:true,
  last:'200.13',lastTimestamp:'2026-11-12T19:00:00+00:00',
  receivedAt:'2026-11-12T20:00:02+00:00',
  bid:'200.11',ask:'200.15',
  bidTimestamp:'2026-11-12T20:00:01+00:00',
  askTimestamp:'2026-11-12T20:00:01+00:00'};
const result=functions.validateQuote(q,id,'MSFT','EQUITY');
assert.equal(result.spread,'0.04 price units');
assert.equal(result.relativeSpread,'2.00 bps');
assert.equal(result.lastFresh,false);
assert.equal(result.twoSidedFresh,true);
assert.equal(functions.validateQuote({...q,twoSidedFresh:false},id,'MSFT','EQUITY').relativeSpread,'Unavailable');
assert.throws(() => functions.validateQuote({...q,accountId:'another'},id,'MSFT','EQUITY'));
assert.throws(() => functions.validateQuote({...q,paperFillEligible:true},id,'MSFT','EQUITY'));
assert.throws(() => functions.validateQuote({...q,bidTimestamp:null},id,'MSFT','EQUITY'));
"""
        output = subprocess.run(
            ["node", "-e", script, str(JS_FILE)], capture_output=True,
            text=True, check=False, timeout=15)
        self.assertEqual(output.returncode, 0, output.stderr)


if __name__ == "__main__":
    unittest.main()
