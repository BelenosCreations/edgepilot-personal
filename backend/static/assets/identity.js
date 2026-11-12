"use strict";
(() => {
  let identityCsrf = "";
  let busy = false;
  let identityViewGeneration = 0;
  let knownPasskeyCount = null;
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
    el("currentEdgePilotPassword").value = "";
    el("replacementEdgePilotPassword").value = "";
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
    el("deviceSessions").replaceChildren();
    el("deviceSessionStatus").textContent = "";
    knownPasskeyCount = null;
    el("passkeyList").replaceChildren();
    el("passkeyState").textContent = "Checking passkey status…";
    el("passkeyListStatus").textContent = "Checking registered passkeys…";
    el("addPasskey").hidden = true;
    el("addAnotherPasskey").hidden = true;
    el("replacementSecret").value = "";
    // Invitation code is never stored in URLs, storage or logs; erase it
    // on sign-out, identity switch, and every account-panel reset.
    el("familyInviteCode").value = "";
    el("familyInviteCode").type = "password";
    el("familyInviteHelp").textContent = "";
    el("familyInviteResult").hidden = true;
    el("familyInvitationsPane").hidden = true;
    el("revealFamilyInvite").textContent = "Show code";
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
    // Never reveal owner-only invitation actions to members or when the
    // deployment has not explicitly enabled invitation issuance.
    el("familyInvitationsPane").hidden = !(
      data.privateInvitationsAvailable === true &&
      data.user && data.user.role === "owner");
    status("Secure EdgePilot account session active. Brokerage execution remains disabled.");
    await loadPasskeys();
    await loadConnections();
    await loadLinkedAccounts();
    await loadDeviceSessions();
  }
  async function loadPasskeys() {
    const generation = identityViewGeneration;
    const list = el("passkeyList");
    list.replaceChildren();
    el("addPasskey").hidden = true;
    el("addAnotherPasskey").hidden = true;
    el("passkeyState").textContent = "Checking passkey status…";
    el("passkeyListStatus").textContent = "Checking registered passkeys…";
    try {
      const response = await api("/passkeys", "GET", undefined, true);
      if (generation !== identityViewGeneration) return false;
      if (!response || !Array.isArray(response.passkeys) ||
          !Number.isInteger(response.activePasskeys) ||
          response.activePasskeys !== response.passkeys.length ||
          response.activePasskeys < 0 || response.activePasskeys > 12 ||
          response.brokerAccessAuthorized !== false ||
          response.tradingEnabled !== false ||
          response.deviceIdentifiersStored !== false ||
          response.biometricsStoredOnServer !== false) {
        throw new Error("Invalid passkey listing");
      }
      const seen = new Set();
      for (const item of response.passkeys) {
        if (!item || typeof item.credentialId !== "string" ||
            !/^[A-Za-z0-9_-]{22,2731}$/.test(item.credentialId) ||
            seen.has(item.credentialId) ||
            !Number.isInteger(item.createdAt) || item.createdAt < 0 ||
            typeof item.deviceType !== "string" ||
            item.deviceType.length > 48 ||
            typeof item.backedUp !== "boolean") {
          throw new Error("Invalid passkey entry");
        }
        seen.add(item.credentialId);
      }
      const count = response.activePasskeys;
      knownPasskeyCount = count;
      el("passkeyState").textContent = count ?
        "✓ Passkey login enabled — " + count +
        (count === 1 ? " passkey registered" : " passkeys registered") +
        " to your account." :
        "Passkey login is not set up for this EdgePilot account.";
      el("addPasskey").hidden = count !== 0;
      el("addAnotherPasskey").hidden = count === 0;
      el("addPasskey").disabled = !supported();
      el("addAnotherPasskey").disabled = !supported() || count >= 12;
      el("passkeyListStatus").textContent = count ?
        "Registered passkeys: " + count :
        "No passkeys registered yet. Use Set up biometric login above.";
      let position = 0;
      for (const item of response.passkeys) {
        position += 1;
        const row = document.createElement("li");
        const when = new Date(item.createdAt * 1000);
        const dateText = Number.isFinite(when.valueOf()) ?
          when.toLocaleString() : "unknown date";
        row.appendChild(document.createTextNode(
          "Passkey " + position + " · Registered " + dateText + " "));
        const remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = "Remove passkey " + position;
        remove.addEventListener("click", () => action(async () => {
          if (!window.confirm(
            "Remove this passkey? You will be signed out of all sessions " +
            "for this EdgePilot account. Other users are not affected. " +
            "You can still sign in with your password. " +
            "This does not erase the saved passkey from your device.")) return;
          const requestGeneration = identityViewGeneration;
          const revoked = await api("/passkeys/" +
            encodeURIComponent(item.credentialId), "DELETE", undefined, true);
          if (requestGeneration !== identityViewGeneration) return;
          if (revoked.revoked !== true ||
              revoked.otherUsersUnaffected !== true ||
              revoked.identitySessionsRevoked !== true) {
            throw new Error("Passkey removal response rejected");
          }
          // The server revokes every session of this member, including this
          // one. Never retain the old CSRF or show the old account view.
          showLoggedOut();
          status("Passkey removed. All sessions for this account were " +
                 "signed out. Sign in again with your password or another passkey.");
        }));
        row.appendChild(remove);
        list.appendChild(row);
      }
      return true;
    } catch (error) {
      if (generation !== identityViewGeneration) return false;
      knownPasskeyCount = null;
      list.replaceChildren();
      el("addPasskey").hidden = true;
      el("addAnotherPasskey").hidden = true;
      el("passkeyState").textContent = "Passkey status unavailable.";
      el("passkeyListStatus").textContent =
        "Unable to display registered passkeys. No changes were made.";
      return false;
    }
  }
  async function loadDeviceSessions() {
    const generation = identityViewGeneration;
    const list = el("deviceSessions");
    list.replaceChildren();
    try {
      const result = await api("/sessions", "GET", undefined, true);
      if (generation !== identityViewGeneration) return;
      if (result.readOnly !== true || result.publicKeysReturned !== false ||
          result.deviceDetailsStored !== false || result.legacyOwnerAccess !== false ||
          !Array.isArray(result.sessions) || result.count !== result.sessions.length) {
        throw new Error("Session listing response rejected");
      }
      const valid = result.sessions.every(item =>
        typeof item.sessionId === "string" && /^[0-9a-f]{32}$/.test(item.sessionId) &&
        Number.isInteger(item.issuedAt) && Number.isInteger(item.expiresAt) &&
        typeof item.current === "boolean");
      if (!valid) throw new Error("Invalid session information");
      el("deviceSessionStatus").textContent = result.count ?
        "Active EdgePilot sessions: " + result.count :
        "No active sessions reported";
      for (const session of result.sessions) {
        const entry = document.createElement("li");
        const when = new Date(session.issuedAt * 1000).toLocaleString();
        entry.appendChild(document.createTextNode(
          (session.current ? "This session" : "Other session") +
          " · signed in " + when + " "));
        if (!session.current) {
          const revokeButton = document.createElement("button");
          revokeButton.type = "button";
          revokeButton.textContent = "Sign out this session";
          revokeButton.addEventListener("click", () => action(async () => {
            if (!window.confirm("Sign out this other EdgePilot session?")) return;
            const requestGeneration = identityViewGeneration;
            const revoked = await api("/sessions/" + encodeURIComponent(session.sessionId),
              "DELETE", undefined, true);
            if (requestGeneration !== identityViewGeneration) return;
            if (revoked.otherSessionRevoked !== true ||
                revoked.currentSessionRevoked !== false ||
                revoked.otherUserAffected !== false ||
                revoked.publicConnectionChanged !== false ||
                revoked.liveTradingEnabled !== false ||
                revoked.fundTransfersEnabled !== false) {
              throw new Error("Session revocation response rejected");
            }
            await loadDeviceSessions();
            status("The selected EdgePilot session was signed out. Your current session remains active.");
          }));
          entry.appendChild(revokeButton);
        }
        list.appendChild(entry);
      }
    } catch (error) {
      if (generation !== identityViewGeneration) return;
      list.replaceChildren();
      el("deviceSessionStatus").textContent = error.status === 404 ?
        "Device session management is not enabled on this server yet." :
        "Session list is unavailable. No session changes were made.";
    }
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
      if (data.discoveryOnlyPilot === true) {
        el("portfolioSummary").textContent = "Account discovery only — portfolio balances and holdings are not enabled during this pilot.";
      } else if (data.accounts.length === 0) {
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
        if (data.discoveryOnlyPilot === true) {
          li.appendChild(document.createTextNode(" · ownership verified; portfolio, monitor, orders and transfers disabled"));
          items.appendChild(li);
          continue;
        }
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
        el("addAnotherPasskey").disabled = true;
      } else {
        el("addAnotherPasskey").disabled = knownPasskeyCount === null ||
          knownPasskeyCount >= 12;
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
  el("generateFamilyInvite").addEventListener("click", () => action(async () => {
    if (el("familyInvitationsPane").hidden) {
      throw new Error("Private invitations are not enabled for this owner.");
    }
    if (!window.confirm("Create a one-time family invitation? It expires after one hour and can be redeemed by one person.")) return;
    // Wipe a previously revealed code before making another request. The
    // server stores only a hash; this page keeps the token in RAM/DOM only.
    el("familyInviteCode").value = "";
    el("familyInviteResult").hidden = true;
    const generation = identityViewGeneration;
    const issued = await api("/admin/invitations", "POST", {}, true);
    if (generation !== identityViewGeneration) return;
    if (typeof issued.invitation !== "string" ||
        !/^[A-Za-z0-9_-]{43}$/.test(issued.invitation) ||
        issued.expiresInSeconds !== 3600 ||
        issued.newUserRole !== "member" ||
        issued.maxPrivateUsers !== 10 ||
        issued.publicBrokerageEnabled !== false ||
        issued.tradingEnabled !== false ||
        issued.fundTransfersEnabled !== false) {
      throw new Error("The private invitation response could not be verified.");
    }
    el("familyInviteCode").value = issued.invitation;
    el("familyInviteCode").type = "password";
    el("revealFamilyInvite").textContent = "Show code";
    el("familyInviteResult").hidden = false;
    el("familyInviteHelp").textContent =
      "Created. Valid for one hour and only one registration. Copy it only to your invited family member.";
    status("A private, one-time invitation was created. No account or brokerage connection was shared.");
  }));
  el("revealFamilyInvite").addEventListener("click", () => {
    if (el("familyInvitationsPane").hidden || !el("familyInviteCode").value) return;
    const input = el("familyInviteCode");
    const reveal = input.type === "password";
    input.type = reveal ? "text" : "password";
    el("revealFamilyInvite").textContent = reveal ? "Hide code" : "Show code";
  });
  el("copyFamilyInvite").addEventListener("click", () => action(async () => {
    if (el("familyInvitationsPane").hidden ||
        !/^[A-Za-z0-9_-]{43}$/.test(el("familyInviteCode").value)) {
      throw new Error("No private invitation is available to copy.");
    }
    if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") {
      throw new Error("Secure clipboard is unavailable. Use Show code and copy it manually.");
    }
    await navigator.clipboard.writeText(el("familyInviteCode").value);
    status("Private invitation copied. Send it directly to your invited family member.");
  }));
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
  async function registerPasskey() {
    if (!supported()) throw new Error("Passkeys are not supported by this device or browser.");
    const begin = await api("/passkeys/register/options","POST",{},true);
    const credential = await navigator.credentials.create({
      publicKey:optionsForBrowser(begin.publicKey,true)
    });
    if (!credential) throw new Error("Passkey creation cancelled");
    await api("/passkeys/register/finish","POST",{
      requestId:begin.requestId,credential:publicCredential(credential)
    },true);
    await loadPasskeys();
    status("Your passkey was registered. You can use your device's credential provider to sign in.");
  }
  el("addPasskey").addEventListener("click", () => action(registerPasskey));
  el("addAnotherPasskey").addEventListener("click", () => action(registerPasskey));
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
  el("passwordChangeForm").addEventListener("submit", event => {
    event.preventDefault();
    action(async () => {
      const currentPassword=el("currentEdgePilotPassword").value;
      const newPassword=el("replacementEdgePilotPassword").value;
      const generation=identityViewGeneration;
      try {
        if (!currentPassword || newPassword.length < 14 || newPassword.length > 128 ||
            currentPassword === newPassword) {
          throw new Error("Enter your current password and a different new password of 14–128 characters.");
        }
        if (!window.confirm("Change your EdgePilot password and sign out all EdgePilot devices?")) return;
        const changed=await api("/password/change","POST",
          {currentPassword,newPassword},true);
        if (generation !== identityViewGeneration) return;
        if (changed.passwordChanged !== true ||
            changed.allIdentitySessionsRevoked !== true ||
            changed.mustSignInAgain !== true ||
            changed.publicCredentialChanged !== false ||
            changed.liveTradingEnabled !== false ||
            changed.fundTransfersEnabled !== false) {
          throw new Error("Password change response rejected");
        }
        showLoggedOut();
        status("EdgePilot password changed. All devices are signed out. Sign in again.");
      } finally {
        el("currentEdgePilotPassword").value = "";
        el("replacementEdgePilotPassword").value = "";
      }
    });
  });
  el("refreshDeviceSessions").addEventListener("click", () => action(async () => {
    await loadDeviceSessions();
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