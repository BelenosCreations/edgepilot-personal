# v0.2.78 — Invitation-only private family accounts alongside the legacy login

**Decision:** On November 12, 2026, the owner approved implementing the *invitation-only coexistence* architecture instead of immediately retiring the working legacy owner login. Approval permits source development and synthetic tests, **not** activation of production member registration or issuing a real invitation.

This stage reuses the existing paid Render backend, the private legacy `/data/edgepilot.db` and independently encrypted `/data/edgepilot-tenants.db`. Public GitHub source availability gives no entitlement to any private account, database, credential, signing key or backup.

## Runtime opt-in boundary

A new, independently default-off `EDGE_FAMILY_INVITE_COEXISTENCE_ENABLED=true` can allow the already implemented owner-only invitation endpoint and one-use member registration to coexist with the original legacy API login. This switch is **not enabled by merging code, running CI or deploying source**, and no production environment variables have been changed as part of this milestone.

The flag requires all of the following concurrently:

- Existing separate prepared tenant SQLite file, validated owner Argon2id identity, owner HTTPS login and verified stable Fernet encryption key.
- Explicit `EDGE_PERMANENT_READONLY_PILOT_ENABLED`, `EDGE_TENANT_ACCOUNT_READS_ENABLED`, `EDGE_TENANT_PUBLIC_VAULT_ENABLED`, `EDGE_TENANT_PUBLIC_READONLY_ENABLED`, and `EDGE_TENANT_PUBLIC_DISCOVERY_ONLY`.
- Existing private owner-only `EDGE_PERMANENT_OWNER_INVITES_ENABLED` and one-use token-only `EDGE_TENANT_SIGNUP_ENABLED` settings.
- **Disabled** tenant-only retirement, Android passkeys, unrelated staging, global workers, orders, monitoring preview and watchlist modifications.

Any missing requirement or prohibited flag fails startup before a new account is registered. The original tenant-only invitation route remains unchanged; no open/public registration is introduced.

## Member isolation

Only a currently authenticated, active **owner** can issue an invitation, using same-origin HTTPS requests and valid identity-session CSRF. Existing `PermanentAdminInvitations` enforces a one-hour token lifetime, at most nine invitations per day, and ten total registered-plus-pending private users. An invite token is returned only once to the owner and stored only as SHA-256 in the tenant database; never put a token in public GitHub, logs or ChatGPT. A member cannot issue another invite or become an owner. Registration atomically consumes a valid invite, creates independent Argon2id login credentials and a non-owner identity, and requires separate login. The explicit 10-user cap is now also enforced in coexistence mode at registration.

Each user must provide their **own** Public API secret in an authenticated tenant session. The source never copies the legacy owner secret into a new family account. Public access under this stage remains restricted to saving encrypted credentials, provider account discovery and owner-scoped verified linkage, with portfolio/balance reads denied and no orders, autonomous execution or bank transfers. Separate legacy session cookies cannot authorize identity APIs, and identity cookies cannot authorize legacy APIs.

## Synthetic acceptance and safe rollback

`backend/tests/test_family_invitation_coexistence_v0278.py` uses only disposable SQLite files and hardcoded synthetic passwords/keys. A real Flask server import in a subprocess verifies owner CSRF, one-use registration, member role restrictions, independent encrypted Public connections and linked fake provider accounts, forbidden cross-user reads, original legacy login continuity, zero real provider requests, and all execution gates disabled. Negative tests reject unsafe runtime settings and missing opt-ins.

If the owner later authorizes a carefully controlled real pilot and needs rollback, all three invitation switches should be set to `false` together: `EDGE_FAMILY_INVITE_COEXISTENCE_ENABLED`, `EDGE_TENANT_SIGNUP_ENABLED`, `EDGE_PERMANENT_OWNER_INVITES_ENABLED`. Existing independently registered users **remain able to sign in** to the tenant login (and owner legacy login continues), but nobody can issue or redeem new invitations during the pause. Do not delete tenant tables, rotate the Fernet key, replace the original owner account, or remove the verified encrypted backups as a rollback mechanism.

## Still not verified or authorized

- No member has actually enrolled through this route on the live paid Render instance.
- No second physical Android phone or independently owned second Public account has been accepted.
- No production multi-member backup has been created or copied off Render; the old v0.2.74 encrypted linked-owner archive remains necessary and cannot cover future members.
- No production member UI, email delivery, forgotten-password recovery, live account balances, real trading, transfers or paid infrastructure changes are authorized by the code alone.
- Manual signed APK workflows remain isolated from PRs in the public GitHub repository.

**Next stage:** Accept CI on the development PR and merged main, then develop owner/member onboarding UI and an operator-gated rollout/rollback checklist. A separately approved, verified backup and two-device procedure must precede real member enrollment.
