"""Manual history uses synthetic provider replies and real tenant authorization."""
from decimal import Decimal
import json
import sqlite3
import unittest
from unittest.mock import patch

import test_owner_market_quotes_v0290 as quote_tests


class SyntheticBarsReply:
    status_code = 200

    def __init__(self, payload):
        self.content = payload.encode()

    def iter_content(self, *, chunk_size):
        yield self.content

    def close(self):
        pass


class OwnerMarketHistoryTests(unittest.TestCase):
    setUp = quote_tests.SyntheticOwnerQuotesTests.setUp
    tearDown = quote_tests.SyntheticOwnerQuotesTests.tearDown

    def history(self, *, symbol="SPY", instrument="EQUITY", period="WEEK", account=None):
        return self.quotes.history(
            self.a["token"], account or self.account_a, symbol=symbol,
            instrument_type=instrument, period=period)

    def provider(self, payload, *, during=None, status=200):
        original_get = self.fake.get
        self.history_calls = []

        def get(url, *, headers, timeout, **options):
            if "/historicdata/" not in url:
                return original_get(url, headers=headers, timeout=timeout)
            self.history_calls.append((url, headers, options))
            if during:
                during()
            result = SyntheticBarsReply(payload)
            result.status_code = status
            return result

        self.fake.get = get

    def payload(self, *, symbol="SPY", period="WEEK", volume="1700"):
        return (f'{{"symbol":"{symbol}","period":"{period}","regularMarket":{{"bars":['
                '{"timestamp":"2026-11-12T18:00:00Z","open":"9.000","high":"9.250",'
                f'"low":"8.999","close":"9.125","volume":{volume}' + '}]}}')

    def test_etf_and_crypto_history_have_exact_source_values_and_scope(self):
        self.provider(self.payload())
        observed = self.history()
        self.assertEqual(observed["accountId"], self.account_a)
        self.assertEqual(observed["provider"], "Public API")
        self.assertEqual(observed["bars"][0]["open"], "9.000")
        self.assertFalse(observed["dataPersisted"])
        self.assertFalse(observed["paperFillEligible"])
        url, headers, options = self.history_calls[0]
        self.assertTrue(url.endswith("/EQUITY/SPY/WEEK?tradingSessionToggle=REGULAR_HOURS"))
        self.assertEqual(headers["Authorization"], "Bearer " + quote_tests.TOKENS[quote_tests.KEY_OWNER])
        self.assertEqual(options, {"allow_redirects": False, "stream": True})
        with self.assertRaises(quote_tests.market.OwnerQuoteUnavailable):
            self.history(account=self.account_b)

    def test_crypto_volume_preserves_decimal_precision(self):
        self.provider(self.payload(symbol="BTC", period="MONTH", volume="1.000000000000000001"))
        observed = self.history(symbol="BTC", instrument="CRYPTO", period="MONTH")
        self.assertEqual(observed["bars"][0]["volume"], "1.000000000000000001")
        self.assertTrue(self.history_calls[0][0].endswith("/CRYPTO/BTC/MONTH"))

    def test_failure_and_mismatched_instrument_refuse(self):
        for payload, status in ((self.payload(), 302), (self.payload(symbol="MSFT"), 200),
                                ("{}", 200), ("not json", 200)):
            self.provider(payload, status=status)
            with self.assertRaises(quote_tests.market.OwnerQuoteUnavailable):
                self.history()

    def test_revocation_during_provider_history_discards_payload(self):
        def revoke():
            with sqlite3.connect(self.path) as db:
                db.execute("UPDATE tenant_connections SET revoked_at=1 WHERE connection_id=?",
                           (self.connection_a,))

        self.provider(self.payload(), during=revoke)
        with self.assertRaises(quote_tests.market.OwnerQuoteUnavailable):
            self.history()

    def test_chart_lead_in_is_excluded_and_malformed_range_refused(self):
        payload = json.loads(self.payload(), parse_float=Decimal)
        row = payload["regularMarket"]["bars"][0]
        payload["regularMarket"]["bars"].append(dict(row, timestamp="2026-11-12T19:00:00Z"))
        payload["leadingFill"] = {
            "startTimestamp": "2026-11-12T17:00:00Z",
            "endTimestamp": "2026-11-12T18:00:00Z",
        }
        self.provider(json.dumps(payload))
        self.assertEqual(self.history()["barCount"], 1)
        payload["leadingFill"]["endTimestamp"] = "2026-11-12T16:00:00Z"
        self.provider(json.dumps(payload))
        with self.assertRaises(quote_tests.market.OwnerQuoteUnavailable):
            self.history()


    def test_oversized_stream_is_refused(self):
        self.provider(self.payload())
        with patch.object(quote_tests.market, "_MAX_HISTORY_BYTES", 12):
            with self.assertRaises(quote_tests.market.OwnerQuoteUnavailable):
                self.history()

    def test_public_expected_bars_are_reported_without_inventing_rows(self):
        payload = json.loads(self.payload())
        payload["regularMarket"]["expectedBars"] = 9
        payload["totalExpectedBars"] = 20
        self.provider(json.dumps(payload))
        observed = self.history()
        self.assertEqual(observed["sourceExpectedBars"], 9)
        self.assertEqual(observed["barCount"], 1)
        self.assertEqual(len(observed["bars"]), 1)
        for invalid in (True, -1, "9"):
            payload["regularMarket"]["expectedBars"] = invalid
            self.provider(json.dumps(payload))
            with self.assertRaises(quote_tests.market.OwnerQuoteUnavailable):
                self.history()
        del payload["regularMarket"]["expectedBars"]
        self.provider(json.dumps(payload))
        self.assertIsNone(self.history()["sourceExpectedBars"])

    def test_weekly_equity_history_excludes_other_provider_series(self):
        payload = json.loads(self.payload())
        row = payload["regularMarket"]["bars"][0]
        for series in ("preMarket", "afterMarket", "preMarketOvernight", "postMarketOvernight"):
            payload[series] = {"expectedBars": 1, "bars": [dict(row, volume=500)]}
        self.provider(json.dumps(payload))
        observed = self.history()
        self.assertEqual(observed["source"], "Get bars v2")
        self.assertEqual([bar["volume"] for bar in observed["bars"]], ["1700"])
        self.assertIsNone(observed["sourceExpectedBars"])
        self.assertFalse(observed["dataPersisted"])

    def test_unsupported_history_period_never_requests_provider_bars(self):
        self.provider(self.payload())
        with self.assertRaises(quote_tests.market.OwnerQuoteUnavailable):
            self.history(period="SINCE_PURCHASE")
        self.assertEqual(self.history_calls, [])

    def test_history_is_discarded_when_owner_session_ends_during_request(self):
        self.provider(self.payload(), during=lambda: self.identities.revoke(self.a["token"]))
        with self.assertRaises(quote_tests.market.OwnerQuoteUnavailable):
            self.history()
        self.assertEqual(len(self.history_calls), 1)

    def test_history_is_discarded_when_selected_account_is_disabled_during_request(self):
        def disable():
            with sqlite3.connect(self.path) as db:
                db.execute("UPDATE tenant_accounts SET disabled_at=1 WHERE account_id=?",
                           (self.account_a,))

        self.provider(self.payload(), during=disable)
        with self.assertRaises(quote_tests.market.OwnerQuoteUnavailable):
            self.history()
        self.assertEqual(len(self.history_calls), 1)

    def test_history_is_discarded_when_connection_ciphertext_changes(self):
        def replace():
            with sqlite3.connect(self.path) as db:
                db.execute("UPDATE tenant_connections SET credential_ciphertext=? WHERE connection_id=?",
                           (b"replacement-synthetic-ciphertext", self.connection_a))

        self.provider(self.payload(), during=replace)
        with self.assertRaises(quote_tests.market.OwnerQuoteUnavailable):
            self.history()
        self.assertEqual(len(self.history_calls), 1)
