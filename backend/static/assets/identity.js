"use strict";
(() => {
  let identityCsrf = "";
  let busy = false;
  let identityViewGeneration = 0;
  const el = id => document.getElementById(id);
  const status = (message, error = false) => {
    const box = el("status");
    box.textContent = message;
    box.classList.toggle("error", !!error);
  };
  async function api(path, method = "GET", body, protectedWrite = false) {
    const headers = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (protectedWrite) headers["X-Edge-Identity-CSRF"] = identityCsrf;
    const res = await fetch("/api/identity" + path, {
      method, credentials:"same-origin", cache:"no-store", headers,
      body:body === undefined ? undefined : JSON.stringify(body)
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const error = new Error(typeof data.error === "string" ? data.error : "Secure request unavailable");
      error.status = res.status;
      throw error;
    }
    return data;
  }
  function toBytes(text) {
    if (typeof text !== "string" || !/^[A-Za-z0-9_-]+={0,2}$/.test(text)) throw new Error("Invalid passkey challenge");
    const base = text.replace(/-/g, "+").replace(/_/g, "/");
    const bytes = atob(base + "=".repeat((4 - base.length % 4) % 4));
    return Uint8Array.from(bytes, character => character.charCodeAt(0));
  }
  function toUrl64(buffer) {
    const bytes = new Uint8Array(buffer);
    let raw = "";
    for (let i=0; i<bytes.length; i++) raw += String.fromCharCode(bytes[i]);
    return btoa(raw).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  }
  function optionsForBrowser(obj, registration) {
    if (!obj || typeof obj !== "object" || typeof obj.challenge !== "string")
      throw new Error("Invalid passkey request");
    const options = {...obj, challenge:toBytes(obj.challenge)};
    if (registration) {
      if (!options.user || typeof options.user.id !== "string")
        throw new Error("Invalid passkey user");
      options.user = {...options.user, id:toBytes(options.user.id)};
      if (Array.isArray(options.excludeCredentials)) {
        options.excludeCredentials = options.excludeCredentials.map(x => ({...x,id:toBytes(x.id)}));
      }
    } else if (Array.isArray(options.allowCredentials)) {
      options.allowCredentials = options.allowCredentials.map(x => ({...x,id:toBytes(x.id)}));
    }
    return options;
  }
  function publicCredential(credential) {
    if (!credential || !credential.rawId || !credential.response) throw new Error("Passkey response unavailable");
    if (typeof credential.toJSON === "function") return credential.toJSON();
    const response = credential.response;
    const payload = {id:credential.id, rawId:toUrl64(credential.rawId), type:credential.type,
      clientExtensionResults:typeof credential.getClientExtensionResults === "function" ?
        credential.getClientExtensionResults() : {}, response:{
        clientDataJSON:toUrl64(response.clientDataJSON)
      }
    };
    if (response.attestationObject) {
      payload.response.attestationObject = toUrl64(response.attestationObject);
      if (typeof response.getTransports === "function") payload.response.transports = response.getTransports();
    } else {
      payload.response.authenticatorData = toUrl64(response.authenticatorData);
      payload.response.signature = toUrl64(response.signature);
      payload.response.userHandle = response.userHandle ? toUrl64(response.userHandle) : null;
    }
    return payload;
  }
  const supported = () => window.isSecureContext && typeof navigator.credentials === "object";
  function showLoggedOut() {
    identityCsrf = "";
    el("authPane").hidden = false;
    el("accountPane").hidden = true;
    el("passkeySignIn").disabled = !supported();
    el("loginPassword").value = "";
    el("newPassword").value = "";
    el("publicSecret").value = "";
    el("replacementSecret").value = "";
    clearReadOnly();
  }
  function clearReadOnly() {
    // Invalidate pending fetches from a previous identity before clearing DOM.
    identityViewGeneration += 1;
    el("connections").replaceChildren();
    el("connectionChoice").replaceChildren();
    el("discoveredAccounts").replaceChildren();
    el("linkedAccounts").replaceChildren();
    el("holdings").replaceChildren();
    el("discoveryInfo").textContent = "";
    el("portfolioSummary").textContent = "";
    el("monitorPlanInfo").textContent = "";
    el("connectionInfo").textContent = "";
    el("replacementSecret").value = "";
  }
  async function showSession() {
    const startedGeneration = identityViewGeneration;
    const data = await api("/session");
    if (startedGeneration !== identityViewGeneration) return;
    identityCsrf = data.csrf;
    el("authPane").hidden = true;
    el("accountPane").hidden = false;
    el("welcome").textContent = "Welcome, " + (data.user && data.user.label || "EdgePilot user");
    el("addPasskey").disabled = !supported();
    clearReadOnly();
    status("Secure EdgePilot account session active. Brokerage execution remains disabled.");
    await loadConnections();
    await loadLinkedAccounts();
  }
  async function loadConnections() {
    const generation = identityViewGeneration;
    const items = el("connections");
    const select = el("connectionChoice");
    items.replaceChildren();
    select.replaceChildren();
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "Choose your connection";
    select.appendChild(blank);
    try {
      const data = await api("/public/connections");
      if (generation !== identityViewGeneration) return;
      if (!Array.isArray(data.connections) || data.secretsReturned !== false) {
        throw new Error("Unexpected connection response");
      }
      for (const item of data.connections) {
        const id = String(item.connectionId || "");
        const entry = document.createElement("li");
        entry.textContent = "Encrypted Public connection ending " + id.slice(-6) + " — " + String(item.status);
        items.appendChild(entry);
        if (item.status !== "revoked") {
          const option = document.createElement("option");
          option.value = id;
          option.textContent = "Public connection ending " + id.slice(-6);
          select.appendChild(option);
        }
      }
      el("connectionInfo").textContent = items.children.length ?
        "Encrypted connections belonging to your account:" : "No Public key saved for this account.";
    } catch (error) {
      if (generation !== identityViewGeneration) return;
      items.replaceChildren();
      el("connectionInfo").textContent = "Public key setup is not enabled for this account yet.";
    }
  }
  async function loadLinkedAccounts() {
    const generation = identityViewGeneration;
    const items = el("linkedAccounts");
    items.replaceChildren();
    el("holdings").replaceChildren();
    el("portfolioSummary").textContent = "";
    el("monitorPlanInfo").textContent = "";
    try {
      const data = await api("/accounts");
      if (generation !== identityViewGeneration) return;
      if (data.readOnly !== true || !Array.isArray(data.accounts)) {
        throw new Error("Invalid read-only account list");
      }
      if (data.accounts.length === 0) {
        el("portfolioSummary").textContent = "No verified Public accounts are linked yet.";
      }
      for (const account of data.accounts) {
        // The existing tenant storage endpoint returns account_id. The
        // provider read-only endpoint uses accountId. Never infer an account
        // from the legacy global selected-account value.
        const id = account.accountId || account.account_id;
        if (typeof id !== "string" ||
            !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id)) {
          throw new Error("Invalid scoped account identifier");
        }
        const li = document.createElement("li");
        li.appendChild(document.createTextNode(String(account.label || "Public account") + " "));
        const listInput = document.createElement("input");
        listInput.type = "text";
        listInput.maxLength = 512;
        listInput.autocomplete = "off";
        listInput.autocapitalize = "characters";
        listInput.placeholder = "Symbols: SPY,QQQ (max 25)";
        listInput.setAttribute("aria-label", "Watchlist symbols for " + String(account.label || "Public account"));
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "View read-only portfolio";
        button.addEventListener("click", () => action(async () => {
          const requestGeneration = identityViewGeneration;
          const portfolio = await api("/public/read/accounts/" + encodeURIComponent(id) + "/portfolio");
          if (requestGeneration !== identityViewGeneration) return;
          if (portfolio.readOnly !== true || portfolio.ordersEnabled !== false ||
              portfolio.transfersEnabled !== false || portfolio.accountId !== id ||
              !Array.isArray(portfolio.holdings)) {
            throw new Error("Portfolio response rejected");
          }
          el("portfolioSummary").textContent = String(account.label || "Public account") +
            " · Public-reported value: " + String(portfolio.balance) +
            " · read-only, no orders or transfers";
          const holdings = el("holdings");
          holdings.replaceChildren();
          for (const position of portfolio.holdings) {
            const item = document.createElement("li");
            item.textContent = String(position.symbol) + " · " + String(position.quantity) +
              " shares · value " + String(position.currentValue);
            holdings.appendChild(item);
          }
        }));
        li.appendChild(button);
        const previewButton = document.createElement("button");
        previewButton.type = "button";
        previewButton.textContent = "Preview inactive monitor";
        previewButton.addEventListener("click", () => action(async () => {
          const requestGeneration = identityViewGeneration;
          const plan = await api("/accounts/" + encodeURIComponent(id) + "/monitor/preview");
          if (requestGeneration !== identityViewGeneration) return;
          if (plan.accountId !== id || plan.readOnly !== true ||
              plan.simulatedPlanOnly !== true || plan.mode !== "observe" ||
              plan.scheduled !== false || plan.workerActive !== false ||
              plan.brokerRequestsAllowed !== false || plan.paperEnabled !== false ||
              plan.liveTradingEnabled !== false || !Array.isArray(plan.watchlist)) {
            throw new Error("Inactive monitor plan rejected");
          }
          el("monitorPlanInfo").textContent = String(account.label || "Public account") +
            " · watchlist: " + (plan.watchlist.join(", ") || "none") +
            " · inactive preview only; no scans, broker requests or orders";
          listInput.value = plan.watchlist.join(", ");
        }));
        li.appendChild(previewButton);
        li.appendChild(listInput);
        const saveWatchlist = document.createElement("button");
        saveWatchlist.type = "button";
        saveWatchlist.textContent = "Save account watchlist";
        saveWatchlist.addEventListener("click", () => action(async () => {
          const requestGeneration = identityViewGeneration;
          const raw = listInput.value.trim();
          const symbols = raw === "" ? [] : raw.split(",").map(s => s.trim().toUpperCase());
          if (symbols.length > 25 || symbols.some(s => !/^[A-Z][A-Z0-9.-]{0,14}$/.test(s)) ||
              new Set(symbols).size !== symbols.length) {
            throw new Error("Use up to 25 unique comma-separated ticker symbols.");
          }
          const saved = await api("/accounts/" + encodeURIComponent(id) + "/monitor/watchlist",
            "PUT", {symbols}, true);
          if (requestGeneration !== identityViewGeneration) return;
          if (saved.accountId !== id || saved.saved !== true ||
              saved.readOnlyMonitoring !== true || saved.workerActive !== false ||
              saved.brokerRequestsAllowed !== false || saved.paperEnabled !== false ||
              saved.liveTradingEnabled !== false || saved.fundTransfersEnabled !== false ||
              !Array.isArray(saved.watchlist)) {
            throw new Error("Watchlist update response rejected");
          }
          listInput.value = saved.watchlist.join(", ");
          el("monitorPlanInfo").textContent = String(account.label || "Public account") +
            " · watchlist saved for inactive monitoring only: " +
            (saved.watchlist.join(", ") || "none");
          status("Watchlist saved for your selected EdgePilot account. No scans or orders started.");
        }));
        li.appendChild(saveWatchlist);
        items.appendChild(li);
      }
    } catch (error) {
      if (generation !== identityViewGeneration) return;
      el("portfolioSummary").textContent = "Read-only Public account viewing is not enabled for this user yet.";
    }
  }
  async function discoverPublicAccounts() {
    const generation = identityViewGeneration;
    const connectionId = el("connectionChoice").value;
    if (!connectionId) throw new Error("Choose one of your encrypted Public connections first.");
    el("discoveredAccounts").replaceChildren();
    const discovered = await api("/public/read/connections/" +
      encodeURIComponent(connectionId) + "/accounts");
    if (generation !== identityViewGeneration) return;
    if (discovered.readOnly !== true || discovered.ordersEnabled !== false ||
        discovered.connectionId !== connectionId || !Array.isArray(discovered.accounts)) {
      throw new Error("Public account discovery response rejected");
    }
    el("discoveryInfo").textContent = discovered.accounts.length ?
      "Select an account to verify and link read-only:" : "Public reported no accounts for this key.";
    for (const account of discovered.accounts) {
      const providerId = String(account.accountId);
      const type = String(account.accountType || "Public");
      const li = document.createElement("li");
      li.appendChild(document.createTextNode(type + " account ending " + providerId.slice(-4) + " "));
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Link read-only";
      button.addEventListener("click", () => action(async () => {
        const requestGeneration = identityViewGeneration;
        const label = ("Public " + type).slice(0,64);
        const result = await api("/public/read/connections/" +
          encodeURIComponent(connectionId) + "/accounts","POST",
          {accountId:providerId,label},true);
        if (requestGeneration !== identityViewGeneration) return;
        if (result.verifiedByPublic !== true || result.readOnly !== true ||
            result.ordersEnabled !== false) throw new Error("Public account link not verified");
        status("Your Public account was verified and linked read-only.");
        await loadLinkedAccounts();
      }));
      li.appendChild(button);
      el("discoveredAccounts").appendChild(li);
    }
  }
  function chosenConnectionId() {
    const id = el("connectionChoice").value;
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id)) {
      throw new Error("Choose your own saved Public connection first.");
    }
    return id;
  }
  async function refreshAfterCredentialChange() {
    clearReadOnly();
    await loadConnections();
    await loadLinkedAccounts();
  }
  async function action(work) {
    if (busy) return;
    busy = true;
    for (const button of document.querySelectorAll("button")) button.disabled = true;
    try { await work(); }
    catch (error) { status(error && error.message || "Request unavailable", true); }
    finally {
      busy = false;
      for (const button of document.querySelectorAll("button")) button.disabled = false;
      if (!supported()) {
        el("passkeySignIn").disabled = true;
        el("addPasskey").disabled = true;
      }
    }
  }
  el("loginForm").addEventListener("submit", event => {
    event.preventDefault();
    action(async () => {
      const username = el("loginUser").value.trim();
      const password = el("loginPassword").value;
      try {
        clearReadOnly();
        const result = await api("/login","POST",{username,password});
        identityCsrf = result.csrf;
        await showSession();
      } finally { el("loginPassword").value = ""; }
    });
  });
  el("registerForm").addEventListener("submit", event => {
    event.preventDefault();
    action(async () => {
      const invitation=el("invite").value, username=el("newUser").value.trim();
      const password=el("newPassword").value, displayName=el("newDisplay").value.trim();
      try {
        await api("/register","POST",{invitation,username,password,displayName});
        status("Your EdgePilot account was created. Sign in using your new username and password.");
        el("loginUser").value = username;
        el("invite").value = "";
      } finally { el("newPassword").value = ""; }
    });
  });
  el("passkeySignIn").addEventListener("click", () => action(async () => {
    if (!supported()) throw new Error("Passkeys are not supported by this device or browser.");
    clearReadOnly();
    const begin = await api("/passkeys/authenticate/options","POST",{});
    const credential = await navigator.credentials.get({
      publicKey:optionsForBrowser(begin.publicKey,false)
    });
    if (!credential) throw new Error("Passkey sign-in cancelled");
    const session = await api("/passkeys/authenticate/finish","POST",{
      requestId:begin.requestId,credential:publicCredential(credential)
    });
    identityCsrf = session.csrf;
    await showSession();
  }));
  el("addPasskey").addEventListener("click", () => action(async () => {
    if (!supported()) throw new Error("Passkeys are not supported by this device or browser.");
    const begin = await api("/passkeys/register/options","POST",{},true);
    const credential = await navigator.credentials.create({
      publicKey:optionsForBrowser(begin.publicKey,true)
    });
    if (!credential) throw new Error("Passkey creation cancelled");
    await api("/passkeys/register/finish","POST",{
      requestId:begin.requestId,credential:publicCredential(credential)
    },true);
    status("Your passkey was registered. You can use your device's credential provider to sign in.");
  }));
  el("publicKeyForm").addEventListener("submit", event => {
    event.preventDefault();
    action(async () => {
      const secret=el("publicSecret").value;
      try {
        if (secret.length < 20) throw new Error("Enter your own Public API key.");
        await api("/public/connections","POST",{secret},true);
        status("Public key saved under your encrypted EdgePilot account. Trading is disabled.");
        await loadConnections();
      } finally { el("publicSecret").value = ""; }
    });
  });
  el("rotatePublicSecret").addEventListener("click", () => action(async () => {
    const connectionId = chosenConnectionId();
    const generation = identityViewGeneration;
    const secret = el("replacementSecret").value;
    try {
      if (secret.length < 20 || secret.length > 2048 ||
          /[\r\n\x00]/.test(secret)) {
        throw new Error("Enter a valid replacement Public API secret.");
      }
      if (!window.confirm("Replace the saved secret for this connection? Existing linked Public accounts will need verification again.")) return;
      const result = await api("/public/connections/" +
        encodeURIComponent(connectionId) + "/rotate", "POST", {secret}, true);
      if (generation !== identityViewGeneration) return;
      if (result.status !== "stored_unverified" ||
          result.boundAccountsDisabled !== true ||
          result.secretsReturned !== false || result.realOrdersEnabled !== false) {
        throw new Error("Credential replacement response rejected");
      }
      await refreshAfterCredentialChange();
      status("Public API secret replaced for this EdgePilot account. Linked accounts must be verified again; trading remains disabled.");
    } finally {
      el("replacementSecret").value = "";
    }
  }));
  el("disconnectPublicConnection").addEventListener("click", () => action(async () => {
    const connectionId = chosenConnectionId();
    const generation = identityViewGeneration;
    if (!window.confirm("Disconnect this encrypted Public connection from EdgePilot? Linked accounts will become unavailable. Your brokerage account will not be closed.")) return;
    const result = await api("/public/connections/" +
      encodeURIComponent(connectionId), "DELETE", undefined, true);
    if (generation !== identityViewGeneration) return;
    if (result.status !== "revoked" ||
        result.boundAccountsDisabled !== true ||
        result.secretsReturned !== false || result.realOrdersEnabled !== false) {
      throw new Error("Disconnection response rejected");
    }
    await refreshAfterCredentialChange();
    status("Public connection disconnected from this EdgePilot account. Your Public brokerage account remains open.");
  }));
  el("findPublicAccounts").addEventListener("click", () => action(async () => {
    await discoverPublicAccounts();
  }));
  el("signOut").addEventListener("click", () => action(async () => {
    try { await api("/logout","POST",{},true); }
    finally { showLoggedOut(); }
    status("Signed out of your EdgePilot account.");
  }));
  (async () => {
    try { await showSession(); }
    catch (error) {
      showLoggedOut();
      if (error.status === 404) status("Multi-user EdgePilot accounts are not enabled on this server yet.");
      else if (error.status === 401) status("Sign in, use an existing passkey, or redeem an invitation to create an account.");
      else status("Secure account service is unavailable.",true);
    }
  })();
})();