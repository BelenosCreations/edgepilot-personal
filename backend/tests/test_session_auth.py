"""No HTTP dependencies: portable session and login-rate-limit unit tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.session_auth import (
    COOKIE_NAME,
    FAILURE_WINDOW_SECONDS,
    MAX_FAILURES_PER_SOURCE,
    SESSION_SECONDS,
    SessionStore,
)


class SessionAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SessionStore(str(Path(self.tmp.name) / 'edgepilot.db'))
        self.store.setup()

    def tearDown(self):
        self.tmp.cleanup()

    def test_unique_session_tokens(self):
        a, a_csrf, exp = self.store.issue(now=100)
        b, b_csrf, _ = self.store.issue(now=100)
        self.assertNotEqual(a, b)
        self.assertNotEqual(a_csrf, b_csrf)
        self.assertEqual(exp, 100 + SESSION_SECONDS)
        self.assertTrue(self.store.validate(a, a_csrf, now=100))
        self.assertTrue(self.store.validate(b, b_csrf, now=100))

    def test_cookie_name_uses_host_prefix(self):
        self.assertTrue(COOKIE_NAME.startswith('__Host-'))

    def test_session_expires_and_fails_closed(self):
        token, csrf, exp = self.store.issue(now=100)
        self.assertTrue(self.store.validate(token, now=exp - 1))
        self.assertFalse(self.store.validate(token, now=exp))
        self.assertFalse(self.store.validate(token, csrf, now=exp))

    def test_wrong_token_and_csrf_rejected(self):
        token, csrf, _ = self.store.issue(now=10)
        self.assertFalse(self.store.validate(token+'x', now=10))
        self.assertFalse(self.store.validate(token, csrf+'x', now=10))
        self.assertFalse(self.store.validate('', now=10))
        self.assertFalse(self.store.validate(token, '', now=10))
        self.assertTrue(self.store.validate(token, csrf, now=10))

    def test_logout_revokes_session(self):
        token, csrf, _ = self.store.issue(now=100)
        self.store.revoke(token)
        self.assertFalse(self.store.validate(token, now=100))
        self.store.revoke(token)

    def test_server_does_not_store_plain_tokens(self):
        import sqlite3
        token, csrf, _ = self.store.issue(now=100)
        with sqlite3.connect(self.store.db_path) as conn:
            row = conn.execute('SELECT token_sha256,csrf_sha256 FROM edge_sessions').fetchone()
        self.assertNotIn(token,row)
        self.assertNotIn(csrf,row)

    def test_csrf_rotation_on_page_reload(self):
        token, csrf, _ = self.store.issue(now=100)
        new_csrf = self.store.renew_csrf(token, now=101)
        self.assertTrue(new_csrf)
        self.assertNotEqual(csrf,new_csrf)
        self.assertTrue(self.store.validate(token,new_csrf,now=101))
        self.assertFalse(self.store.validate(token,csrf,now=101))
        self.assertIsNone(self.store.renew_csrf('not-a-cookie',now=101))

    def test_rate_limited_by_source_hash(self):
        self.assertFalse(self.store.blocked('192.0.2.1',now=1000))
        for _ in range(MAX_FAILURES_PER_SOURCE):
            self.store.failed_login('192.0.2.1',now=1000)
        self.assertTrue(self.store.blocked('192.0.2.1',now=1000))
        self.assertFalse(self.store.blocked('192.0.2.2',now=1000))
        self.assertFalse(self.store.blocked('192.0.2.1',now=1000+FAILURE_WINDOW_SECONDS+1))

    def test_success_clears_failures(self):
        self.store.failed_login('192.0.2.1',now=200)
        self.store.successful_login('192.0.2.1')
        for _ in range(MAX_FAILURES_PER_SOURCE-1):
            self.store.failed_login('192.0.2.1',now=200)
        self.assertFalse(self.store.blocked('192.0.2.1',now=200))

    def test_persisted_session_across_store_instances(self):
        token, csrf, _ = self.store.issue(now=100)
        fresh = SessionStore(self.store.db_path)
        fresh.setup()
        self.assertTrue(fresh.validate(token,csrf,now=101))

    def test_double_login_does_not_revoke_other_session(self):
        a,csrf1,_ = self.store.issue(now=200)
        b,csrf2,_ = self.store.issue(now=201)
        self.assertTrue(self.store.validate(a,csrf1,now=202))
        self.assertTrue(self.store.validate(b,csrf2,now=202))


if __name__ == '__main__':
    unittest.main()
