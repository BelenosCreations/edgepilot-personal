# v0.2.79 — Owner invitation controls for private family onboarding

This milestone adds a small invitation panel to the existing Android-capable EdgePilot account page. It is **source-only, default-off** and builds on the already merged v0.2.78 protected owner/legacy coexistence architecture. It does not create any invitation, user, Public account, Android APK, or new paid service during deployment.

## Owner-only experience

After a successful independent EdgePilot account login, `GET /api/identity/session` returns a nonsecret `privateInvitationsAvailable` boolean. It is true only when the server's existing invitation flag is active **and** the authenticated identity has the owner role. This field contains neither an invitation nor an authorization token. The actual invitation creation endpoint still revalidates owner identity, active session, CSRF hash, capacity and rate limit atomically in SQLite.

When the capability is false, the entire invitation panel remains hidden. With valid owner authorization, the owner may tap **Create a private invitation**, confirm the action, and receive a one-time code. The page validates the server's response: 43-character token, one-hour lifetime, member-only role, private cap of ten, no broker privileges, trades or transfers. The token is kept only in the live page's password-style input; it is never written to URLs, local/session storage, telemetry, GitHub, or any server-side log by this UI. A direct owner action can reveal/hide or copy the code to their phone clipboard. Copying is an intentional human action; Android clipboard history may retain it, so treat the code as secret. The page wipes it on logout or session replacement.

The invited person opens the existing `/account` screen, uses its already existing **Create an account** form and privately supplied token, then signs in with independently chosen Argon2id credentials. The owner remains on the original dashboard and/or their separate EdgePilot identity login. New members never receive an owner's browser cookie, key, portfolio or legacy login token.

## Production gates and limitations

No owner invitation button appears unless the currently configured backend expressly enables issuance. The shared paid Render service must still satisfy every v0.2.78 discovery-only, encrypted-storage and no-trade prerequisite. The production environment has **not** been changed by this branch. The original owner has not authorized live invitation issuance or enrolled a second family member. A physical second Android phone, separate Public credential/account, off-service multi-user backup and recovery test remain required before production enrollment.

User-facing controls do not replace the pending operator workflow for verifying backups, credential-key custody, invitation transport and reversible feature flags. No email delivery or public signup is added. Do not publish screenshots containing active invitation codes or use public GitHub issues for sharing codes. Existing manual signed APK workflows remain separate and never run automatically from this backend/UI-only PR.

See [FAMILY_INVITE_COEXISTENCE_V0278.md](FAMILY_INVITE_COEXISTENCE_V0278.md), README.md, CHANGELOG.md and DEVELOPMENT_CONTINUITY.md.
