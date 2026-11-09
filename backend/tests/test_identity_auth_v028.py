"""Independent identity authentication and zero legacy-account access regression."""
import importlib
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from engine import identity_auth, tenant_foundation


class IdentityRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=self.temp.name+'/identity.db'
        tenant_foundation.setup(self.path)
        identity_auth.setup(self.path)
        self.tenants=tenant_foundation.TenantStore(self.path)
        self.store=identity_auth.IdentityStore(self.path)
        self.alice=self.tenants.provision_user('First Person','owner')
        self.bob=self.tenants.provision_user('Another Person','member')
        self.store.provision(self.alice,'first_user','strong-example-password-0001')
        self.store.provision(self.bob,'second_user','strong-example-password-0002')

    def tearDown(self):
        self.temp.cleanup()

    def test_passwords_are_argon2id_hashes_no_plaintext_and_unique(self):
        with sqlite3.connect(self.path) as con:
            rows=con.execute('SELECT user_id,login_name,password_hash FROM tenant_identities').fetchall()
        self.assertEqual(len(rows),2)
        self.assertTrue(all(row[2].startswith('$argon2id$') for row in rows))
        self.assertTrue(all('strong-example-password' not in row[2] for row in rows))
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.provision(self.bob,'FIRST_USER','different-long-password-2026')

    def test_sessions_are_scoped_to_correct_user_and_csrf(self):
        a=self.store.authenticate('FIRST_USER','strong-example-password-0001','10.1.2.3')
        b=self.store.authenticate('second_user','strong-example-password-0002','10.1.2.4')
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        self.assertNotEqual(a['token'],b['token'])
        self.assertEqual(self.store.principal(a['token'],a['csrf'])['user_id'],self.alice)
        self.assertEqual(self.store.principal(b['token'],b['csrf'])['user_id'],self.bob)
        self.assertIsNone(self.store.principal(a['token'],b['csrf']))
        before=a['csrf']
        principal,new_csrf=self.store.rotate_csrf(a['token'])
        self.assertEqual(principal['user_id'],self.alice)
        self.assertIsNone(self.store.principal(a['token'],before))
        self.assertEqual(self.store.principal(a['token'],new_csrf)['user_id'],self.alice)
        self.store.revoke(a['token'])
        self.assertIsNone(self.store.principal(a['token']))
        self.assertIsNotNone(self.store.principal(b['token']))

    def test_disabled_user_and_password_rotation_revoke_sessions(self):
        a=self.store.authenticate('first_user','strong-example-password-0001','client')
        b=self.store.authenticate('second_user','strong-example-password-0002','client2')
        self.store.change_password(self.alice,'strong-example-password-0001',
                                   'fresh-new-password-example-8888')
        self.assertIsNone(self.store.principal(a['token']))
        self.assertIsNone(self.store.authenticate('first_user','strong-example-password-0001','client'))
        fresh=self.store.authenticate('first_user','fresh-new-password-example-8888','client')
        self.assertIsNotNone(fresh)
        self.store.revoke_all(self.alice)
        self.assertIsNone(self.store.principal(fresh['token']))
        self.assertIsNotNone(self.store.principal(b['token']))
        with sqlite3.connect(self.path) as con:
            con.execute('UPDATE tenant_users SET disabled_at=? WHERE user_id=?',
                        ('2026-11-09T00:00:00+00:00',self.bob))
        self.assertIsNone(self.store.principal(b['token']))
        self.assertIsNone(self.store.authenticate('second_user','strong-example-password-0002','client2'))

    def test_failed_logins_have_generic_outcome_and_rate_limit(self):
        for i in range(identity_auth.MAX_FAILURES):
            self.assertIsNone(self.store.authenticate('unknown-user','any-wrong-password','10.1.1.1',now=5000))
        with self.assertRaises(identity_auth.TooManyAttempts):
            self.store.authenticate('first_user','strong-example-password-0001','10.1.1.1',now=5000)
        # A separate IP is not blocked by another IP, unless the login name is blocked too.
        self.assertIsNotNone(self.store.authenticate(
            'first_user','strong-example-password-0001','10.2.2.2',now=5000))
        self.assertIsNotNone(self.store.authenticate(
            'first_user','strong-example-password-0001','10.1.1.1',now=5000+identity_auth.FAILURE_WINDOW_SECONDS+2))

    def test_input_validation_does_not_admit_user_secrets(self):
        for invalid in ('ab',' spaces ','A@B','\nfoo','éclair'):
            with self.assertRaises(ValueError):
                self.store.provision(self.alice,invalid,'strong-example-password-0001')
        for short in ('short','', 'pass\nword'):
            with self.assertRaises(ValueError):
                self.store.provision(self.alice,'third_name',short)
        self.assertIsNone(self.store.authenticate('first_user','bad','source'))


class IdentityHttpIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{
            'EDGE_DB_PATH':self.temp.name+'/site.db',
            'EDGE_TENANT_SCHEMA_PREPARE':'true',
            'EDGE_IDENTITY_AUTH_ENABLED':'true',
            'EDGE_APP_TOKEN':'only-legacy-session-secret-0123456789ABCDEF',
            'PUBLIC_API_SECRET':'',
            'EDGE_AUTOMATION_WORKER_ENABLED':'false'
        })
        self.env.start()
        import app
        self.mod=importlib.reload(app)
        self.client=self.mod.app.test_client()
        self.origin={'Origin':'https://edgepilot.example.test'}
        self.base='https://edgepilot.example.test'
        user=self.mod.tenant_foundation.TenantStore(str(self.mod.DB)).provision_user('Isolated User','member')
        self.mod.identity_store.provision(user,'isolated_user','strong-identity-password-2026')
        self.user=user

    def tearDown(self):
        self.env.stop()
        # The next tests importing app must not inherit test identity flags.
        import app
        importlib.reload(app)
        self.temp.cleanup()

    def identity_login(self):
        return self.client.post('/api/identity/login',headers=self.origin,base_url=self.base,
            json={'username':'isolated_user','password':'strong-identity-password-2026'})

    def test_identity_cookie_cannot_access_legacy_broker_or_automation(self):
        login=self.identity_login()
        self.assertEqual(login.status_code,200)
        cookie=login.headers['Set-Cookie']
        for marker in ('__Host-edgepilot_identity','HttpOnly','Secure','SameSite=Strict','Path=/'):
            self.assertIn(marker,cookie)
        self.assertNotIn('strong-identity-password',login.get_data(as_text=True))
        self.assertEqual(self.client.get('/api/health',base_url=self.base).status_code,401)
        self.assertEqual(self.client.get('/api/dashboard',base_url=self.base).status_code,401)
        self.assertEqual(self.client.get('/api/automation/status',base_url=self.base).status_code,401)
        self.assertEqual(self.client.get('/api/broker/credentials/status',base_url=self.base).status_code,401)
        self.assertEqual(self.client.get('/api/identity/session',base_url=self.base).get_json()['user']['userId'],self.user)
        self.assertEqual(self.client.get('/api/identity/session',base_url=self.base).get_json()['scope'],
                         'identity_only_no_broker_access')

    def test_identity_csrf_logout_and_cross_origin(self):
        self.assertEqual(self.client.post('/api/identity/login',base_url=self.base,headers={
            'Origin':'https://attacker.example'},
            json={'username':'isolated_user','password':'strong-identity-password-2026'}).status_code,403)
        login=self.identity_login()
        self.assertEqual(login.status_code,200)
        self.assertEqual(self.client.post('/api/identity/logout',base_url=self.base,
                                         headers=self.origin,json={}).status_code,403)
        rotated=self.client.get('/api/identity/session',base_url=self.base).get_json()
        self.assertEqual(self.client.post('/api/identity/logout',base_url=self.base,
                    headers={**self.origin,'X-Edge-Identity-CSRF':login.get_json()['csrf']},
                    json={}).status_code,403)
        ok=self.client.post('/api/identity/logout',base_url=self.base,
                    headers={**self.origin,'X-Edge-Identity-CSRF':rotated['csrf']},json={})
        self.assertEqual(ok.status_code,200)
        self.assertEqual(self.client.get('/api/identity/session',base_url=self.base).status_code,401)

    def test_legacy_login_cannot_access_identity_api(self):
        self.assertEqual(self.client.post('/api/login',base_url=self.base,headers=self.origin,
          json={'accessToken':'only-legacy-session-secret-0123456789ABCDEF'}).status_code,200)
        self.assertEqual(self.client.get('/api/health',base_url=self.base).status_code,200)
        self.assertEqual(self.client.get('/api/identity/session',base_url=self.base).status_code,401)
        self.assertEqual(self.client.post('/api/identity/provision',base_url=self.base,headers=self.origin,
                                         json={'username':'new_user','password':'any'}).status_code,401)


class IdentityDisabledDefaultTests(unittest.TestCase):
    def test_no_identity_routes_or_tenant_schema_activated_by_default(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{
          'EDGE_DB_PATH':temp+'/legacy.db','EDGE_IDENTITY_AUTH_ENABLED':'false',
          'EDGE_TENANT_SCHEMA_PREPARE':'false','EDGE_AUTOMATION_WORKER_ENABLED':'false'}):
            import app
            importlib.reload(app)
            client=app.app.test_client()
            self.assertEqual(client.post('/api/identity/login',
              base_url='https://edgepilot.example.test',
              headers={'Origin':'https://edgepilot.example.test'},
              json={'username':'anything','password':'anything'}).status_code,404)
            with sqlite3.connect(temp+'/legacy.db') as con:
                self.assertFalse(con.execute("""SELECT name FROM sqlite_master
                  WHERE type='table' AND name='tenant_identity_sessions'""").fetchone())
        import app
        importlib.reload(app)


if __name__=='__main__':
    unittest.main()
