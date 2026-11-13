"""Execute the shipped owner history UI against synthetic HTTP replies."""
from pathlib import Path
import shutil
import subprocess
import unittest


JS_FILE = Path(__file__).resolve().parents[1] / "static/assets/owner-dashboard.js"


@unittest.skipUnless(shutil.which("node"), "Node is required for real JS execution")
class OwnerHistoryBrowserTests(unittest.TestCase):
    def test_history_scope_and_failures_use_the_current_selection_only(self):
        script = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
class Element {
  value = "";
  textContent = "";
  children = [];
  handlers = {};
  classList = {toggle() {}};
  addEventListener(name, handler) { this.handlers[name] = handler; }
  replaceChildren(...children) { this.children = children; }
  appendChild(child) { this.children.push(child); }
  fire(name) { return this.handlers[name](); }
}
const elements = new Map();
function el(id) {
  if (!elements.has(id)) elements.set(id, new Element());
  return elements.get(id);
}
const id = "00000000-0000-0000-0000-000000000001";
const otherId = "00000000-0000-0000-0000-000000000002";
const reply = (status, data) => ({ok: status === 200, status, json: async () => data});
const timestamp = "2026-11-12T19:00:00Z";
const result = period => ({
  accountId: id, provider: "Public API", source: "Get bars v2", symbol: "MSFT",
  assetClass: "EQUITY", period, receivedAt: timestamp, sourceExpectedBars: 12,
  readOnly: true, dataPersisted: false, ordersEnabled: false, transfersEnabled: false,
  paperFillEligible: false, barCount: 1,
  bars: [{timestamp, open: "200.01", high: "201.25", low: "199.95",
          close: "201.10", volume: "100"}]
});
const pending = [];
const windowHandlers = {};
const fetch = async (path, options) => {
  assert.equal(options.cache, "no-store");
  if (path === "/api/identity/session")
    return reply(200, {ok: true, csrf: "synthetic", user: {role: "owner", userId: id}});
  if (path === "/api/identity/accounts")
    return reply(200, {readOnly: true, discoveryOnlyPilot: true,
                       soloOwnerPortfolioAvailable: true,
                       accounts: [{accountId: id}, {accountId: otherId}]});
  assert.equal(path, "/api/identity/public/read/accounts/" + el("accountChoice").value +
                    "/market-history");
  assert.equal(options.method, "POST");
  assert.equal(options.headers["X-Edge-Identity-CSRF"], "synthetic");
  return new Promise(resolve => pending.push({resolve, payload: JSON.parse(options.body)}));
};
vm.runInNewContext(fs.readFileSync(process.argv[1], "utf8"), {
  document: {getElementById: el, createElement: () => new Element()},
  window: {addEventListener(name, handler) { windowHandlers[name] = handler; }}, fetch
});
(async () => {
  await new Promise(resolve => setImmediate(resolve));
  el("accountChoice").value = id;
  el("quoteSymbol").value = "msft";
  el("quoteType").value = "EQUITY";
  el("historyPeriod").value = "WEEK";
  const week = el("loadHistory").fire("click");
  assert.deepEqual(pending[0].payload, {symbol: "MSFT", type: "EQUITY", period: "WEEK"});
  pending.shift().resolve(reply(200, result("WEEK")));
  await week;
  assert.match(el("historyEvidence").textContent, /Public API · MSFT · One week · 1 displayed bar · 12 expected/);
  assert.equal(el("historyTable").hidden, false);
  assert.equal(el("historyRows").children[0].children[4].textContent, "201.10");

  const obsolete = el("loadHistory").fire("click");
  el("historyPeriod").value = "MONTH";
  el("historyPeriod").fire("change");
  assert.equal(el("historyTable").hidden, true);
  pending.shift().resolve(reply(503, {privateDiagnostic: "ignore me"}));
  await obsolete;
  assert.equal(el("historyEvidence").textContent, "No history loaded.");
  assert.doesNotMatch(el("status").textContent, /503/);

  const month = el("loadHistory").fire("click");
  assert.equal(pending[0].payload.period, "MONTH");
  pending.shift().resolve(reply(200, result("MONTH")));
  await month;
  assert.match(el("historyEvidence").textContent, /MSFT · One month/);

  const stale = el("loadHistory").fire("click");
  el("historyPeriod").value = "WEEK";
  el("historyPeriod").fire("change");
  pending.shift().resolve(reply(200, result("MONTH")));
  await stale;
  assert.equal(el("historyTable").hidden, true);
  assert.equal(el("historyRows").children.length, 0);

  const previousAccount = el("loadHistory").fire("click");
  el("accountChoice").value = otherId;
  el("accountChoice").fire("change");
  pending.shift().resolve(reply(200, result("WEEK")));
  await previousAccount;
  assert.equal(el("historyTable").hidden, true);
  assert.equal(el("historyRows").children.length, 0);

  const currentAccount = el("loadHistory").fire("click");
  pending.shift().resolve(reply(200, {...result("WEEK"), accountId: otherId}));
  await currentAccount;
  assert.equal(el("historyTable").hidden, false);
  windowHandlers.pagehide();
  assert.equal(el("historyTable").hidden, true);
  assert.equal(el("historyRows").children.length, 0);

  const previousPage = el("loadHistory").fire("click");
  windowHandlers.pagehide();
  pending.shift().resolve(reply(200, {...result("WEEK"), accountId: otherId}));
  await previousPage;
  assert.equal(el("historyTable").hidden, true);
  assert.equal(el("historyEvidence").textContent, "No history loaded.");
  el("accountChoice").value = id;
  el("accountChoice").fire("change");

  const denied = el("loadHistory").fire("click");
  pending.shift().resolve(reply(404, {privateDiagnostic: "ignore me"}));
  await denied;
  assert.equal(el("historyTable").hidden, true);
  assert.equal(el("historyRows").children.length, 0);
  assert.equal(el("status").textContent, "Public history request unavailable (HTTP 404).");

  const mismatched = el("loadHistory").fire("click");
  pending.shift().resolve(reply(200, result("MONTH")));
  await mismatched;
  assert.equal(el("historyTable").hidden, true);
  assert.equal(el("status").textContent, "Public history response could not be verified.");

  const expired = el("loadHistory").fire("click");
  el("quoteSymbol").fire("input");
  pending.shift().resolve(reply(401, {}));
  await expired;
  assert.equal(el("dashboard").hidden, true);
  assert.match(el("status").textContent, /Session expired/);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        result = subprocess.run(
            ["node", "-e", script, str(JS_FILE)], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
