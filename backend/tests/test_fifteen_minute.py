"""Public 15-minute scanner unit tests: synthetic payloads, no actual broker data."""
import unittest
from datetime import datetime, timezone, timedelta
from engine import fifteen_minute as f

NOW=datetime(2026,11,8,22,0,tzinfo=timezone.utc)
EVENT='KALSHI.KXBTC15M-26NOV082210'
YES=EVENT+'-10.Y'
NO=EVENT+'-10.N'

def stamp(offset):
    return (NOW+timedelta(seconds=offset)).isoformat().replace('+00:00','Z')

def summary(symbol=EVENT,close=600):
    return {'content':[{'eventSymbol':symbol,'title':'BTC Up or Down - 15 minutes','resolved':False,'halted':False,'resolutionTime':stamp(close)}]}

def details(symbol=EVENT,close=600):
    return {'eventSymbol':symbol,'title':'BTC Up or Down','resolved':False,'halted':False,
        'outcomes':[{'title':'Target Price: $80,811.49','state':'STATE_OPEN','trading':'BUY_AND_SELL',
        'timeline':{'openTime':stamp(close-900),'closeTime':stamp(close)},
        'contracts':[{'symbol':YES,'predictedOutcome':'YES','bid':'0.026','ask':'0.027'},
                     {'symbol':NO,'predictedOutcome':'NO','bid':'0.973','ask':'0.974'}]}]}

class FifteenMinuteTests(unittest.TestCase):
    def test_documented_frequency_filter_and_read_only_calls(self):
        calls=[]
        def pub(method,path,body=None):
            calls.append((method,path,body))
            if 'summary' in path: return summary()
            return details()
        result=f.discover(pub,now=NOW)
        self.assertEqual([x[0] for x in calls],['POST','GET'])
        self.assertEqual(calls[0][2]['filters']['frequencies'],['FIFTEEN_MINUTES'])
        self.assertEqual(calls[0][2]['filters']['eventIds'],[])
        self.assertTrue(all('order' not in x[1] for x in calls))
        self.assertTrue(result['readOnly'])
        self.assertFalse(result['executionEnabled'])

    def test_fractional_cent_precision_and_break_even(self):
        row=f.parse_details(f.candidate_summaries(summary(),NOW)[0],details(),NOW)
        self.assertEqual(row['yes']['ask'],'0.027')
        self.assertEqual(row['yes']['spread'],'0.001')
        self.assertEqual(row['yes']['illustrativeBreakEvenPct'],'4.70')
        self.assertEqual(row['target'],'Target Price: $80,811.49')
        self.assertEqual(row['secondsRemainingAtCapture'],600)

    def test_no_expired_future_resolved_or_halted_summaries(self):
        raw=summary();raw['content']+= [
            {'eventSymbol':EVENT+'B','title':'future','resolved':False,'resolutionTime':stamp(1500)},
            {'eventSymbol':EVENT+'C','title':'past','resolved':False,'resolutionTime':stamp(-1)},
            {'eventSymbol':EVENT+'D','title':'settled','resolved':True,'resolutionTime':stamp(400)},
            {'eventSymbol':EVENT+'E','title':'halted','resolved':False,'halted':True,'resolutionTime':stamp(400)}]
        self.assertEqual(len(f.candidate_summaries(raw,NOW)),1)

    def test_summary_requires_actual_documented_response_shape(self):
        for invalid in [None,{}, {'content':{}},{'content':None}]:
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                f.candidate_summaries(invalid,NOW)

    def test_missing_timezone_rejected(self):
        with self.assertRaises(ValueError):f.timestamp('2026-11-08T22:00:00')

    def test_duplicate_or_missing_contracts_not_displayed(self):
        item=f.candidate_summaries(summary(),NOW)[0]
        response=details();response['outcomes'][0]['contracts'].pop()
        with self.assertRaises(ValueError): f.parse_details(item,response,NOW)
        response=details();response['outcomes'][0]['contracts'].append(response['outcomes'][0]['contracts'][0].copy())
        with self.assertRaises(ValueError): f.parse_details(item,response,NOW)

    def test_invalid_quotes_rejected(self):
        item=f.candidate_summaries(summary(),NOW)[0]
        for bid,ask in [('Infinity','0.3'),('0.6','0.4'),('abc','0.4'),('0','1.5')]:
            response=details();response['outcomes'][0]['contracts'][0].update(bid=bid,ask=ask)
            with self.subTest(bid=bid,ask=ask),self.assertRaises(ValueError):f.parse_details(item,response,NOW)

    def test_detail_identity_and_timeline_conflict_fail_closed(self):
        item=f.candidate_summaries(summary(),NOW)[0]
        cases=[]
        a=details();a['eventSymbol']='KALSHI.KXBTC15M-DIFFERENT';cases.append(a)
        a=details();a['outcomes'][0]['timeline']['closeTime']=stamp(1500);cases.append(a)
        a=details();a['outcomes'][0]['trading']='DISABLED';cases.append(a)
        a=details();a['halted']=True;cases.append(a)
        for response in cases:
            with self.subTest(response=str(response)[:80]),self.assertRaises(ValueError):f.parse_details(item,response,NOW)

    def test_does_not_fabricate_missing_quoted_market(self):
        calls=[]
        def pub(method,path,body=None):
            calls.append(path)
            return {'content':[]} if 'summary' in path else details()
        r=f.discover(pub,now=NOW)
        self.assertEqual(r['events'],[])
        self.assertEqual(len(calls),1)

    def test_pagination_dedup_and_bounded_detail_fetches(self):
        calls=[]
        def pub(method,path,body=None):
            calls.append(path)
            if 'summary' in path:
                if not body.get('nextToken'):return {**summary(),'nextToken':'next-page'}
                return summary()
            return details()
        r=f.discover(pub,limit=4,now=NOW)
        self.assertEqual(len(r['events']),1)
        self.assertEqual(r['coverage']['pagesFetched'],2)
        self.assertEqual(len(calls),3)

    def test_skips_failed_details_without_claiming_quotes(self):
        def pub(method,path,body=None):
            if 'summary' in path:return summary()
            raise TimeoutError('Quote service unavailable')
        r=f.discover(pub,now=NOW)
        self.assertEqual(r['events'],[])
        self.assertEqual(r['coverage']['skippedInvalid'],1)

    def test_rejects_invalid_limits(self):
        for limit in [0,9,True,'8']:
            with self.subTest(limit=limit),self.assertRaises(ValueError):f.discover(lambda *args:None,limit=limit,now=NOW)

if __name__=='__main__':unittest.main()
