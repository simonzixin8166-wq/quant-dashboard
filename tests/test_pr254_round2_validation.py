#!/usr/bin/env python3
"""Round 2 PR validation tests for PR #254."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

class TestPR254Round2Contracts(unittest.TestCase):

    def test_learning_evaluation_three_tier_isolation(self):
        from scripts.learning_evaluation_engine import build, load, PATHS
        data = build(
            load(PATHS["execution"]),
            load(PATHS["planner"]),
            load(PATHS["learning"]),
            load(PATHS["method"]),
            load(PATHS["evidence"]),
            load(PATHS["history"]),
            load(PATHS["self_improvement"]),
            load(PATHS["auto_thesis"]),
            load(PATHS["event_window"]),
            load(PATHS["server_action"]),
            load(PATHS["forward_feedback"]),
            load(PATHS["fundamental_outcomes"]),
        )
        three_tier = data.get("three_tier_metrics_isolation", {})
        genuine = three_tier.get("genuine_learning_outcomes", {})

        # historical_mature_60 must NOT be inside genuine_learning_outcomes
        self.assertNotIn("historical_mature_60", genuine)

        # historical_mature_60 must be in historical_reconstruction
        hist = three_tier.get("historical_reconstruction", {})
        self.assertIn("historical_mature_60", hist)

        # forward_status must be UNPROVEN when forward mature count is 0
        if genuine.get("forward_mature_20", 0) == 0 and genuine.get("forward_mature_60", 0) == 0:
            self.assertEqual(genuine.get("forward_status"), "UNPROVEN")

    def test_source_validation_explanation_no_hardcoding(self):
        from scripts.source_outcome_validation import build, load, SOURCE
        source = load(SOURCE, {"operation_cases": []})
        data = build(source, {})
        explanation = data.get("explanation", {})

        # Must not contain balanced_reconciliation or hardcoded "100%" string in explanation keys or values
        for key, val in explanation.items():
            self.assertNotIn("100%", str(val))
            self.assertNotIn("1918/1918", str(val))
            self.assertNotEqual(key, "balanced_reconciliation")


if __name__ == "__main__":
    unittest.main()
