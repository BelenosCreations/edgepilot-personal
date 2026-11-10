# EdgePilot Android test shell — v0.19.17

EdgePilot supports both **debug-signed** Android testing and a separately
**permanently signed private test APK**. Neither is a Play Store release or a
production-activated brokerage client. It runs the hosted EdgePilot web application through
an HTTPS-only Android WebView. Server research and Observe/Paper workers run
in Render; no trading worker operates on the phone.

## Install on Android

1. Open the private GitHub repository, then **Actions** > **EdgePilot Android
   test APK**, and select a successful run matching the desired commit.
2. Under Artifacts, download
   **EdgePilot-v0.19.17-public-onboarding-debug-apk.zip**.
3. Extract app-debug.apk and install it using your Android file manager.
   Android may request permission for that installer to install apps.
   Enable that only when you have verified your own private repository.
4. Launch EdgePilot. The default page is
   **https://edgepilot.belenoscreations.biz/**. Sign in with the existing
   personal EdgePilot access token in the personal dashboard, NOT a Public
   API secret.
5. The separate **/account** web page provides a development-stage shared
   account interface for invitation signup, password login, passkey flows
   and per-user Public key entry. The server gates are intentionally OFF
   in the default deployed configuration.

## Official Public account onboarding

From the EdgePilot personal login screen, follow the link to create or sign
in to a separate EdgePilot identity. Under Your Public connection, users may
follow Public's official **Sign Up for Public** page or the official API
quickstart/key instructions. The Android shell opens these two HTTPS pages
externally after a deliberate click; it never loads Public's site into
the EdgePilot authenticated WebView.

After generating the secret key in Public's Settings > Security > API,
return to EdgePilot and paste it into the individual-account connection
field, not the legacy personal access-token input. Features are still
default-off in production and the two-device integration remains unverified.

## Permanently signed private test APK — verified CI and owner-reported install

The repository now includes a **separate manual** GitHub Actions workflow
named "EdgePilot manually signed Android test APK". It requires an operator
to configure a long-lived private signing keystore and matching certificate
SHA-256 digest in GitHub Actions secrets. A requested build refuses absent
or mismatched signing credentials and uploads *only* a verified private
test APK. The usual v0.19.17 debug APK remains the normal build path.

The signed workflow completed successfully on its second attempt on
November 10, 2026: GitHub run #42888113943, commit
`45ecaf82d0f1c3d648c2e6ab0a17d18817823e73`. The first attempt correctly
refused a mismatched fingerprint; the second passed certificate pinning and
uploaded `EdgePilot-v0.19.17-private-stable-signed-test` containing
`EdgePilot-private-signed-test.apk`. The private artifact expires November
17, 2026 (seven-day retention).

To retrieve the verified private artifact, open the signed
[GitHub Actions run](https://github.com/BelenosCreations/edgepilot-personal/actions/runs/42888113943)
while signed into the authorized repository account. Download its successful
attempt's artifact, extract the APK and verify the package/signature before
installing. GitHub's artifact URL requires authorized repository access.

**Do not uninstall your currently installed debug APK yet.** Android rejects
an in-place install when the existing same-package APK has a different
signing certificate. A new stable-signed install may require uninstalling
the debug version, which erases the app's on-device cookies and preferences.
Ensure existing login and recovery paths work first. Encrypted server-side
credentials are separate from local app data. On November 10, 2026, the owner reported installing the previously
downloaded permanent-signed test APK on their current Android phone, then
successfully logging into the legacy EdgePilot personal dashboard using
the previously verified existing owner access token. This confirms a
basic real-phone application/login smoke test as reported by the owner;
it does NOT independently inspect that phone's installed signing
certificate, verify Digital Asset Links or test the separate tenant
passkey authentication path. The old installation's local cookies and
settings were not guaranteed to be preserved.

See ANDROID_PRIVATE_SIGNING_RUNBOOK.md. Signing a test APK does not activate
EdgePilot multi-user credentials, Android passkeys, live brokerage requests,
market scanners, orders or transfers.

## Separate EdgePilot Staging Android package (prepared, not installed)

The main release and debug APKs remain package `com.edgepilot.mobile` and
continue to use the production HTTPS host. A separate unsigned staging
variant now builds with package `com.edgepilot.mobile.staging`, visible
label `EdgePilot Staging`, and a compile-time owned test hostname. Its
default unconfigured host uses a deliberately nonfunctional `.invalid`
address. The ordinary Android PR workflow compiles it but uploads only
the usual debug APK; no staging signed artifact has been generated yet.

A separate manual-only staging signing workflow, protected by the existing
certificate verifier and strict host/package checks, is available once an
independent HTTPS staging backend has been explicitly provisioned. Do not
create a second service, distribute this APK, or enable dormant tenant
identity/passkey flags merely because this source compiles. The regular
installed EdgePilot app stays unchanged. See ANDROID_ISOLATED_STAGING_RUNBOOK.md.

## Passkeys are not yet proven on real devices

This APK includes AndroidX WebKit's native Web Authentication feature
(on devices and WebView versions that support it) and stable Credential
Manager dependencies. The passkey credential remains in the Android
credential provider. The backend verifies signed WebAuthn challenges;
EdgePilot never saves fingerprint/face templates.

**Do not infer this build has working biometric login.** An Android app
and website must be linked through a Digital Asset Links response containing
the SHA-256 fingerprint of the certificate that signed the *installed* APK.
GitHub debug APKs use transient debug signing keys, so a future build may
have a different fingerprint. Stable signed release builds and verified
Digital Asset Links must be established before claiming supported
biometric login or allowing multi-user real-account acceptance.

The backend publishes /.well-known/assetlinks.json only if
EDGE_ANDROID_CERT_SHA256 contains a valid signing certificate fingerprint.
Without configuration it returns 404. See
TENANT_PASSKEY_MOBILE_RUNBOOK.md for the verification process.

## Existing security boundaries

- The wrapper opens only the approved HTTPS EdgePilot host; off-host
  navigation, file access, third-party cookies, mixed content and invalid
  TLS certificates remain blocked. WebView debugging stays disabled.
- Neither Public credentials nor the owner access token are embedded in APK
  source. Browser and Android session cookies are separate.
- Real brokerage orders, autonomous live execution and funds transfers
  remain disabled.
- No Android offline trading, push-notification engine, automatic trusted
  release signing or Play Store delivery is implemented.
- APK artifacts are available only to authorized repository users. The
  permanent-signed test artifact currently has 7-day retention; the debug
  workflow's artifact retention is separate.
- The debug signing identity can change between GitHub runners. Installing a
  new debug build may require uninstalling the previous one, losing local
  phone preferences and cookies; server data is unaffected.

## Build

Gradle 8.9, Java 17 and the Android SDK are used by the GitHub workflow.
Build locally with `gradle -p android :app:assembleDebug` when the Android
SDK and compatible Gradle installation are present. A successful compile
does not establish trusted Digital Asset Links or real biometric login.
