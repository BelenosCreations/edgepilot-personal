"use strict";
(() => {
  const el = id => document.getElementById(id);
  let ownerSession = null;
  let revision = 0;
  let busy = false;

  const accountIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  const symbolPattern = /^[A-Za-z0-9.^_-]{1,30}$/;
  const moneyPattern = /^\d+(?:\.\d{1,2})?$/;
  const unitsPattern = /^-?\d+(?:\.\d{1,18})?$/;

  const setStatus = (message, error = false) => {
    el("status").textContent = message;
    el("status").classList.toggle("error", !!error);
  };
  const money = raw => {
    if (typeof raw !== "string" || raw.length > 40 || !moneyPattern.test(raw))
      throw new Error("Public value format was not accepted");
    const [whole, fractional = ""] = raw.split(".");
    return "$" + whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",") +
      "." + (fractional + "00").slice(0, 2);
  };
  const quantity = raw => {
    if (typeof raw !== "string" || raw.length > 64 || !unitsPattern.test(raw))
      throw new Error("Public position units could not be verified");
    return raw;
  };
  async function api(path, method = "GET", csrf = "") {
    const headers = method === "POST"
      ? {"Content-Type":"application/json", "X-Edge-Identity-CSRF":csrf} : {};
    const response = await fetch(path, {
      method,
      headers,
      credentials:"same-origin",
      cache:"no-store",
      body:method === "POST" ? "{}" : undefined
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error("EdgePilot secure request unavailable");
      error.status = response.status;
      throw error;
    }
    return result;
  }
  function clearSnapshot() {
    revision += 1;
    el("portfolioValue").textContent = "Not loaded";
    el("portfolioPositions").textContent = "Not loaded";
    el("positions").replaceChildren();
    el("snapshotTime").textContent = "No snapshot loaded. Values are not automatically refreshed.";
    el("intro").textContent = "No brokerage balances have been requested in this session.";
  }
  function clearIdentity() {
    ownerSession = null;
    clearSnapshot();
    el("dashboard").hidden = true;
    el("signedOut").hidden = false;
    el("accountChoice").replaceChildren();
    el("loadPortfolio").disabled = true;
  }
  function validatePortfolio(data, selectedId) {
    if (!data || data.accountId !== selectedId ||
        data.readOnly !== true || data.ordersEnabled !== false ||
        data.transfersEnabled !== false ||
        !Array.isArray(data.holdings) || data.holdings.length > 100)
      throw new Error("Public read-only account response rejected");
    const value = money(data.balance);
    const positions = data.holdings.map(position => {
      if (!position || typeof position.symbol !== "string" ||
          !symbolPattern.test(position.symbol))
        throw new Error("Unverified Public position");
      return {
        symbol:position.symbol,
        quantity:quantity(position.quantity),
        value:money(position.currentValue)
      };
    });
    return {value, positions};
  }
  async function refreshAccounts() {
    const stamp = ++revision;
    el("accountChoice").replaceChildren();
    el("loadPortfolio").disabled = true;
    clearSnapshot();
    const current = revision;
    const data = await api("/api/identity/accounts");
    if (stamp > current || current !== revision || !ownerSession) return;
    if (!data || data.readOnly !== true || data.discoveryOnlyPilot !== true ||
        !Array.isArray(data.accounts) ||
        typeof data.soloOwnerPortfolioAvailable !== "boolean") {
      throw new Error("Account scope response rejected");
    }
    if (data.soloOwnerPortfolioAvailable !== true) {
      setStatus("Owner read-only portfolio access is not available. Use Account & connections to review your profile.");
      return;
    }
    const available = data.accounts.map(account => {
      const id = account && (account.account_id || account.accountId);
      if (typeof id !== "string" || !accountIdPattern.test(id))
        throw new Error("Verified account identifier unavailable");
      return {id, label:typeof account.label === "string" ?
        account.label.slice(0, 72) : "Public brokerage account"};
    });
    if (current !== revision) return;
    if (!available.length) {
      setStatus("No verified Public brokerage account is linked. Add one under Account & connections.");
      return;
    }
    for (const account of available) {
      const option = document.createElement("option");
      option.value = account.id;
      option.textContent = account.label;
      el("accountChoice").appendChild(option);
    }
    el("loadPortfolio").disabled = false;
    setStatus("Verified account found. Select Retrieve read-only snapshot to contact Public.");
  }
  async function run(action) {
    if (busy) return;
    busy = true;
    el("reloadAccounts").disabled = true;
    el("loadPortfolio").disabled = true;
    el("signOut").disabled = true;
    try {
      await action();
    } catch (error) {
      if (error.status === 401) {
        clearIdentity();
        setStatus("Session expired. Sign in again through EdgePilot Accounts.", true);
      } else {
        setStatus("Read-only request unavailable. No trading or transfer was attempted.", true);
      }
    } finally {
      busy = false;
      el("reloadAccounts").disabled = false;
      el("signOut").disabled = false;
      el("loadPortfolio").disabled =
        !ownerSession || !accountIdPattern.test(el("accountChoice").value);
    }
  }
  el("accountChoice").addEventListener("change", () => {
    clearSnapshot();
    setStatus("Account changed. Request a new read-only snapshot to view its value.");
  });
  el("reloadAccounts").addEventListener("click", () => run(refreshAccounts));
  el("loadPortfolio").addEventListener("click", () => run(async () => {
    const id = el("accountChoice").value;
    if (!ownerSession || !accountIdPattern.test(id))
      throw new Error("Select a linked Public account");
    clearSnapshot();
    const current = revision;
    el("intro").textContent = "Requesting the current Public account snapshot…";
    const response = await api("/api/identity/public/read/accounts/" +
      encodeURIComponent(id) + "/portfolio");
    if (revision !== current || !ownerSession || el("accountChoice").value !== id) return;
    const snapshot = validatePortfolio(response, id);
    if (revision !== current || !ownerSession) return;
    const rows = snapshot.positions.map(position => {
      const li = document.createElement("li");
      const left = document.createElement("div");
      const symbol = document.createElement("div");
      symbol.className = "position-name";
      symbol.textContent = position.symbol;
      const units = document.createElement("div");
      units.className = "position-units";
      units.textContent = "Quantity: " + position.quantity + " units";
      left.append(symbol, units);
      const value = document.createElement("span");
      value.className = "position-value";
      value.textContent = position.value;
      li.append(left, value);
      return li;
    });
    if (!rows.length) {
      const item = document.createElement("li");
      item.textContent = "Public reported no open positions; account value may include cash.";
      rows.push(item);
    }
    el("positions").replaceChildren(...rows);
    el("portfolioValue").textContent = snapshot.value;
    el("portfolioPositions").textContent = String(snapshot.positions.length);
    el("intro").textContent = "Public-reported account snapshot for the selected verified account.";
    el("snapshotTime").textContent =
      "Retrieved " + new Date().toLocaleString() +
      " on this device; not a market quote timestamp. Read-only, no orders or transfers.";
    setStatus("Read-only Public portfolio retrieved. No trade or bank action occurred.");
  }));
  el("signOut").addEventListener("click", () => run(async () => {
    const csrf = ownerSession && ownerSession.csrf;
    try { await api("/api/identity/logout", "POST", csrf); }
    finally { clearIdentity(); }
    setStatus("Signed out of your independent EdgePilot account.");
  }));
  window.addEventListener("pagehide", clearSnapshot);
  (async () => {
    try {
      const session = await api("/api/identity/session");
      if (!session || session.ok !== true || !session.user ||
          session.user.role !== "owner" ||
          typeof session.user.userId !== "string" ||
          typeof session.csrf !== "string") {
        clearIdentity();
        setStatus("Only the independently authenticated EdgePilot owner can open this pilot dashboard.");
        return;
      }
      ownerSession = {csrf:session.csrf};
      el("signedOut").hidden = true;
      el("dashboard").hidden = false;
      await run(refreshAccounts);
    } catch (error) {
      clearIdentity();
      setStatus("Sign in to your independent EdgePilot owner account to continue.", error.status !== 401);
    }
  })();
})();
