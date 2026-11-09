"""Mobile navigation and separation contract for the v0.19.16 web release."""
from pathlib import Path
from html.parser import HTMLParser
import unittest

ROOT=Path(__file__).resolve().parents[2]
HTML=(ROOT/'backend/static/index.html')
JS=(ROOT/'backend/static/assets/app.js')


class TagCount(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sections=0
        self.section_closes=0
        self.ids=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='section':
            self.sections+=1
        if 'id' in attrs:
            self.ids.append(attrs['id'])
    def handle_endtag(self,tag):
        if tag=='section':
            self.section_closes+=1


class TradingNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=HTML.read_text(encoding='utf-8')
        cls.js=JS.read_text(encoding='utf-8')

    def panel(self,id):
        anchor='<section class="section" id="'+id+'">'
        if id=='dash':
            anchor='<section class="section active" id="dash">'
        return self.html.split(anchor,1)[1].split('</section>',1)[0]

    def test_navigation_exposes_three_distinct_engines_and_more(self):
        nav=self.html.split('<nav class="nav"',1)[1].split('</nav>',1)[0]
        self.assertEqual(nav.count('data-nav='),5)
        for name in ('dash','auto','micro','fifteen','more'):
            self.assertIn('data-nav="'+name+'"',nav)
            self.assertIn("tab('"+name+"')",nav)
        for name in ('funds','markets','trade','ai','settings'):
            self.assertIn("tab('"+name+"')",self.panel('more'))
        for id in ('auto','micro','fifteen'):
            self.assertIn('NOT ACTIVE',self.panel(id))

    def test_micro_controls_moved_out_of_settings(self):
        self.assertNotIn('id="microEnabled"',self.panel('settings'))
        self.assertNotIn('Micro-Trading: adaptive opportunity screen',self.html)
        self.assertIn('id="microEnabled"',self.panel('micro'))
        self.assertIn('id="microAllocation"',self.panel('micro'))
        self.assertIn('id="microLossStop"',self.panel('micro'))
        self.assertIn('id="microProfitTarget"',self.panel('micro'))
        self.assertIn('id="microMaxTradesSession"',self.panel('micro'))
        self.assertIn('id="microResult"',self.panel('micro'))

    def test_fifteen_minute_scanner_moves_to_dedicated_tab(self):
        self.assertIn('id="fifteenStatus"',self.panel('fifteen'))
        self.assertIn('loadFifteenMinuteMarkets()',self.panel('fifteen'))
        self.assertNotIn('id="fifteenStatus"',self.panel('markets'))
        self.assertIn('id="fifteenMinRemaining"',self.panel('fifteen'))
        self.assertIn('id="fifteenMaxSpread"',self.panel('fifteen'))

    def test_funds_shortcuts_are_read_only_and_functional(self):
        self.assertIn("openFunds('deposit')",self.panel('dash'))
        self.assertIn("openFunds('withdraw')",self.panel('dash'))
        self.assertIn('id="fundsHistoryList"',self.panel('funds'))
        self.assertIn('id="fundsAccountValue"',self.panel('funds'))
        self.assertIn('Not available in EdgePilot',self.panel('funds'))
        for name in ('openFunds','selectFundsGuide','loadFundsHistory','loadEngineProfiles','saveEngineConfig'):
            self.assertIn('function '+name+'(',self.js)
        self.assertIn("api('funds/transfer-history')",self.js)
        self.assertIn("api('engines/'+engine+'/config','POST',payload)",self.js)
        self.assertNotIn("api('funds/transfer-history','POST'",self.js)

    def test_unique_ids_and_closed_sections(self):
        p=TagCount()
        p.feed(self.html)
        self.assertEqual(p.sections,p.section_closes)
        self.assertEqual(len(p.ids),len(set(p.ids)), 'Duplicate DOM IDs cause unexpected settings updates')
        self.assertEqual(p.sections,11)
        self.assertIn('src="/assets/edgepilot-brand.png"',self.html)


if __name__=='__main__':
    unittest.main()
