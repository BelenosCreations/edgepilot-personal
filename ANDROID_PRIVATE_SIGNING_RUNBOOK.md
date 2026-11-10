# EdgePilot v0.2.38 — Private Android signing preflight

## Purpose

EdgePilot's existing GitHub Actions debug APK is signed with a runner
specific debug key. It cannot establish a stable Android-to-HTTPS
Digital Asset Links relationship across installs. Passkey verification
through Android Credential Manager must be tested with a **stable,
verified signing certificate**, not a random debug key.

This milestone introduces a completely separate manual signing workflow:
`.github/workflows/android-private-signed.yml`.

It builds an **unsigned release APK from main**, then signs it with a
private keystore supplied only at job runtime. Android SDK `apksigner`
verifies the APK; an independent Python preflight compares the single
signer fingerprint to an operator-pinned SHA-256 certificate fingerprint.
A mismatch, missing input, malformed certificate, multi-signer output
or verification failure terminates the job before any artifact upload.

The existing automatic PR/debug APK workflow stays unchanged. Neither
workflow enables Public access, biometric login, tenant flags, trading,
funds transfers or any operational production change.

## One-time trusted signing prerequisites

A trusted operator must generate a long-lived Android release signing
key **outside the repository** using trustworthy tooling, retain the
private key in a protected offline backup and record its SHA-256
certificate digest. Google recommends retaining and protecting signing
keys since losing or rotating a key affects future Android app updates.

After verifying the key and making a separate backup, add these five
GitHub **Actions repository secrets** to the private repository
Settings > Secrets and variables > Actions. Do not paste them into
ChatGPT, issues, PRs, source files, build logs, screenshots or APKs.

- EDGE_ANDROID_SIGNING_JKS_B64 — base64 encoding of the original binary JKS
- EDGE_ANDROID_SIGNING_STORE_PASS — keystore passphrase
- EDGE_ANDROID_SIGNING_KEY_PASS — signing key passphrase
- EDGE_ANDROID_SIGNING_ALIAS — existing alias inside that JKS
- EDGE_ANDROID_EXPECTED_CERT_SHA256 — pinned signing certificate SHA-256 digest
  (64 hex bytes, optionally colon-separated; public fingerprint, still
  stored as a workflow input for configuration integrity)

The workflow is `workflow_dispatch` only and refuses all branches
except `main`. It cannot generate a key, install signing tools on a
user's phone or automatically create the five secrets. Before a signed
build is attempted, the required signer inputs must be configured by
the authorized repository owner. Do not use a debug keystore or
generate a new key on every CI run.

## Execution and artifact restrictions

Once the trusted inputs are available, an owner can manually run
"EdgePilot manually signed Android test APK" from GitHub Actions on
`main`. The workflow builds unsigned APK code, decodes keystore
material into a private temporary file on the ephemeral runner, signs
with `apksigner` using password environment references (never literal
password arguments), verifies the signature and checks the pinned
certificate, package ID and APK version. Temporary JKS and report files
are removed on exit. The only uploaded artifact is the signed private
test APK, retained for 7 days.

Do not distribute that artifact or infer that it is production-ready.
Private repository access restricts who may download the artifact, not
who may install it after download. Stable signer requirements do not
replace vulnerability review, device testing or brokerage authorization.

A test APK signed with this certificate cannot generally be installed
over an existing runner-debug-signed APK with the same package name.
An uninstall/reinstall may be required; this removes local app cookies
and preferences. Server-side encrypted credentials remain on the
server, provided the server data itself is intact.

## Digital Asset Links and biometric test gate

After successfully signing and verifying a private APK, set the server's
EDGE_ANDROID_CERT_SHA256 configuration to **that same actual certificate**
only in an appropriate isolated test deployment. The server's
`/.well-known/assetlinks.json` must return the exact Android package
`com.edgepilot.mobile`, proper relationship, and matching fingerprint.

Then test the installed APK on two physical Android devices with
independent EdgePilot users and synthetically isolated Public account
data. Verify actual Credential Manager registration/sign-in, lost-session
revocation, and account isolation. These checks require controlled
tenant feature flags and are not performed by GitHub's compile jobs.

Because EdgePilot's current tenant identity/passkey routes and Public
read-only APIs are default-off, the signed APK alone does NOT make
biometric sign-in usable. Never enable real brokerage orders or transfers
as a side effect of a signed Android build.

## CI verification

`backend/tests/test_android_private_signing_v0238.py` checks the signing
preflight against mismatched/multiple signer reports and audits the
manual-only workflow, secret-handling boundaries and ignored keystore
files. Standard backend CI runs those tests, but a real signed APK build
cannot be exercised without an operator-controlled keystore. That
limitation is an explicit open acceptance item.

For Google's documentation see:
https://developer.android.com/build/building-cmdline
https://developer.android.com/identity/sign-in/credential-manager-webview
