"""v0.2.91 selected-account owner comparison: offline browser-only evidence.

No real brokerage account, credentials, outbound network, or trading action.
"""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "static/assets/owner-dashboard.js").read_text(encoding="utf-8")
PAGE = (ROOT / "static/owner-dashboard.html").read_text(encoding="utf-8")


class OwnerValueComparisonTests(unittest.TestCase):
    def test_manual_only_and_snapshot_scoped(self):
        for element in ("publicAppValue", "compareValues", "reconcileResult", "reconcileHeading"):
            self.assertIn('id="' + element + '"', PAGE)
        self.assertIn('id="compareValues" type="button" disabled', PAGE)
        self.assertIn('el("compareValues").addEventListener("click"', JS)
        self.assertIn('snapshotAccount !== el("accountChoice").value', JS)
        self.assertIn("snapshotBalance = null;", JS)
        self.assertIn("snapshotAccount = null;", JS)
        self.assertIn('el("publicAppValue").value = "";', JS)
        self.assertIn('el("compareValues").disabled = true;', JS)
        self.assertIn("snapshotBalance = snapshot.rawBalance;", JS)
        self.assertIn("snapshotAccount = id;", JS)
        self.assertIn('el("compareValues").disabled = false;', JS)
        self.assertIn('window.addEventListener("pagehide", clearSnapshot)', JS)
        self.assertIn("not independently verified", JS.lower())
        self.assertIn("not submitted or saved", JS.lower())
        self.assertNotIn('id="tradeButton"', PAGE)
        for forbidden in ("localStorage", "sessionStorage", "indexedDB", "document.cookie",
                          "innerHTML", "setInterval(", "setTimeout("):
            self.assertNotIn(forbidden, JS)
        # The new manual comparison must not introduce additional API access.
        self.assertEqual(JS.count('"/api/identity/public/read/accounts/" +'), 3)

    @unittest.skipUnless(shutil.which("node"), "Node runtime not present")
    def test_exact_cent_math_using_actual_frontend_functions(self):
        script = r"""
const fs=require('node:fs'), assert=require('node:assert/strict');
const js=fs.readFileSync(process.argv[1],'utf8');
const beg=js.indexOf('  const money = raw => {');
const end=js.indexOf('  const quantity = raw => {',beg);
assert.ok(beg>=0 && end>beg);
const part=js.slice(beg,end);
const result=Function('moneyPattern','manualUSDPattern',
  part+' return {money,cents,amountFromCents};')(
    /^\d+(?:\.\d{1,2})?$/,
    /^(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$/
  );
assert.equal(result.cents('0'),0n);
assert.equal(result.cents('0.01'),1n);
assert.equal(result.cents('123.45'),12345n);
assert.equal(result.cents('999999999999.99'),99999999999999n);
assert.equal(result.amountFromCents(12345n),'$123.45');
assert.equal(result.amountFromCents(-1n),'$0.01');
for(const invalid of ['-1','1.234','1e3','1,000','01','12.','', 'NaN',
                     '9999999999999','0.0.1',' 3.00 '])
  assert.throws(()=>result.cents(invalid), /Public app amount/);
assert.equal(result.cents('12.30')-result.cents('12.29'),1n);
"""
        result = subprocess.run(
            ["node", "-e", script, str(ROOT / "static/assets/owner-dashboard.js")],
            capture_output=True, text=True, check=False, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
