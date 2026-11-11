# v0.2.61 — Owner-only invitations for up to 10 private EdgePilot users

**Status:** Production feature flag remains OFF, no invitation issued.

The permanent single-instance EdgePilot backend can use an independently
authenticated **owner-role EdgePilot session** to issue one-use,
one-hour member invitations. Owner role originates from the v0.2.60
private console bootstrap, never from the old `EDGE_APP_TOKEN`,
a Public account key, a requested client role, or a staging operator
key. The route is `POST /api/identity/admin/invitations`, accepts
**exactly an empty JSON object**, and uses same-origin HTTPS,
identity cookie, independent CSRF and a second live user-role/session
check under the SQLite write lock.

## Capability limits

- New owner invitations return a 43-character random token **once**;
  only SHA-256 token hashes and nonsecret issuance audit events are
  persisted. The new registrant has `role=member`, never owner.
- Ten total registered users, including initial owner, with pending
  unredeemed invitations also consuming a slot. Concurrent requests
  serialize. The registrar independently checks the hard ten-user
  ceiling inside its registration transaction; it cannot be raced
  through another invitation source.
- No more than nine invitations per rolling 24-hour period. Expired
  unused invitations can be replaced later while seats are available.
  Audit history is append-only and not reset by expiration.
- Other logged-in members, revoked/expired sessions, unknown CSRF,
  cross-origin requests or malformed JSON cannot issue invitations.
  Login, password and account authorization are entirely per-user.
- It does not copy owner's legacy data, bypass identity bootstrap,
  grant Public trading access, issue broker tokens, run worker jobs,
  transfer funds, add paid resources or permit autonomous trading.

## Operational gate

`EDGE_PERMANENT_OWNER_INVITES_ENABLED=true` is **independently**
opt-in and is refused by app startup unless the separate tenant
database and tenant-only routing have been prepared, identity
authentication is enabled and `EDGE_TENANT_SIGNUP_ENABLED=true`.
This flag is **not set on the real paid Render service**.

First verify the original database and encrypted recovery, owner
bootstrap, owner member login/recovery, and separated identity DB.
Only then separately approve turning on this invitation gate and
creating real family accounts. New users receive tokens through a
secure private channel; do not paste live invitations into GitHub,
public screenshots or logs. Two independently signed-in phones and
fully scoped accounts must still be tested. Provider-permitted
read-only Public integration is a separate step. Production orders
and fund transfers stay disabled.

The ten-user cap is a private pilot size, **not** a commercial
scalability promise or cloud capacity guarantee. Future expansion,
recovery, rate limits across user networks and production compliance
would require additional review.
