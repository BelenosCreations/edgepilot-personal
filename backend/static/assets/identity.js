"use strict";
(() => {
  let identityCsrf = "";
  let busy = false;
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
  }
  async function showSession() {
    const data = await api("/session");
    identityCsrf = data.csrf;
    el("authPane").hidden = true;
    el("accountPane").hidden = false;
    el("welcome").textContent = "Welcome, " + (data.user && data.user.label || "EdgePilot user");
    el("addPasskey").disabled = !supported();
    status("Secure EdgePilot account session active. Brokerage execution remains disabled.");
    await loadConnections();
  }
  async function loadConnections() {
    try {
      const data = await api("/public/connections");
      const items = el("connections");
      items.replaceChildren();
      for (const item of data.connections || []) {
        const entry = document.createElement("li");
        entry.textContent = "Public connection " + String(item.connectionId) + " — " + String(item.status);
        items.appendChild(entry);
      }
      el("connectionInfo").textContent = items.children.length ?
        "Encrypted connections belonging to your account:" : "No Public key saved for this account.";
    } catch (error) {
      el("connections").replaceChildren();
      el("connectionInfo").textContent = "Public key setup is not enabled for this account yet.";
    }
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