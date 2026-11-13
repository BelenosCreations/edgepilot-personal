"""v0.2.93 browser quote acceptance against the actual shipped parser.

Synthetic only. No brokerage request, secret, trading, disk cache or paper fill.
"""
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
JS_FILE = ROOT / "static" / "assets" / "owner-dashboard.js"
JS = JS_FILE.read_text(encoding="utf-8")


class OwnerQuoteBrowserAcceptanceTests(unittest.TestCase):
    def test_manual_only_with_clear_nonsecret_denial(self):
        self.assertIn('el("loadQuote").addEventListener("click"', JS)
        self.assertIn('  }, "quote"));', JS)
        self.assertIn('Public quote request unavailable (HTTP ', JS)
        self.assertIn('quoteSpread', JS)
        self.assertIn('Fresh at receipt is not a live/current price guarantee.', JS)
        self.assertNotIn('quoteHistory', JS)
        self.assertIn('Quote response could not be verified by the browser.', JS)
        for bad in ("localStorage", "sessionStorage", "indexedDB", "document.cookie",
                    "setInterval(", "setTimeout(", "innerHTML"):
            self.assertNotIn(bad, JS)
        self.assertEqual(JS.count('"/api/identity/public/read/accounts/" +'), 3)

    @unittest.skipUnless(shutil.which("node"), "Node is required for real JS execution")
    def test_actual_browser_quote_parser_accepts_valid_utc_public_timestamp(self):
        script = r"""
const assert=require('node:assert/strict');
const fs=require('node:fs');
const js=fs.readFileSync(process.argv[1],'utf8');
const begin=js.indexOf('  const readSourcePrice = raw => {');
const end=js.indexOf('  function clearMarketResearch() {',begin);
assert.ok(begin>0 && end>begin);
const parser=Function('quotePricePattern',js.slice(begin,end)+
 '\nreturn {readSourceTime,validateQuote,quotedSpread};')(
 /^(?:0|[1-9]\d{0,11})(?:\.\d{1,12})?$/
);
assert.equal(parser.readSourceTime('2026-11-12T20:00:00+00:00'),
 '2026-11-12T20:00:00+00:00');
assert.equal(parser.readSourceTime('2026-11-12T20:00:00Z'),
 '2026-11-12T20:00:00Z');
for(const invalid of ['no-date','not-a-date','2026-13-99T20:00:00Z',42])
 assert.throws(()=>parser.readSourceTime(invalid));
const id='00000000-0000-0000-0000-000000000001';
const p={
 accountId:id, symbol:'MSFT', assetClass:'EQUITY', provider:'Public API',
 sourceReportedOnly:true,readOnly:true,cacheRightsVerified:false,
 paperFillEligible:false,executable:false,ordersEnabled:false,
 transfersEnabled:false,lastFresh:true,twoSidedFresh:false,
 last:'200.13',lastTimestamp:'2026-11-12T20:00:00+00:00',
 receivedAt:'2026-11-12T20:00:02+00:00',
 bid:'200.11',ask:'200.15',bidTimestamp:null,askTimestamp:null
};
const q=parser.validateQuote(p,id,'MSFT','EQUITY');
assert.equal(q.last,'200.13');
assert.equal(q.bid,'200.11');
assert.equal(q.bidAt,'timestamp unavailable');
assert.equal(q.askAt,'timestamp unavailable');
assert.equal(q.twoSidedFresh,false);
assert.equal(q.spread,'Unavailable');
assert.throws(()=>parser.validateQuote({...p,twoSidedFresh:true},id,'MSFT','EQUITY'));
const verified={...p,twoSidedFresh:true,
 bidTimestamp:'2026-11-12T20:00:01Z',
 askTimestamp:'2026-11-12T20:00:01Z'};
assert.equal(parser.validateQuote(verified,id,'MSFT','EQUITY').spread,
 '0.04 price units');
assert.equal(parser.quotedSpread('0.000000000001','0.000000000003',true),
 '0.000000000002 price units');
assert.equal(parser.quotedSpread('100.10','100.10',true),'0 price units');
assert.equal(parser.quotedSpread('100.10','100.15',false),'Unavailable');
assert.throws(()=>parser.quotedSpread('100.15','100.10',true));
assert.throws(()=>parser.validateQuote({...p,accountId:'cross-account'},id,'MSFT','EQUITY'));
assert.throws(()=>parser.validateQuote({...p,paperFillEligible:true},id,'MSFT','EQUITY'));
assert.throws(()=>parser.validateQuote({...p,lastTimestamp:'invalid'},id,'MSFT','EQUITY'));
assert.throws(()=>parser.validateQuote({...p,assetClass:'CRYPTO'},id,'MSFT','EQUITY'));
"""
        proc=subprocess.run(
            ["node","-e",script,str(JS_FILE)],
            check=False,capture_output=True,text=True,timeout=15
        )
        self.assertEqual(proc.returncode,0,proc.stderr)


if __name__=="__main__":
    unittest.main()
