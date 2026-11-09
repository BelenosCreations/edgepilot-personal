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
        self.assertIn('0.2',health.get_json()['version'])
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


    def test_automation_master_routes_require_session_csrf_and_never_enable_live(self):
        endpoint='/api/automation/status'
        self.assertEqual(self.client.get(endpoint,base_url=self.base_url).status_code,401)
        self.assertEqual(self.client.post('/api/automation/config',base_url=self.base_url,
                          headers=self.origin,json={}).status_code,401)
        login=self.sign_in()
        self.assertEqual(login.status_code,200)
        csrf=login.get_json()['csrf']
        status=self.client.get(endpoint,base_url=self.base_url)
        self.assertEqual(status.status_code,200)
        self.assertFalse(status.get_json()['master']['liveTradingAvailable'])
        self.assertIn('observationHealth',status.get_json())
        self.assertIsNone(status.get_json()['observationHealth']['lastCycle'])
        headers={**self.origin,'X-Edge-CSRF':csrf}
        self.assertEqual(self.client.post('/api/automation/config',base_url=self.base_url,
                          headers=self.origin,json={}).status_code,403)
        cfg={'mode':'paper','risk_level':'balanced','paper_capital':'2000.00',
             'protected_pct':'50.00','profit_lock_pct':'0.00',
             'compound_pct':'0.00','reserve_profit_pct':'0.00'}
        self.assertEqual(self.client.post('/api/automation/config',base_url=self.base_url,
                         headers=headers,json={**cfg,'mode':'live'}).status_code,400)
        saved=self.client.post('/api/automation/config',base_url=self.base_url,
                               headers=headers,json=cfg)
        self.assertEqual(saved.status_code,200)
        self.assertFalse(saved.get_json()['master']['enabled'])
        self.assertEqual(self.appmod.settings()['live_armed'],'0')
        self.assertEqual(self.client.post('/api/automation/auto/start',base_url=self.base_url,
                         headers=headers,json={}).status_code,400)
        self.assertEqual(self.client.post('/api/automation/unknown/start',base_url=self.base_url,
                         headers=headers,json={'confirmation':'START PAPER'}).status_code,400)

    def test_emergency_stop_latches_and_reset_never_restarts_engine(self):
        login=self.sign_in()
        headers={**self.origin,'X-Edge-CSRF':login.get_json()['csrf']}
        self.assertEqual(self.client.post('/api/disarm',base_url=self.base_url,
                                         headers=headers,json={}).status_code,200)
        state=self.client.get('/api/automation/status',base_url=self.base_url).get_json()
        self.assertEqual(state['master']['emergency'],1)
        self.assertEqual(state['engines']['auto']['state'],'paused')
        self.assertEqual(self.client.post('/api/automation/emergency/reset',base_url=self.base_url,
                                         headers=headers,json={}).status_code,400)
        reset=self.client.post('/api/automation/emergency/reset',base_url=self.base_url,
                               headers=headers,json={'confirmation':'RESET EMERGENCY'})
        self.assertEqual(reset.status_code,200)
        self.assertEqual(reset.get_json()['master']['emergency'],0)
        self.assertEqual(reset.get_json()['engines']['auto']['state'],'paused')

    def test_engine_profiles_are_authenticated_inactive_and_validate_input(self):
        get_route='/api/engines/config'
        post_route='/api/engines/micro/config'
        self.assertEqual(self.client.get(get_route,base_url=self.base_url).status_code,401)
        self.assertEqual(self.client.post(post_route,base_url=self.base_url,headers=self.origin,json={}).status_code,401)
        login=self.sign_in()
        csrf=login.get_json()['csrf']
        self.assertEqual(self.client.post(post_route,base_url=self.base_url,headers=self.origin,json={}).status_code,403)
        headers={**self.origin,'X-Edge-CSRF':csrf}
        data=self.client.get(get_route,base_url=self.base_url).get_json()
        self.assertTrue(data['activationAvailable'])
        self.assertEqual(set(data['profiles']),{'auto','micro','fifteen'})
        plan=self.appmod.engine_config.DEFAULTS['micro'].copy()
        plan.update({'allocation':'20.00','loss_stop':'5.00','max_per_trade':'2.00'})
        result=self.client.post(post_route,base_url=self.base_url,headers=headers,json=plan)
        self.assertEqual(result.status_code,200)
        self.assertFalse(result.get_json()['profile']['active'])
        self.assertFalse(result.get_json()['profile']['liveTradingAvailable'])
        self.assertEqual(result.get_json()['profile']['config']['allocation'],'20.00')
        self.assertFalse(self.client.get(get_route,base_url=self.base_url).get_json()['profiles']['auto']['configured'])
        self.assertEqual(self.appmod.settings()['live_armed'],'0')
        bad={**plan,'active':True}
        self.assertEqual(self.client.post(post_route,base_url=self.base_url,headers=headers,json=bad).status_code,400)
        self.assertEqual(self.client.post(post_route,base_url=self.base_url,headers={'Origin':'https://evil.example','X-Edge-CSRF':csrf},json=plan).status_code,403)
        self.assertEqual(self.client.post('/api/engines/unknown/config',base_url=self.base_url,headers=headers,json=plan).status_code,400)

    def test_funds_history_is_auth_protected_and_never_exposes_bank_details(self):
        endpoint='/api/funds/transfer-history'
        self.assertEqual(self.client.get(endpoint,base_url=self.base_url).status_code,401)
        login=self.sign_in()
        self.assertEqual(login.status_code,200)
        empty=self.client.get(endpoint,base_url=self.base_url).get_json()
        self.assertFalse(empty['historyCaptured'])
        self.appmod.put('account_id','acct-A')
        import sqlite3
        with sqlite3.connect(self.temp.name+'/test.db') as c:
            c.execute('''INSERT INTO sync_transactions(account,tx_id,timestamp,symbol,side,type,subtype,raw_json,first_seen)
                         VALUES(?,?,?,?,?,?,?,?,?)''',
                      ('acct-A','x1','2026-11-08T17:00:00Z','','','DEPOSIT','ACH',
                       '{"bankAccount":"secret-bank-9876","amount":"123.45"}','2026-11-08T18:00:00Z'))
            c.execute('''INSERT INTO sync_runs(account,ts,status,imported_count,pages,message)
                         VALUES(?,?,?,?,?,?)''',('acct-A','2026-11-08T18:00:00Z','READ_ONLY_COMPLETE',1,1,'synced'))
        out=self.client.get(endpoint,base_url=self.base_url)
        self.assertEqual(out.status_code,200)
        payload=out.get_json()
        self.assertTrue(payload['historyCaptured'])
        self.assertEqual(len(payload['entries']),1)
        self.assertFalse(payload['entries'][0]['verifiedBankTransfer'])
        self.assertNotIn('secret-bank-9876',out.get_data(as_text=True))
        self.assertNotIn('123.45',out.get_data(as_text=True))
        self.assertEqual(self.client.post(endpoint,base_url=self.base_url,headers=self.origin,json={}).status_code,403)

    def test_bulk_sync_acknowledgement_requires_session_csrf_and_selected_account(self):
        endpoint='/api/sync/alerts/acknowledge-all'
        self.assertEqual(self.client.post(endpoint,base_url=self.base_url,headers=self.origin,json={}).status_code,401)
        login=self.sign_in()
        self.assertEqual(login.status_code,200)
        csrf=login.get_json()['csrf']
        self.assertEqual(self.client.post(endpoint,base_url=self.base_url,headers=self.origin,json={}).status_code,403)
        good_headers={**self.origin,'X-Edge-CSRF':csrf}
        self.assertEqual(self.client.post(endpoint,base_url=self.base_url,headers=good_headers,json={}).status_code,400)
        self.appmod.put('account_id','acct-A')
        with self.appmod.reconcile.db(str(self.appmod.DB)) as c:
            for acct,number in [('acct-A','1'),('acct-A','2'),('acct-B','3')]:
                c.execute("INSERT INTO sync_alerts(account,kind,fingerprint,message,detail_json,created) VALUES(?,?,?,?,?,?)",
                          (acct,'UNATTRIBUTED_SELL','route-test-'+number,'Review sale','{"repurchaseAllowed": false}','2026-11-08T00:00:00Z'))
        rejected=self.client.post(endpoint,base_url=self.base_url,headers={'Origin':'https://evil.example','X-Edge-CSRF':csrf},json={})
        self.assertEqual(rejected.status_code,403)
        response=self.client.post(endpoint,base_url=self.base_url,headers=good_headers,json={})
        self.assertEqual(response.status_code,200)
        body=response.get_json()
        self.assertEqual(body['acknowledgedCount'],2)
        self.assertEqual(body['openAlertCount'],0)
        self.assertEqual(self.appmod.reconcile.overview(str(self.appmod.DB),'acct-A')['openAlertCount'],0)
        self.assertEqual(self.appmod.reconcile.overview(str(self.appmod.DB),'acct-B')['openAlertCount'],1)
        self.assertFalse(self.client.get('/api/dashboard',base_url=self.base_url).get_json()['liveTradingAvailable'])
        repeat=self.client.post(endpoint,base_url=self.base_url,headers=good_headers,json={})
        self.assertEqual(repeat.status_code,200)
        self.assertEqual(repeat.get_json()['acknowledgedCount'],0)

    def test_protected_balance_accepts_zero_and_ninety_nine_and_rejects_out_of_range(self):
        sign_in=self.sign_in()
        self.assertEqual(sign_in.status_code,200)
        csrf=sign_in.get_json()['csrf']
        headers={**self.origin,'X-Edge-CSRF':csrf}
        for pct in ('0','99'):
            with self.subTest(accepted=pct):
                result=self.client.post('/api/settings',base_url=self.base_url,
                    headers=headers,json={'protected_pct':pct})
                self.assertEqual(result.status_code,200)
                self.assertEqual(result.get_json()['settings']['protected_pct'],pct)
                self.assertEqual(self.appmod.settings()['live_armed'],'0')
        for pct in ('-1','100','101'):
            with self.subTest(rejected=pct):
                result=self.client.post('/api/settings',base_url=self.base_url,
                    headers=headers,json={'protected_pct':pct})
                self.assertEqual(result.status_code,400)
                self.assertIn('0–99%',result.get_json()['error'])
                self.assertEqual(self.appmod.settings()['protected_pct'],'99')



if __name__=='__main__':
    unittest.main()
