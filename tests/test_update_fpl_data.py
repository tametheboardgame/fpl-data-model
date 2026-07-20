from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.update_fpl_data import build_datasets, current_and_next_event, infer_season


class TransformTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bootstrap = {
            "total_players": 1000,
            "events": [
                {
                    "id": 1,
                    "name": "Gameweek 1",
                    "deadline_time": "2025-08-15T17:30:00Z",
                    "finished": True,
                    "is_current": True,
                    "is_next": False,
                },
                {
                    "id": 2,
                    "name": "Gameweek 2",
                    "deadline_time": "2026-05-24T14:00:00Z",
                    "finished": False,
                    "is_current": False,
                    "is_next": True,
                },
            ],
            "teams": [
                {"id": 1, "name": "Home FC", "short_name": "HOM", "strength": 3},
                {"id": 2, "name": "Away FC", "short_name": "AWY", "strength": 4},
            ],
            "elements": [
                {
                    "id": 10,
                    "web_name": "Example",
                    "first_name": "Test",
                    "second_name": "Player",
                    "team": 1,
                    "element_type": 3,
                    "now_cost": 75,
                    "status": "a",
                    "total_points": 12,
                    "event_points": 7,
                    "form": "6.0",
                    "transfers_in_event": 100,
                }
            ],
        }
        self.fixtures = [
            {
                "id": 1,
                "event": 1,
                "team_h": 1,
                "team_a": 2,
                "team_h_score": 2,
                "team_a_score": 1,
                "team_h_difficulty": 2,
                "team_a_difficulty": 4,
                "kickoff_time": "2025-08-15T19:00:00Z",
                "started": True,
                "finished": True,
            }
        ]
        self.live = {1: {"elements": [{"id": 10, "stats": {"minutes": 90, "total_points": 7}}]}}
        self.profile = {
            "name": "Test XI",
            "player_first_name": "David",
            "player_last_name": "Test",
            "summary_overall_points": 7,
            "summary_overall_rank": 500,
            "summary_event_points": 7,
        }
        self.history = {"current": [{"event": 1, "points": 7, "total_points": 7}]}
        self.picks = {
            "active_chip": None,
            "entry_history": {"event": 1, "points": 7, "bank": 5, "value": 1000},
            "picks": [
                {
                    "element": 10,
                    "position": 1,
                    "multiplier": 2,
                    "is_captain": True,
                    "is_vice_captain": False,
                    "purchase_price": 75,
                    "selling_price": 75,
                }
            ],
        }

    def test_event_and_season_helpers(self) -> None:
        current, following = current_and_next_event(self.bootstrap["events"])
        self.assertEqual(current["id"], 1)
        self.assertEqual(following["id"], 2)
        self.assertEqual(infer_season(self.bootstrap["events"]), "2025/26")

    def test_builds_chatgpt_datasets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            manifest = build_datasets(
                output,
                6435140,
                self.bootstrap,
                self.fixtures,
                self.live,
                self.profile,
                self.history,
                self.picks,
            )
            self.assertEqual(manifest["team_id"], 6435140)
            self.assertEqual(manifest["row_counts"]["players"], 1)

            my_team = json.loads((output / "chatgpt" / "my_team.json").read_text())
            self.assertEqual(my_team["team_name"], "Test XI")
            self.assertEqual(my_team["squad"][0]["web_name"], "Example")

            with (output / "chatgpt" / "players.csv").open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["price"], "7.5")
            self.assertEqual(rows[0]["team_name"], "Home FC")

    def test_unavailable_team_is_non_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            build_datasets(
                output,
                6435140,
                self.bootstrap,
                self.fixtures,
                {},
                None,
                None,
                None,
            )
            my_team = json.loads((output / "chatgpt" / "my_team.json").read_text())
            self.assertFalse(my_team["available"])


if __name__ == "__main__":
    unittest.main()
