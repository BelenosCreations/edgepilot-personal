"""Flask test-client checks. CI installs requirements to run these."""
import os
import importlib.util
import tempfile
import unittest
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec('flask') and importlib.util.find_spec('dotenv'), 'Flask HTTP tests require installed backend dependencies')
class HttpSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            'EDGE_DB_PATH': self.temp.name + '/test.db',
            'EDGE_APP_TOKEN': 'valid-test-token-with-at-least-32-chars-0123456789',
            'PUBLIC_API_SECRET': ''
        })
        self.env.start()
        import importlib
        import app
        self.appmod = importlib.reload(app)
        self.client = self.appmod.app.test_client()
        self.origin = {'Origin':'https://edgepilot.example.test'}
        self.base_url = 'https://edgepilot.example.test'

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def sign_in(self):
        return self.client.post('/api/login',base_url=self.base_url,headers=self.origin,
            json={'accessToken':'valid-test-token-with-at-least-32-chars-0123456789'})

    def test_health_open_but_sensitive_api_closed(self):
        self.assertEqual(self.client.get('/healthz',base_url=self.base_url).status_code,200)
        self.assertEqual(self.client.get('/api/health',base_url=self.base_url).status_code,401)

    def test_legacy_header_no_longer_authenticates(self):
        r=self.client.get('/api/health',base_url=self.base_url,headers={
            'X-Edge-Token':'valid-test-token-with-at-least-32-chars-0123456789'})
        self.assertEqual(r.status_code,401)

    def test_secure_cookie_session_and_logout(self):
        login=self.sign_in()
        self.assertEqual(login.status_code,200)
        cookie=login.headers['Set-Cookie']
        for marker in ('__Host-edgepilot_session','Secure','HttpOnly','SameSite=Strict','Path=/'):
            self.assertIn(marker,cookie)
        self.assertNotIn('valid-test-token',login.get_data(as_text=True))
        health=self.client.get('/api/health',base_url=self.base_url)
        self.assertEqual(health.status_code,200)
        self.assertIn('0.19.15',health.get_json()['version'])
        csrf=login.get_json()['csrf']
        no_csrf=self.client.post('/api/disarm',base_url=self.base_url,headers=self.origin,json={})
        self.assertEqual(no_csrf.status_code,403)
        cross_site=self.client.post('/api/disarm',base_url=self.base_url,headers={
            'Origin':'https://attacker.example'},json={})
        self.assertEqual(cross_site.status_code,403)
        allowed=self.client.post('/api/disarm',base_url=self.base_url,headers={**self.origin,
            'X-Edge-CSRF':csrf},json={})
        self.assertEqual(allowed.status_code,200)
        logout=self.client.post('/api/logout',base_url=self.base_url,headers={**self.origin,
            'X-Edge-CSRF':csrf},json={})
        self.assertEqual(logout.status_code,200)
        self.assertEqual(self.client.get('/api/health',base_url=self.base_url).status_code,401)

    def test_session_refresh_rotates_csrf(self):
        login=self.sign_in()
        self.assertEqual(login.status_code,200)
        old=login.get_json()['csrf']
        refresh=self.client.get('/api/session',base_url=self.base_url)
        self.assertEqual(refresh.status_code,200)
        new=refresh.get_json()['csrf']
        self.assertNotEqual(new,old)
        self.assertEqual(self.client.post('/api/disarm',base_url=self.base_url,
            headers={**self.origin,'X-Edge-CSRF':old},json={}).status_code,403)
        self.assertEqual(self.client.post('/api/disarm',base_url=self.base_url,
            headers={**self.origin,'X-Edge-CSRF':new},json={}).status_code,200)

    def test_login_rejects_cross_origin(self):
        r=self.client.post('/api/login',base_url=self.base_url,
            headers={'Origin':'https://attacker.example'},json={'accessToken':'valid-test-token-with-at-least-32-chars-0123456789'})
        self.assertEqual(r.status_code,403)

    def test_invalid_token_rejected(self):
        r=self.client.post('/api/login',base_url=self.base_url,headers=self.origin,
            json={'accessToken':'wrong-token'})
        self.assertEqual(r.status_code,401)

    def test_sensitive_headers(self):
        response=self.client.get('/',base_url=self.base_url)
        self.assertEqual(response.status_code,200)
        self.assertIn('frame-ancestors',response.headers['Content-Security-Policy'])
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertIn('max-age',response.headers['Strict-Transport-Security'])


    def test_public_settings_encryption_is_required_and_route_is_protected(self):
        from cryptography.fernet import Fernet
        self.assertEqual(self.client.get('/api/broker/credentials/status',base_url=self.base_url).status_code,401)
        login=self.sign_in()
        csrf=login.get_json()['csrf']
        secret='Public-TEST-KEY-DO-NOT-USE-11112222333344'
        with patch.dict(os.environ,{'EDGE_CREDENTIAL_KEY':''}):
            resp=self.client.post('/api/broker/credentials',base_url=self.base_url,
                headers={**self.origin,'X-Edge-CSRF':csrf},json={'secret':secret})
            self.assertEqual(resp.status_code,503)
        with patch.dict(os.environ,{'EDGE_CREDENTIAL_KEY':Fernet.generate_key().decode()}):
            bad=self.client.post('/api/broker/credentials',base_url=self.base_url,
                headers={'Origin':'https://evil.example','X-Edge-CSRF':csrf},json={'secret':secret})
            self.assertEqual(bad.status_code,403)
            resp=self.client.post('/api/broker/credentials',base_url=self.base_url,
                headers={**self.origin,'X-Edge-CSRF':csrf},json={'secret':secret})
            self.assertEqual(resp.status_code,200)
            status=self.client.get('/api/broker/credentials/status',base_url=self.base_url)
            self.assertTrue(status.get_json()['configured'])
            self.assertTrue(status.get_json()['usable'])
            self.assertNotIn(secret,status.get_data(as_text=True))
            self.assertNotIn(secret,self.client.get('/api/dashboard',base_url=self.base_url).get_data(as_text=True))
            import sqlite3
            with sqlite3.connect(self.temp.name+'/test.db') as conn:
                cipher=conn.execute('SELECT ciphertext FROM broker_credentials WHERE provider=?',('public',)).fetchone()[0]
            self.assertNotIn(secret.encode(),cipher)
            resp=self.client.delete('/api/broker/credentials',base_url=self.base_url,
                headers={**self.origin,'X-Edge-CSRF':csrf})
            self.assertEqual(resp.status_code,200)
            self.assertFalse(self.client.get('/api/broker/credentials/status',base_url=self.base_url).get_json()['configured'])
            self.assertEqual(self.appmod.settings()['account_id'],'')


if __name__=='__main__':
    unittest.main()
