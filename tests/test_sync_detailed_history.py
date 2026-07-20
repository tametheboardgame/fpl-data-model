from __future__ import annotations

import unittest

from src.sync_detailed_history import complete_fields, flatten_detail


class DetailedHistoryTests(unittest.TestCase):
    def test_flattens_fixture_and_past_season_history(self) -> None:
        player = {
            "id": 10,
            "code": 10010,
            "web_name": "Example",
            "team": 1,
            "element_type": 3,
        }
        teams = {
            1: {"id": 1, "name": "Home FC"},
            2: {"id": 2, "name": "Away FC"},
        }
        payload = {
            "history": [
                {
                    "fixture": 22,
                    "round": 3,
                    "opponent_team": 2,
                    "was_home": True,
                    "value": 75,
                    "minutes": 90,
                    "expected_goals": "0.50",
                    "total_points": 8,
                }
            ],
            "history_past": [
                {
                    "season_name": "2024/25",
                    "element_code": 10010,
                    "start_cost": 70,
                    "end_cost": 75,
                    "total_points": 150,
                }
            ],
        }

        fixtures, past = flatten_detail(player, payload, teams)
        self.assertEqual(fixtures[0]["opponent_name"], "Away FC")
        self.assertEqual(fixtures[0]["value"], 7.5)
        self.assertEqual(past[0]["start_cost"], 7.0)
        self.assertNotIn("element_code", past[0])

    def test_complete_fields_retains_new_api_fields(self) -> None:
        fields = complete_fields([{"player_id": 1, "new_stat": 2}], ["player_id"])
        self.assertEqual(fields, ["player_id", "new_stat"])


if __name__ == "__main__":
    unittest.main()
