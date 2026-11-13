"""v0.2.92 historical provenance parser: strict synthetic data, no HTTP."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import unittest

from engine import owner_historical_bars as history

RECEIVED = datetime(2026, 11, 12, 23, 30, tzinfo=timezone.utc)


def sample():
    return {
        "symbol": "AAPL", "period": "DAY",
        "regularMarket": {"bars": [
            {"timestamp":"2026-11-12T20:00:00Z",
             "open":"100.05","high":"101.01","low":"99.99",
             "close":"100.50","volume":100},
            {"timestamp":"2026-11-12T21:00:00+00:00",
             "open":"100.50","high":"101.50","low":"100.11",
             "close":"101.12","volume":"101"},
        ]},
        "leadingFill": {"value":"1234.00", "count":10,
                        "startTimestamp":"2026-11-12T18:00:00Z",
                        "endTimestamp":"2026-11-12T19:59:59Z"},
    }


def normalize(payload=None, **overrides):
    args = {"symbol":"AAPL", "instrument_type":"EQUITY",
            "period":"DAY", "received_at":RECEIVED}
    args.update(overrides)
    return history.normalize_bars(sample() if payload is None else payload, **args)


class HistoricalProvenanceTests(unittest.TestCase):
    def test_exact_source_strings_no_fabricated_prices_or_returns(self):
        result = normalize()
        self.assertEqual(result["barCount"], 2)
        self.assertEqual(result["bars"][0]["open"], "100.05")
        self.assertEqual(result["bars"][1]["close"], "101.12")
        self.assertEqual(result["bars"][1]["volume"], "101")
        self.assertNotIn("changePct", result)
        self.assertNotIn("profitLoss", result)
        self.assertNotIn("leadingFill", result)
        for flag in ("providerRequestAuthenticated","accountScopeVerified",
                     "dataRightsVerified","cacheRightsVerified",
                     "redistributionAllowed","paperFillEligible",
                     "productionEligible","performanceVerified",
                     "dataPersisted","calendarCompletenessVerified"):
            self.assertIs(result[flag], False)
        self.assertIs(result["leadingFillExcluded"], True)
        self.assertEqual(result["providerLabel"],
                         "Public API (unverified source payload)")

    def test_normalizes_real_timezone_offsets_only(self):
        data = sample()
        data["regularMarket"]["bars"][0]["timestamp"] = "2026-11-12T15:00:00-05:00"
        self.assertEqual(normalize(data)["bars"][0]["timestamp"],
                         "2026-11-12T20:00:00+00:00")

    def test_bad_source_label_and_scope(self):
        for key,value in (("symbol","MSFT"),("period","WEEK"),("symbol",None)):
            with self.subTest(key=key,value=value):
                data=sample();data[key]=value
                with self.assertRaises(history.HistoryUnavailable):
                    normalize(data)
        for kwargs in ({"instrument_type":"PREDICTION"},
                       {"period":"INVALID"}, {"symbol":"../SECRET"},
                       {"instrument_type":[]}, {"period":[]}):
            with self.subTest(args=kwargs):
                with self.assertRaises(history.HistoryUnavailable):
                    normalize(**kwargs)
        with self.assertRaises(history.HistoryUnavailable):
            normalize(received_at=datetime.now())

    def test_invalid_bars_fail_closed(self):
        def case(change):
            data=sample();change(data)
            with self.assertRaises(history.HistoryUnavailable):
                normalize(data)
        case(lambda d: d.update(regularMarket={"bars":[]}))
        case(lambda d: d.update(regularMarket={"bars":[1]}))
        case(lambda d: d["regularMarket"]["bars"][1].update(
            timestamp=d["regularMarket"]["bars"][0]["timestamp"]))
        case(lambda d: d["regularMarket"]["bars"][1].update(
            timestamp="2026-11-12T19:00:00Z"))
        case(lambda d: d["regularMarket"]["bars"][0].update(
            timestamp="2026-11-13T00:00:00Z"))
        case(lambda d: d["regularMarket"]["bars"][0].update(
            timestamp="2026-11-12T20:00:00"))
        for value in (None, -2, "NaN", "inf", "0", "1e2",
                      "01.2", 12.34, "100.1234567890123"):
            case(lambda d,v=value:d["regularMarket"]["bars"][0].update(open=v))
        case(lambda d:d["regularMarket"]["bars"][0].update(high="100.00"))
        case(lambda d:d["regularMarket"]["bars"][0].update(low="100.90"))
        for volume in (-1, True, 1.2, "1.5", "-2", "1e2", None):
            case(lambda d,v=volume:d["regularMarket"]["bars"][0].update(volume=v))

    def test_rejects_oversized_source_and_future_receipt(self):
        data=sample()
        data["regularMarket"]["bars"] *= 3000
        with self.assertRaises(history.HistoryUnavailable):
            normalize(data)
        with self.assertRaises(history.HistoryUnavailable):
            normalize(received_at=RECEIVED-timedelta(days=2))


if __name__ == "__main__":
    unittest.main()
