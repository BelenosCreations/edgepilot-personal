# EdgePilot v0.19.12 — private Android APK prototype

This is a **debug-signed test APK**, not a Play Store release. It is a minimal Android WebView wrapper around the existing secure Flask web app. The server still runs on Render; an Android app does not provide autonomous trading when the phone is offline.

## Get the APK from GitHub (phone only)

1. Open the private GitHub repository → **Actions** → **EdgePilot Android test APK**.
2. Open the successful workflow run and scroll to **Artifacts**.
3. Download `EdgePilot-v0.19.12-debug-apk.zip`, extract `app-debug.apk` from it using your phone's file manager, and install it.
4. Android may request permission to install apps from the application you used to open the APK. Only allow this for a download you verified came from your own private repository.
5. Launch the EdgePilot icon. The app opens **https://edgepilot.belenoscreations.biz/**. Use your existing EdgePilot access token to sign in; never use your Public key in the app's token field.

The APK has no keys or brokerage credentials embedded. It only loads the trusted HTTPS hostname, blocks outside domains and plaintext URLs, disallows local file access and mixed content, and uses WebView's first-party cookie jar for the server's HttpOnly session. A Chrome login does not automatically carry over to the APK.

## Limitations and security

- Debug APKs are **test-only** and signed by a transient GitHub runner debug key. A future build may require uninstalling this copy, which loses local app preferences and cookie sessions; database settings remain on Render.
- There is no background Android trading worker, push notifications, biometric login, MFA, offline trading or Play Store publishing yet.
- The native shell executes the existing remote website. Until the web UI receives stricter CSP/XSS defenses and private access protections, do not configure the Public brokerage secret.
- API endpoints remain protected by the server session, and production broker order execution remains disabled.
- HTTPS must be valid; the app deliberately blocks SSL errors rather than ignoring them.
- Debug artifacts are visible only to authorized GitHub users and retained for 14 days. Do not share them publicly.

## Source build

The Android Gradle Plugin is `8.7.3`, Gradle is `8.9`, and Java is `17`. In the `android` directory, the command is `gradle :app:assembleDebug`. The GitHub Actions workflow performs the build with an Android SDK installed; no desktop is necessary.
