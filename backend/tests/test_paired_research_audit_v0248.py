"""v0.2.48 tests for leak-resistant paired forward research and AI costs."""
from datetime import datetime, timedelta, timezone
import unittest

from engine import paired_research_audit as audit

NOW = datetime.now(timezone.utc).replace(microsecond=0)


class ForwardAuditTests(unittest.TestCase):
    def sample(self, i, **extra):
        observed = NOW - timedelta(days=45 - i)
        item = {
            "eventId": "synthetic-event-" + str(i),
            "assetClass": "prediction",
            "outcomeDefinition": "synthetic-yes-settled",
            "source": "synthetic-verified-feed",
            "observedAt": observed.isoformat(),
            "baselineIssuedAt": (observed + timedelta(seconds=10)).isoformat(),
            "assistedIssuedAt": (observed + timedelta(seconds=20)).isoformat(),
            "baselineValidationEndAt": (observed - timedelta(days=1)).isoformat(),
            "assistedValidationEndAt": (observed - timedelta(days=1)).isoformat(),
            "settledAt": (observed + timedelta(minutes=15)).isoformat(),
            "verifiedOutcome": 1,
            "outcomeVerified": True,
            "baselineProbability": "0.5",
            "assistedProbability": "0.7",
            "baselineValidationSamples": 50,
            "assistedValidationSamples": 50,
            "baselineValidationMethod": "chronological-held-out",
            "assistedValidationMethod": "chronological-held-out",
            "aiActualCostMicroUsd": 200,
            "aiCostMeasured": True,
            "independentModelValidation": True,
        }
        item.update(extra)
        return item

    def evaluate(self, records):
        return audit.evaluate_matched_forward(records, now=NOW.isoformat())

    def test_matched_forty_forward_samples_and_attributable_cost(self):
        result = self.evaluate([self.sample(i) for i in range(40)])
        self.assertEqual(result["status"], "descriptive_pairing_available")
        self.assertEqual(result["baselineMeanBrier"], "0.25")
        self.assertEqual(result["assistedMeanBrier"], "0.09")
        self.assertEqual(result["descriptiveBrierImprovement"], "0.16")
        self.assertTrue(result["assistedCalibrationImprovedDescriptively"])
        self.assertEqual(result["matchedForwardEvents"], 40)
        self.assertEqual(result["measuredAiCostMicroUsd"], 8000)
        self.assertEqual(result["measuredAiCostUsd"], "0.008")
        self.assertFalse(result["causalValueOfAiEstablished"])
        self.assertFalse(result["evidenceOfProfitableTrading"])
        self.assertFalse(result["eligibleForAutomatedTrading"])
        self.assertEqual(result["brokerRequestsMade"], 0)
        self.assertEqual(result["aiRequestsMade"], 0)

    def test_small_sample_and_degraded_assisted_model_cannot_claim_value(self):
        small = self.evaluate([self.sample(i) for i in range(5)])
        self.assertEqual(small["status"], "insufficient_forward_sample")
        self.assertFalse(small["causalValueOfAiEstablished"])
        worse = self.evaluate([self.sample(i, assistedProbability="0.1")
                               for i in range(40)])
        self.assertFalse(worse["assistedCalibrationImprovedDescriptively"])
        self.assertLess(float(worse["descriptiveBrierImprovement"]), 0)
        self.assertFalse(worse["riskAdjustedAfterTradeCostAlphaEstablished"])

    def test_no_unverified_probabilities_unknown_costs_or_future_leakage(self):
        observed = NOW - timedelta(days=1)
        bad = (
            {"aiCostMeasured": False},
            {"aiActualCostMicroUsd": -1},
            {"aiActualCostMicroUsd": 3.5},
            {"independentModelValidation": False},
            {"outcomeVerified": False},
            {"verifiedOutcome": 2},
            {"verifiedOutcome": True},
            {"baselineProbability": "1.01"},
            {"assistedProbability": "-0.01"},
            {"baselineValidationSamples": 10},
            {"assistedValidationMethod": "unverified-llm-prose"},
            {"settledAt": (NOW + timedelta(days=1)).isoformat()},
            {"assistedValidationEndAt": observed.isoformat()},
            {"assistedIssuedAt": (NOW + timedelta(days=1)).isoformat()},
            {"privateAccountId": "never-share-this"},
            {"holdings": ["PRIVATE"]},
        )
        for alterations in bad:
            with self.subTest(alterations=alterations):
                with self.assertRaises(audit.AuditUnavailable):
                    self.evaluate([self.sample(44, **alterations)])

    def test_duplicate_events_and_mixed_cohorts_are_blocked(self):
        with self.assertRaises(audit.AuditUnavailable):
            self.evaluate([self.sample(0), self.sample(0)])
        with self.assertRaises(audit.AuditUnavailable):
            self.evaluate([self.sample(0), self.sample(1, assetClass="stock")])
        with self.assertRaises(audit.AuditUnavailable):
            self.evaluate([self.sample(0), self.sample(1,
                            outcomeDefinition="different-settlement")])
        with self.assertRaises(audit.AuditUnavailable):
            self.evaluate([self.sample(0), self.sample(1,
                            source="different-provider")])

    def test_source_dates_and_probability_validation_are_strict(self):
        with self.assertRaises(audit.AuditUnavailable):
            self.evaluate([])
        with self.assertRaises(audit.AuditUnavailable):
            self.evaluate([self.sample(0, observedAt="not-a-time")])
        with self.assertRaises(audit.AuditUnavailable):
            self.evaluate([self.sample(0, baselineValidationEndAt=
                           (NOW + timedelta(days=1)).isoformat())])
        with self.assertRaises(audit.AuditUnavailable):
            self.evaluate([self.sample(0, eventId="personal information with spaces")])


if __name__ == "__main__":
    unittest.main()
