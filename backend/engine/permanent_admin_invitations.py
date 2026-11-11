"""Owner-only, bounded family invitations on the permanent tenant database.

DORMANT until separately enabled on tenant-only production identity.
Never accepts a client user ID, creates owner privileges, copies Public
credentials, contacts the broker, schedules work or executes trades.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time

from . import identity_auth

MAX_USERS = 10
MAX_ISSUED_PER_DAY = 9
TTL_SECONDS = 3600
DAY_SECONDS = 86400


class PermanentInvitationDenied(PermissionError):
    pass


def setup(path):
    """Prepare an isolated append-only nonsecret owner invitation audit."""
    with identity_auth._db(path) as db:
        required=("tenant_users", "tenant_identities",
                  "tenant_identity_sessions", "tenant_signup_invites")
        if any(not db.execute("""SELECT 1 FROM sqlite_master
                WHERE name=? AND type='table'""",(name,)).fetchone()
                for name in required):
            raise PermanentInvitationDenied("Owner invitations unavailable")
        db.execute("""CREATE TABLE IF NOT EXISTS permanent_invitation_issues(
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_user_id TEXT NOT NULL REFERENCES tenant_users(user_id),
            issued_at INTEGER NOT NULL
        )""")
        db.execute("""CREATE INDEX IF NOT EXISTS idx_permanent_invite_issued
            ON permanent_invitation_issues(owner_user_id,issued_at)""")
        db.execute("""CREATE TRIGGER IF NOT EXISTS no_permanent_invite_delete
            BEFORE DELETE ON permanent_invitation_issues
            BEGIN SELECT RAISE(ABORT,'audit append-only'); END""")
        db.execute("""CREATE TRIGGER IF NOT EXISTS no_permanent_invite_update
            BEFORE UPDATE ON permanent_invitation_issues
            BEGIN SELECT RAISE(ABORT,'audit append-only'); END""")


class PermanentAdminInvitations:
    def __init__(self, path, identity_store):
        if (not isinstance(identity_store, identity_auth.IdentityStore)
                or identity_store.path != str(path)):
            raise TypeError("Independent identity store required")
        self.path=str(path)

    def issue(self, identity_token, csrf, *, now=None):
        """Owner session + CSRF revalidated under the same SQLite write lock.

        At most nine one-use member invitations per day, with a hard
        ten-registered-plus-unredeemed cap. Expired unused invitations may
        be replaced later. No owner or elevated roles are issued.
        """
        moment=int(time.time()) if now is None else now
        if type(moment) is not int or not 0 < moment < 253402300799:
            raise PermanentInvitationDenied("Owner invitations unavailable")
        if (not isinstance(identity_token,str) or not 25<len(identity_token)<256
                or not isinstance(csrf,str) or not 20<len(csrf)<256):
            raise PermanentInvitationDenied("Owner invitations unavailable")
        new_token=secrets.token_urlsafe(32)
        token_hash=hashlib.sha256(new_token.encode("utf-8")).hexdigest()
        try:
            with identity_auth._db(self.path) as db:
                db.execute("BEGIN IMMEDIATE")
                principal=db.execute("""SELECT s.user_id,s.csrf_hash
                    FROM tenant_identity_sessions s
                    JOIN tenant_identities i ON i.user_id=s.user_id
                    JOIN tenant_users u ON u.user_id=s.user_id
                    WHERE s.token_hash=? AND s.expires_at>?
                    AND s.credential_version=i.credential_version
                    AND u.disabled_at IS NULL AND u.role='owner'""",
                    (identity_auth._digest(identity_token),moment)).fetchone()
                if principal is None or not hmac.compare_digest(
                        principal["csrf_hash"],identity_auth._digest(csrf)):
                    raise PermanentInvitationDenied("Owner invitations unavailable")
                users=db.execute("SELECT COUNT(*) FROM tenant_users").fetchone()[0]
                pending=db.execute("""SELECT COUNT(*) FROM tenant_signup_invites
                    WHERE consumed_at IS NULL AND expires_at>?""",
                    (moment,)).fetchone()[0]
                issued=db.execute("""SELECT COUNT(*) FROM permanent_invitation_issues
                    WHERE issued_at>?""",(moment-DAY_SECONDS,)).fetchone()[0]
                if (users<1 or users+pending>=MAX_USERS
                        or issued>=MAX_ISSUED_PER_DAY):
                    raise PermanentInvitationDenied("Private member invitation limit reached")
                db.execute("""INSERT INTO tenant_signup_invites
                    (token_hash,created_at,expires_at) VALUES(?,?,?)""",
                    (token_hash,moment,moment+TTL_SECONDS))
                db.execute("""INSERT INTO permanent_invitation_issues
                    (owner_user_id,issued_at) VALUES(?,?)""",
                    (principal["user_id"],moment))
        except sqlite3.Error:
            raise PermanentInvitationDenied("Owner invitations unavailable") from None
        return {"invitation":new_token,"expiresInSeconds":TTL_SECONDS,
                "maxPrivateUsers":MAX_USERS,"newUserRole":"member",
                "publicBrokerageEnabled":False,"tradingEnabled":False,
                "fundTransfersEnabled":False}
