"""Authenticated read-only scanner HTTP route tests with mocked upstream Public."""
import importlib,importlib.util,os,tempfile,unittest
from unittest.mock import patch

@unittest.skipUnless(importlib.util.find_spec('flask') and importlib.util.find_spec('dotenv'), 'Flask backend dependencies required')
class FifteenMinuteHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'EDGE_DB_PATH':self.tmp.name+'/db.sqlite',
            'EDGE_APP_TOKEN':'test-app-login-token-with-more-than-32-chars',
            'PUBLIC_API_SECRET':'', 'ENABLE_LIVE_ORDERS':'false'})
        self.env.start()
        import app
        self.mod=importlib.reload(app)
        self.client=self.mod.app.test_client()
        self.url='https://edgepilot.example.test'
    def tearDown(self):
        self.env.stop();self.tmp.cleanup()
    def sign_in(self):
        r=self.client.post('/api/login',base_url=self.url,
          headers={'Origin':self.url},json={'accessToken':'test-app-login-token-with-more-than-32-chars'})
        self.assertEqual(r.status_code,200)
    def test_no_unauthenticated_market_access(self):
        r=self.client.get('/api/markets/15-minute',base_url=self.url)
        self.assertEqual(r.status_code,401)
    def test_missing_broker_connection_does_not_query_upstream(self):
        self.sign_in()
        with patch.object(self.mod,'pub',side_effect=AssertionError('unexpected Public call')):
            r=self.client.get('/api/markets/15-minute',base_url=self.url)
        self.assertEqual(r.status_code,200)
        self.assertFalse(r.get_json()['connected'])
        self.assertEqual(r.get_json()['events'],[])
    def test_invalid_limit_rejected(self):
        self.sign_in()
        self.assertEqual(self.client.get('/api/markets/15-minute?limit=100',base_url=self.url).status_code,400)
    def test_provider_error_returns_sanitized_message(self):
        self.sign_in()
        with patch.dict(os.environ,{'PUBLIC_API_SECRET':'fake-legacy-test-secret'}),             patch.object(self.mod,'pub',side_effect=RuntimeError('sensitive test upstream content')):
            r=self.client.get('/api/markets/15-minute',base_url=self.url)
        self.assertEqual(r.status_code,502)
        self.assertNotIn('sensitive',r.get_data(as_text=True))
    def test_request_only_broker_queries_and_never_orders(self):
        self.sign_in()
        from test_fifteen_minute import summary,details
        def fake_pub(method,path,body=None):
            if 'summary' in path:return summary()
            if 'details' in path:return details()
            raise AssertionError('Unexpected API route')
        with patch.dict(os.environ,{'PUBLIC_API_SECRET':'fake-legacy-test-secret'}),             patch.object(self.mod,'pub',side_effect=fake_pub) as call:
            r=self.client.get('/api/markets/15-minute',base_url=self.url)
        self.assertEqual(r.status_code,200)
        self.assertEqual(len(r.get_json()['events']),1)
        self.assertTrue(r.get_json()['readOnly'])
        self.assertTrue(all('order' not in x.args[1] for x in call.call_args_list))

if __name__=='__main__':unittest.main()
