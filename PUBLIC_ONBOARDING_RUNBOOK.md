# EdgePilot v0.2.34 — Official Public signup and API key onboarding

This stage adds the owner-approved Public onboarding choice directly to
EdgePilot's separate individual-account screen. It does not bypass the
EdgePilot invitation-only signup gate or change any brokerage permission.

If the member has no Public account, they can follow **Sign Up for Public**:
https://public.com/signup

If the member already has Public, **Get your Public API key** opens the
official documentation:
https://public.com/api/docs/quickstart

Public's documented navigation is Settings > Security > API. Generate a
secret API key in Public, return to EdgePilot and enter it into the
current user's own encrypted credential form. Do not enter a Public login
password, bearer access token or secret inside the separate personal
EdgePilot owner access-token field.

## Android URL boundary

The WebView still accepts only the EdgePilot HTTPS host. For these two
specific Public help links alone, Android can send a deliberate main-frame
user click to the operating system's external URL handler. Public pages
never run inside the EdgePilot authenticated WebView and cannot read its
cookies or local application state.

Allowed: https://public.com/signup
Allowed: https://public.com/api/docs/quickstart

The host must be exactly public.com (no subdomains), HTTPS on default or
443, with no userinfo, query or fragment. Other off-host URLs, custom schemes,
iframe navigation, unsolicited redirects and subresources remain blocked.
The Public website may handle its own redirects after opening externally.

On mobile return to EdgePilot through the Android app switcher and paste
the secret into Your Public connection. Avoid screenshots and clipboard
sharing of a secret. A new user's key is never copied into another tenant's
record; the existing encrypted Public credential vault still enforces
server-side identity and connection ownership.

## Validation and remaining requirements

GitHub tests verify exact official URLs, secure help links, explicit gesture
routing, lack of JavaScript bridges and unchanged WebView network
restrictions. Android debug APK compilation confirms source compatibility
but real-device external link behavior must still be tested.

The account, passkey, Public vault, tenant read-only and monitor features
remain separately default-off. No real provider connection, broker order,
funds transfer, production multi-user activation, signed APK or two-device
acceptance is claimed by this release.
