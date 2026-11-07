from __future__ import annotations

import unittest

from src.fpl_fixture_monitor import build_fixture_schedule_monitor


class FixtureScheduleMonitorTests(unittest.TestCase):
    def test_detects_confirmed_double_blank_and_unscheduled_fixture(self) -> None:
        teams = [
            {"team_id": 1, "name": "Alpha"},
            {"team_id": 2, "name": "Bravo"},
            {"team_id": 3, "name": "Charlie"},
            {"team_id": 4, "name": "Delta"},
        ]
        fixtures = [
            {
                "fixture_id": 111,
                "gameweek": 11,
                "kickoff_time": "2026-11-21T15:00:00Z",
                "finished": False,
                "home_team_id": 1,
                "home_team": "Alpha",
                "away_team_id": 2,
                "away_team": "Bravo",
            },
            {
                "fixture_id": 112,
                "gameweek": 11,
                "kickoff_time": "2026-11-21T15:00:00Z",
                "finished": False,
                "home_team_id": 3,
                "home_team": "Charlie",
                "away_team_id": 4,
                "away_team": "Delta",
            },
            {
                "fixture_id": 121,
                "gameweek": 12,
                "kickoff_time": "2026-11-28T15:00:00Z",
                "finished": False,
                "home_team_id": 1,
                "home_team": "Alpha",
                "away_team_id": 2,
                "away_team": "Bravo",
            },
            {
                "fixture_id": 122,
                "gameweek": 12,
                "kickoff_time": "2026-12-01T19:45:00Z",
                "finished": False,
                "home_team_id": 3,
                "home_team": "Charlie",
                "away_team_id": 1,
                "away_team": "Alpha",
            },
            {
                "fixture_id": 130,
                "gameweek": None,
                "kickoff_time": None,
                "finished": False,
                "home_team_id": 4,
                "home_team": "Delta",
                "away_team_id": 2,
                "away_team": "Bravo",
            },
        ]
        current_gameweek = {
            "current": {"id": 10},
            "next": {"id": 11},
        }

        monitor = build_fixture_schedule_monitor(
            fixtures,
            teams,
            current_gameweek,
            "2026-11-07T18:00:00+00:00",
        )

        self.assertEqual(monitor["status"], "ready")
        self.assertEqual(monitor["next_double_gameweek"], 12)
        self.assertEqual(monitor["next_blank_gameweek"], 12)
        event = monitor["special_gameweeks"][0]
        self.assertEqual(event["gameweek"], 12)
        self.assertEqual(event["type"], "blank_and_double")
        self.assertEqual(event["double_team_ids"], [1])
        self.assertEqual(event["blank_team_ids"], [4])
        self.assertEqual(event["double_teams"][0]["fixture_count"], 2)
        self.assertEqual(monitor["unscheduled_fixture_count"], 1)
        self.assertEqual(monitor["unscheduled_fixtures"][0]["fixture_id"], 130)


if __name__ == "__main__":
    unittest.main()
