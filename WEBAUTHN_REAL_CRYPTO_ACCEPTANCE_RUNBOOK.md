# EdgePilot v0.2.41 — Offline real-cryptography WebAuthn acceptance

## What this milestone proves

The new backend/tests/test_two_user_real_crypto_webauthn_v0241.py exercises
the real gated Flask identity/passkey routes using two separate in-memory HTTP
clients and independently generated P-256 software-authenticator keys. Unlike
older WebAuthn tests, **the production py_webauthn registration and
authentication cryptographic verifiers are not patched or mocked**.

Each test credential is generated only inside the test process. The fixture
produces a genuine COSE EC2/ES256 public key, CBOR fmt=none attestation,
relying-party hash, UP/UV and attested credential flags, WebAuthn clientDataJSON,
and signed authenticator assertions. The private keys are short-lived test
memory values, not exported to disk, GitHub artifacts, Render, APKs or users.
Outbound HTTP requests are explicitly blocked during the test.

The test checks:
- Password-authenticated, owner-scoped enrollment of two different credentials
  with independent tenant identities and exactly matching RP/origin.
- Cryptographically verified login using actual ES256 signatures and
  correct WebAuthn challenges for each account; separate Secure, HttpOnly
  identity cookies and no access to legacy owner endpoints.
- Denial of forged WebAuthn origin, missing user-verification flag, altered
  signature, mismatched user handle, and challenge reuse.
- Rejection of signature-counter rollback and a revoked passkey, including
  invalidation of only that user's sessions.

## Safety boundaries

This is **not** proof of Android Credential Manager WebView compatibility,
real fingerprint/face/PIN verification, app-to-domain OS-level Digital Asset
Links verification, physical-device enrollment or two-device acceptance.
The owner verified the website's public Digital Asset Links JSON and installed
and logged into the permanently signed APK using the **legacy** owner token.
The separate tenant login remains disabled in the live deployment.

No Public account is contacted, no real credentials are used, and no
brokerage order/transfer APIs are reachable from this fixture. Run only with
test-controlled RP/origin, temp SQLite DB and synthetic users. Never set
tenant/passkey/signup/vault flags to true on the existing personal deployment
just to satisfy a test, and never copy the legacy EDGE_APP_TOKEN into a
tenant identity.

## How to run locally or in CI

From backend/ after installing requirements.txt:

    python -m unittest tests.test_two_user_real_crypto_webauthn_v0241 -v

Standard GitHub Actions discovers the test automatically, compiles backend
code and checks browser JavaScript. Test failures must be corrected before
the milestone is declared complete.

## Remaining acceptance gates

1. Run actual Android Credential Manager/WebAuthn on an isolated HTTPS
   backend with explicit non-trading tenant test settings and reliable
   account recovery. The live personal owner service remains unchanged.
2. Confirm the installed APK certificate and OS app-to-domain association
   (not only website JSON), and verify the local biometric/PIN prompt and
   a server-authenticated tenant identity session.
3. Enroll a second independent user on another Android device; test
   cross-user account isolation, session revocation and lost-device recovery.
4. Obtain appropriate Public API permissions and test independent real
   accounts in read-only mode. Real orders/transfers stay disabled until
   separately authorized.

Passing this CI suite closes local cryptographic WebAuthn acceptance only.
