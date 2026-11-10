# EdgePilot Android test shell — v0.19.17

This is a **debug-signed, private test APK**, not a Play Store release or
production-signed build. It runs the hosted EdgePilot web application through
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
- APK artifacts are available only to authorized repository users and
  expire after the private workflow retention period (currently 14 days).
- The debug signing identity can change between GitHub runners. Installing a
  new debug build may require uninstalling the previous one, losing local
  phone preferences and cookies; server data is unaffected.

## Build

Gradle 8.9, Java 17 and the Android SDK are used by the GitHub workflow.
Build locally with `gradle -p android :app:assembleDebug` when the Android
SDK and compatible Gradle installation are present. A successful compile
does not establish trusted Digital Asset Links or real biometric login.
