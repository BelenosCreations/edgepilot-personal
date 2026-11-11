'use strict';
// Disposable staging operator bootstrap. Never persist the operator key or
// invitation codes to browser storage, query parameters, cookies or logs.
const form = document.getElementById('operatorForm');
const input = document.getElementById('operatorKey');
const status = document.getElementById('status');
const button = document.getElementById('issue');
const results = document.getElementById('results');
const invite1 = document.getElementById('invite1');
const invite2 = document.getElementById('invite2');
let codes = null;

form.addEventListener('submit', async event => {
  event.preventDefault();
  status.textContent = '';
  results.hidden = true;
  const key = input.value;
  input.value = ''; // Do not leave the operator secret in a DOM form.
  if (!/^[A-Za-z0-9_-]{43}$/.test(key)) {
    status.textContent = 'Enter the full private operator key.';
    return;
  }
  button.disabled = true;
  try {
    const response = await fetch('/api/staging/invitations', {
      method: 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: {'Content-Type': 'application/json', 'X-Edge-Staging-Operator': key},
      body: '{}'
    });
    if (!response.ok) throw new Error('Codes unavailable. Check the key, host, and staging settings; they can be issued only once.');
    const data = await response.json();
    if (!Array.isArray(data.invitations) || data.invitations.length !== 2
        || data.invitations.some(code => !/^[A-Za-z0-9_-]{43}$/.test(code))) {
      throw new Error('Unexpected response. No codes were displayed.');
    }
    codes = data.invitations.slice();
    invite1.textContent = codes[0];
    invite2.textContent = codes[1];
    results.hidden = false;
    status.textContent = 'Two private invitations created. Redeem within one hour.';
  } catch (error) {
    codes = null;
    invite1.textContent = '';
    invite2.textContent = '';
    status.textContent = error instanceof Error ? error.message : 'Test operator unavailable.';
  } finally {
    button.disabled = false;
  }
});

for (const [id, slot] of [['copy1', 0], ['copy2', 1]]) {
  document.getElementById(id).addEventListener('click', async () => {
    if (!codes || !codes[slot]) return;
    try {
      await navigator.clipboard.writeText(codes[slot]);
      status.textContent = 'Invitation copied. Keep it private.';
    } catch {
      status.textContent = 'Select and copy the displayed code manually.';
    }
  });
}

window.addEventListener('pagehide', () => {
  input.value = '';
  invite1.textContent = '';
  invite2.textContent = '';
  codes = null;
});
