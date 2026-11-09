"""Regression for accurate watchlist-only market research coverage."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
APP=(ROOT/'backend/app.py').read_text(encoding='utf-8')
JS=(ROOT/'backend/static/assets/app.js').read_text(encoding='utf-8')


class WatchlistCoverageTests(unittest.TestCase):
    def test_watchlist_uses_manual_count_not_unfetched_broker_universe(self):
        self.assertIn("'watchlistSymbols':len(manual)",APP)
        self.assertIn("d.mode==='watchlist'",JS)
        self.assertIn("d.coverage.watchlistSymbols",JS)
        self.assertIn("watchlist stocks checked",JS)
        self.assertNotIn("stocks sampled from ${d.coverage.eligibleEquitiesReported} listed",JS)

    def test_scanner_remains_read_only(self):
        self.assertIn("'readOnly':True,'eligibleForLiveExecution':False",APP)
        self.assertIn("Research only; no trades.",JS)


if __name__=='__main__':
    unittest.main()
