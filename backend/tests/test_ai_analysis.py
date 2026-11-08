import tempfile,unittest,os
from engine import ai_analysis as ai
class TestAI(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=os.path.join(self.tmp.name,'db.sqlite');ai.setup(self.path)
 def tearDown(self):self.tmp.cleanup()
 def test_status_disabled(self):
  s=ai.status(self.path,{'ai_enabled':'0','ai_monthly_budget_usd':'0'},False)
  self.assertFalse(s['enabled']);self.assertFalse(s['credentialConfigured'])
 def test_budget_rejects(self):
  with self.assertRaises(ai.AIError):ai.reserve(self.path,{'ai_monthly_budget_usd':'0.10'},'q','stock','ABC')
 def test_reservation_limit(self):
  s={'ai_monthly_budget_usd':'0.40'}
  ai.reserve(self.path,s,'q1','stock','ABC');ai.reserve(self.path,s,'q2','etf','XYZ')
  with self.assertRaises(ai.AIError):ai.reserve(self.path,s,'q3','prediction','X')
  self.assertEqual(ai.status(self.path,{'ai_enabled':'1',**s},True)['estimatedBudgetReservedUsd'],'0.40')
 def test_no_history_for_reserved(self):
  ai.reserve(self.path,{'ai_monthly_budget_usd':'1'},'q','stock','ABC')
  self.assertEqual(ai.history(self.path),[])
 def test_extract_text(self):
  self.assertEqual(ai.extract_text({'output':[{'type':'message','content':[{'type':'output_text','text':'OK'}]}]}),'OK')
if __name__=='__main__':unittest.main()
