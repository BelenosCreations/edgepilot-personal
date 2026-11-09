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
    def test_acknowledge_all_account_scoped_and_idempotent(self):
        import json
        # More than 50 alerts ensures the bulk action includes notices not on screen.
        with reconcile.db(self.db) as c:
            for i in range(60):
                c.execute("INSERT INTO sync_alerts(account,kind,fingerprint,message,detail_json,created) VALUES(?,?,?,?,?,?)",
                          ('acct','UNATTRIBUTED_SELL','bulk-'+str(i),'Review sale',json.dumps({'repurchaseAllowed':False}),'2026-11-08T00:00:00Z'))
            c.execute("INSERT INTO sync_alerts(account,kind,fingerprint,message,detail_json,created) VALUES(?,?,?,?,?,?)",
                      ('other','POSITION_DECREASE','other-bulk','Review other','{}','2026-11-08T00:00:00Z'))
        before=reconcile.overview(self.db,'acct')
        self.assertEqual(before['openAlertCount'],60)
        self.assertEqual(len(before['alerts']),50)
        self.assertEqual(reconcile.dismiss_all(self.db,'acct'),60)
        self.assertEqual(reconcile.dismiss_all(self.db,'acct'),0)
        after=reconcile.overview(self.db,'acct')
        self.assertEqual(after['openAlertCount'],0)
        self.assertEqual(after['alerts'],[])
        self.assertEqual(reconcile.overview(self.db,'other')['openAlertCount'],1)
        with reconcile.db(self.db) as c:
            rows=c.execute("SELECT state,detail_json FROM sync_alerts WHERE account='acct'").fetchall()
        self.assertEqual(len(rows),60)
        self.assertTrue(all(row['state']=='ACKNOWLEDGED' for row in rows))
        self.assertTrue(all(json.loads(row['detail_json'])['repurchaseAllowed'] is False for row in rows))

    def test_acknowledge_all_does_not_change_broker_history(self):
        transaction={**self.tx,'id':'sale-bulk','side':'SELL'}
        reconcile.reconcile(self.db,'acct',self.p,[transaction])
        self.assertEqual(reconcile.overview(self.db,'acct')['openAlertCount'],1)
        self.assertEqual(reconcile.dismiss_all(self.db,'acct'),1)
        self.assertEqual(reconcile.overview(self.db,'acct')['totalTransactionsCaptured'],1)
        with self.assertRaisesRegex(ValueError,'Select a Public account'):
            reconcile.dismiss_all(self.db,'')

    def test_reject_incomplete_portfolio(self):
        with self.assertRaisesRegex(ValueError,'required'):reconcile.reconcile(self.db,'acct',{'positions':[]},[])
        self.assertEqual(reconcile.overview(self.db,'acct')['totalTransactionsCaptured'],0)
if __name__=='__main__':unittest.main()
