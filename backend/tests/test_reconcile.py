import os,tempfile,unittest
from engine import reconcile

class SyncTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.db=os.path.join(self.t.name,'x.db');reconcile.setup(self.db)
        self.p={'totalAccountValue':'100','cash':'20','positions':[{'instrument':{'symbol':'ABC'},'quantity':'2'}],'orders':[]}
        self.tx={'id':'transaction-1','type':'TRADE','side':'BUY','symbol':'ABC','timestamp':'2026-11-08T12:00:00Z'}
    def tearDown(self):self.t.cleanup()
    def test_idempotent_capture(self):
        self.assertEqual(reconcile.reconcile(self.db,'acct',self.p,[self.tx])['importedTransactions'],1)
        self.assertEqual(reconcile.reconcile(self.db,'acct',self.p,[self.tx])['importedTransactions'],0)
        self.assertEqual(reconcile.overview(self.db,'acct')['totalTransactionsCaptured'],1)
    def test_incomplete_pages_do_not_commit(self):
        with self.assertRaisesRegex(ValueError,'Incomplete'):reconcile.reconcile(self.db,'acct',self.p,[self.tx],complete=False)
        self.assertEqual(reconcile.overview(self.db,'acct')['totalTransactionsCaptured'],0)
    def test_missing_transaction_id_fails_atomically(self):
        with self.assertRaisesRegex(ValueError,'stable broker ID'):reconcile.reconcile(self.db,'acct',self.p,[self.tx,{'type':'TRADE'}])
        self.assertEqual(reconcile.overview(self.db,'acct')['totalTransactionsCaptured'],0)
    def test_sale_is_unattributed_and_no_auto_execution(self):
        t={**self.tx,'id':'sale1','side':'SELL'}
        x=reconcile.reconcile(self.db,'acct',self.p,[t]);self.assertFalse(x['attributionVerified'])
        a=reconcile.overview(self.db,'acct')['alerts'][0]
        self.assertEqual(a['kind'],'UNATTRIBUTED_SELL');self.assertFalse(a['detail']['repurchaseAllowed'])
        self.assertTrue(reconcile.dismiss(self.db,'acct',a['id']))
        self.assertEqual(reconcile.overview(self.db,'acct')['alerts'],[])
    def test_position_decrease_not_called_manual_sale(self):
        reconcile.reconcile(self.db,'acct',self.p,[])
        p={**self.p,'positions':[{'instrument':{'symbol':'ABC'},'quantity':'1'}]}
        reconcile.reconcile(self.db,'acct',p,[])
        a=reconcile.overview(self.db,'acct')['alerts'][0]
        self.assertEqual(a['kind'],'POSITION_DECREASE');self.assertFalse(a['detail']['manualSaleConfirmed'])
    def test_broker_mutation_detected_without_overwriting(self):
        reconcile.reconcile(self.db,'acct',self.p,[self.tx])
        reconcile.reconcile(self.db,'acct',self.p,[{**self.tx,'quantity':'3'}])
        self.assertEqual(reconcile.overview(self.db,'acct')['alerts'][0]['kind'],'CHANGED_TRANSACTION')
    def test_reject_incomplete_portfolio(self):
        with self.assertRaisesRegex(ValueError,'required'):reconcile.reconcile(self.db,'acct',{'positions':[]},[])
        self.assertEqual(reconcile.overview(self.db,'acct')['totalTransactionsCaptured'],0)
if __name__=='__main__':unittest.main()
