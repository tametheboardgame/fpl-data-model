from __future__ import annotations

import unittest

from src.sync_historical_fpl import PositionAccumulator, normalise_history_row


class HistoricalImportTests(unittest.TestCase):
    def test_normalises_history_without_lookahead_xp(self) -> None:
        row = {
            "GW": "4",
            "name": "Example Player",
            "position": "Midfielder",
            "team": "Example FC",
            "element": "10",
            "minutes": "90",
            "total_points": "8",
            "expected_goals": "0.4",
            "expected_assists": "0.2",
            "xP": "99.0",
        }
        result = normalise_history_row(row, "2024-25")
        self.assertEqual(result["gameweek"], "4")
        self.assertEqual(result["position"], "MID")
        self.assertNotIn("xP", result)

    def test_builds_position_priors(self) -> None:
        accumulator = PositionAccumulator()
        accumulator.add(
            {
                "minutes": 90,
                "starts": 1,
                "total_points": 6,
                "goals_scored": 1,
                "expected_goals": 0.5,
                "expected_assists": 0.1,
                "expected_goal_involvements": 0.6,
            }
        )
        prior = accumulator.output("ALL", "MID")
        self.assertEqual(prior["appearance_rate"], 1)
        self.assertEqual(prior["points_per_90"], 6)
        self.assertEqual(prior["xgi_per_90"], 0.6)


if __name__ == "__main__":
    unittest.main()
