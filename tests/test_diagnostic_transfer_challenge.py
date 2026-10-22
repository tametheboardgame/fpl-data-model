import unittest
from src.diagnostic_transfer_challenge import audit


class DiagnosticTransferChallengeTests(unittest.TestCase):
    def setUp(self):
        self.report = {"target_gameweek": 8, "recommendation": {"transfers": [{"sell": "A", "buy": "Mbeumo"}]}}
        self.decisions = {
            "target_gameweek": 8, "team_id": 39395, "generated_at": "test",
            "transfer_shortlist": [{"buy": {"web_name": "Groß"}, "three_gameweek_gain": 11.9}],
            "multi_gameweek_plan": {"recommended_route": {"score": 5}},
        }

    def test_diagnostic_is_read_only_and_discloses_limitations(self):
        import copy
        before = copy.deepcopy((self.report, self.decisions))
        result = audit(self.report, self.decisions)
        self.assertEqual(result["candidate_shortlist"][0]["buy"]["web_name"], "Groß")
        self.assertEqual((self.report, self.decisions), before)
        self.assertIn("not_counterfactual", result["scope"])

    def test_missing_candidate_fails_closed(self):
        with self.assertRaises(ValueError):
            audit(self.report, self.decisions, candidate="Unknown")

    def test_gameweek_mismatch_fails_closed(self):
        self.report["target_gameweek"] = 9
        with self.assertRaises(ValueError):
            audit(self.report, self.decisions)


if __name__ == "__main__":
    unittest.main()
