"""v0.2.36 password-change unit tests, isolated temporary tenant DB only."""
import sqlite3
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from engine import identity_auth, tenant_foundation, tenant_password_change

PW_A="first-member-password-strong-example-2026"
PW_B="second-member-password-strong-example-2026"
PW_NEW="first-member-replacement-strong-example-2026"


class TenantPasswordChangeUnitTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="edgepilot-pw-change-v036-")
        self.path=self.temp.name+"/tenant.sqlite3"
        tenant_foundation.setup(self.path)
        identity_auth.setup(self.path)
        tenant_password_change.setup(self.path)
        self.tenants=tenant_foundation.TenantStore(self.path)
        self.identity=identity_auth.IdentityStore(self.path)
        self.manager=tenant_password_change.TenantPasswordChange(self.path,self.identity)
        self.a=self.tenants.provision_user("Alice","member")
        self.b=self.tenants.provision_user("Bob","member")
        self.identity.provision(self.a,"password_alice",PW_A)
        self.identity.provision(self.b,"password_bob",PW_B)
        self.s1=self.identity.authenticate("password_alice",PW_A,"phone-a")
        self.s2=self.identity.authenticate("password_alice",PW_A,"tablet-a")
        self.sb=self.identity.authenticate("password_bob",PW_B,"phone-b")
        self.assertTrue(self.s1 and self.s2 and self.sb)

    def tearDown(self):
        self.temp.cleanup()

    def test_change_requires_old_password_and_revokes_only_owners_sessions(self):
        changed=self.manager.change(self.s1["token"],self.s1["csrf"],PW_A,PW_NEW)
        self.assertTrue(changed["passwordChanged"])
        self.assertTrue(changed["allIdentitySessionsRevoked"])
        self.assertTrue(changed["mustSignInAgain"])
        self.assertFalse(changed["publicCredentialChanged"])
        self.assertFalse(changed["liveTradingEnabled"])
        self.assertFalse(changed["fundTransfersEnabled"])
        self.assertIsNone(self.identity.principal(self.s1["token"]))
        self.assertIsNone(self.identity.principal(self.s2["token"]))
        self.assertEqual(self.identity.principal(self.sb["token"])["user_id"],self.b)
        self.assertIsNone(self.identity.authenticate("password_alice",PW_A,"phone-a"))
        renewed=self.identity.authenticate("password_alice",PW_NEW,"phone-a")
        self.assertEqual(self.identity.principal(renewed["token"])["user_id"],self.a)
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute("""SELECT COUNT(*) FROM tenant_identity_sessions
                WHERE user_id=?""",(self.a,)).fetchone()[0],1)
            audit=con.execute("""SELECT event,user_id FROM tenant_password_change_events""").fetchall()
            self.assertEqual(audit,[("PASSWORD_CHANGED",self.a)])
            hashed=con.execute("""SELECT password_hash FROM tenant_identities
                WHERE user_id=?""",(self.a,)).fetchone()[0]
            self.assertTrue(hashed.startswith("$argon2id$"))
            self.assertNotIn(PW_NEW,hashed)
            self.assertNotIn(PW_A,hashed)
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("DELETE FROM tenant_password_change_events")

    def test_invalid_old_password_and_bad_csrf_do_not_affect_any_session(self):
        for token,csrf,current,new in (
            (self.s1["token"],self.s1["csrf"],"wrong-current-password",PW_NEW),
            (self.s1["token"],self.sb["csrf"],PW_A,PW_NEW),
            (self.sb["token"],self.s1["csrf"],PW_B,PW_NEW),
            (self.s1["token"],self.s1["csrf"],PW_A,PW_A),
            ("bad",self.s1["csrf"],PW_A,PW_NEW),
            (self.s1["token"],"bad",PW_A,PW_NEW),
            (self.s1["token"],self.s1["csrf"],PW_A,"short"),
            (self.s1["token"],self.s1["csrf"],PW_A,"bad\npassword-long"),
        ):
            with self.subTest(current=str(current)[:12]):
                with self.assertRaises(tenant_password_change.PasswordChangeDenied):
                    self.manager.change(token,csrf,current,new)
        self.assertEqual(self.identity.principal(self.s1["token"])["user_id"],self.a)
        self.assertEqual(self.identity.principal(self.sb["token"])["user_id"],self.b)
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tenant_password_change_events").fetchone()[0],0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tenant_password_change_failures").fetchone()[0],1)

    def test_wrong_current_password_rate_limit_is_user_scoped(self):
        for _ in range(tenant_password_change.MAX_FAILURES):
            with self.assertRaises(tenant_password_change.PasswordChangeDenied):
                self.manager.change(self.s1["token"],self.s1["csrf"],
                                    "wrong-current-password",PW_NEW)
        with self.assertRaises(tenant_password_change.PasswordChangeRateLimited):
            self.manager.change(self.s1["token"],self.s1["csrf"],PW_A,PW_NEW)
        self.assertTrue(self.manager.change(
            self.sb["token"],self.sb["csrf"],PW_B,"new-bob-secret-long-enough")["passwordChanged"])
        self.assertEqual(self.identity.principal(self.s1["token"])["user_id"],self.a)
        self.assertIsNone(self.identity.principal(self.sb["token"]))

    def test_concurrent_password_change_wins_once(self):
        def try_change(session):
            try:
                self.manager.change(session["token"],session["csrf"],PW_A,PW_NEW)
                return "changed"
            except tenant_password_change.PasswordChangeDenied:
                return "denied"
        with ThreadPoolExecutor(max_workers=2) as pool:
            decisions=list(pool.map(try_change,(self.s1,self.s2)))
        self.assertEqual(sorted(decisions),["changed","denied"])
        self.assertEqual(self.identity.principal(self.sb["token"])["user_id"],self.b)
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM tenant_password_change_events").fetchone()[0],1)

    def test_disabled_member_rejected_and_nonprepared_database_denied(self):
        with sqlite3.connect(self.path) as con:
            con.execute("UPDATE tenant_users SET disabled_at='2026-11-10' WHERE user_id=?",(self.a,))
        with self.assertRaises(tenant_password_change.PasswordChangeDenied):
            self.manager.change(self.s1["token"],self.s1["csrf"],PW_A,PW_NEW)
        self.assertEqual(self.identity.principal(self.sb["token"])["user_id"],self.b)
        with tempfile.TemporaryDirectory(prefix="edgepilot-pw-empty-") as temp:
            with self.assertRaises(RuntimeError):
                tenant_password_change.setup(temp+"/unprepared.db")


if __name__=="__main__":
    unittest.main()
