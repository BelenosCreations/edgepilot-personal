"""XNYS cash equity regular-session test cases for market-closed paper gating."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from engine import stock_session


def utc(value):
    return datetime.fromisoformat(value.replace('Z','+00:00'))


class StockSessionTests(unittest.TestCase):
    def test_sunday_evening_snapshot_does_not_imply_market_open(self):
        self.assertEqual(stock_session.regular_session_state(utc('2026-11-09T03:09:00Z')), 'CLOSED')

    def test_regular_weekday_session_dst_correctness(self):
        self.assertEqual(stock_session.regular_session_state(utc('2026-11-09T15:00:00Z')), 'OPEN')
        self.assertEqual(stock_session.regular_session_state(utc('2026-06-15T14:00:00Z')), 'OPEN')
        self.assertEqual(stock_session.regular_session_state(utc('2026-11-09T22:00:00Z')), 'CLOSED')

    def test_thanksgiving_and_early_close_follow_exchange_calendar(self):
        self.assertEqual(stock_session.regular_session_state(utc('2026-11-26T16:00:00Z')), 'CLOSED')
        self.assertEqual(stock_session.regular_session_state(utc('2026-11-27T17:30:00Z')), 'OPEN')
        self.assertEqual(stock_session.regular_session_state(utc('2026-11-27T18:30:00Z')), 'CLOSED')

    def test_uncertain_calendar_blocks_paper(self):
        self.assertEqual(stock_session.regular_session_state(datetime(2026,11,9,15)), 'UNKNOWN')
        with patch('engine.stock_session._calendar',side_effect=RuntimeError('no calendar')):
            self.assertEqual(stock_session.regular_session_state(utc('2026-11-09T15:00:00Z')),'UNKNOWN')


if __name__=='__main__':
    unittest.main()
