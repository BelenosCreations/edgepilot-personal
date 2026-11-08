import unittest
from engine import connection_check

BROKER = lambda: {'accounts':[{'accountId':'private-ID-123','accountType':'BROKERAGE'}]}
PORTFOLIO = lambda acc: {'totalAccountValue':'123.45','positions':[]}

class PublicConnectionTests(unittest.TestCase):
    def test_not_configured_does_not_call_broker(self):
        def no():raise AssertionError('should never call broker')
        r=connection_check.verify(False,no,'',lambda acc:no())
        self.assertEqual(r['broker'],'not_configured')
        self.assertFalse(r['tradingEnabled'])
    def test_accounts_but_none_selected(self):
        r=connection_check.verify(True,BROKER,'',PORTFOLIO)
        self.assertEqual(r['broker'],'verified')
        self.assertEqual(r['accountCount'],1)
        self.assertEqual(r['selectedAccount'],'none')
        self.assertNotIn('private-ID',str(r))
    def test_selected_broker_portfolio(self):
        r=connection_check.verify(True,BROKER,'private-ID-123',PORTFOLIO)
        self.assertEqual(r['portfolio'],'verified')
        self.assertEqual(r['selectedAccount'],'verified')
        self.assertNotIn('123.45',str(r))
        self.assertFalse(r['tradingEnabled'])
    def test_unrecognized_account_not_loaded(self):
        def no(acc):raise AssertionError('should not load portfolio')
        r=connection_check.verify(True,BROKER,'not-my-account',no)
        self.assertEqual(r['selectedAccount'],'not_available')
    def test_broker_api_failure(self):
        def fail():raise RuntimeError('TOP_SECRET')
        r=connection_check.verify(True,fail,'',PORTFOLIO)
        self.assertEqual(r['broker'],'failed')
        self.assertNotIn('TOP_SECRET',str(r))
    def test_bad_portfolio_shape_fails_closed(self):
        r=connection_check.verify(True,BROKER,'private-ID-123',lambda acc:{'totalAccountValue':'invalid','positions':[]})
        self.assertEqual(r['portfolio'],'failed')
    def test_missing_accounts_fails_closed(self):
        r=connection_check.verify(True,lambda:{},'',PORTFOLIO)
        self.assertEqual(r['broker'],'failed')
    def test_negative_balance_is_rejected(self):
        r=connection_check.verify(True,BROKER,'private-ID-123',lambda acc:{'totalAccountValue':'-1','positions':[]})
        self.assertEqual(r['portfolio'],'failed')

if __name__=='__main__':unittest.main()
