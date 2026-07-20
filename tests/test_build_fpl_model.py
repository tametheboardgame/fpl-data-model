from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.build_fpl_model import (
    build_model,
    build_player_features,
    build_projections,
    build_team_features,
    write_prediction_snapshot,
)


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class ModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.players = [
            {
                "player_id": 10,
                "player_code": 10010,
                "web_name": "Example",
                "team_id": 1,
                "team_name": "Home FC",
                "position": "Midfielder",
                "price": 7.5,
                "status": "a",
                "chance_of_playing_next_round": "",
            }
        ]
        self.teams = [
            {"team_id": 1, "team_code": 101, "name": "Home FC"},
            {"team_id": 2, "team_code": 102, "name": "Away FC"},
        ]
        self.history = []
        for fixture in range(1, 7):
            self.history.append(
                {
                    "player_id": 10,
                    "player_code": 10010,
                    "web_name": "Example",
                    "team_id": 1,
                    "team_name": "Home FC",
                    "position": "Midfielder",
                    "fixture": fixture,
                    "round": fixture,
                    "kickoff_time": f"2026-01-{fixture:02d}T15:00:00Z",
                    "opponent_team": 2,
                    "was_home": True,
                    "team_h_score": 2,
                    "team_a_score": 1,
                    "minutes": 90,
                    "starts": 1,
                    "total_points": 6,
                    "expected_goals": 0.3,
                    "expected_assists": 0.2,
                    "expected_goal_involvements": 0.5,
                    "expected_goals_conceded": 1.0,
                    "bonus": 1,
                    "saves": 0,
                    "clean_sheets": 0,
                    "defensive_contribution": 2,
                }
            )
        self.fixtures = [
            {
                "fixture_id": 100,
                "gameweek": 7,
                "kickoff_time": "2026-02-01T15:00:00Z",
                "finished": False,
                "home_team_id": 1,
                "home_team": "Home FC",
                "away_team_id": 2,
                "away_team": "Away FC",
                "home_difficulty": 2,
                "away_difficulty": 4,
            }
        ]

    def test_builds_rolling_features_and_projection(self) -> None:
        player_features = build_player_features(self.players, self.history)
        team_features = build_team_features(self.teams, self.history)
        priors = {
            "MID": {
                "position": "MID",
                "start_rate": 0.5,
                "appearance_rate": 0.7,
                "average_minutes_per_fixture": 50,
                "points_per_90": 4,
                "xg_per_90": 0.2,
                "xa_per_90": 0.15,
                "saves_per_90": 0,
                "bonus_per_90": 0.2,
            }
        }
        projections, horizons = build_projections(
            self.players,
            player_features,
            team_features,
            self.fixtures,
            priors,
            [],
        )
        self.assertEqual(player_features[0]["fixtures_6"], 6)
        self.assertEqual(len(projections), 1)
        self.assertGreater(projections[0]["expected_minutes"], 80)
        self.assertGreater(projections[0]["expected_points"], 0)
        self.assertAlmostEqual(
            horizons[0]["expected_points_next_1"], projections[0]["expected_points"], places=3
        )

    def test_creates_immutable_predeadline_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            now = datetime.now(timezone.utc).replace(microsecond=0)
            current_gameweek = {
                "next": {
                    "id": 7,
                    "deadline_time": (now + timedelta(hours=2)).isoformat(),
                }
            }
            horizons = [
                {
                    "model_version": "baseline-1.0",
                    "player_id": 10,
                    "player_code": 10010,
                    "web_name": "Example",
                    "team_id": 1,
                    "team_name": "Home FC",
                    "position": "Midfielder",
                    "price": 7.5,
                    "expected_points_next_1": 5.2,
                    "expected_minutes_next_1": 82,
                    "value_next_1": 0.69,
                }
            ]
            first = write_prediction_snapshot(data_dir, current_gameweek, horizons, now.isoformat())
            second = write_prediction_snapshot(data_dir, current_gameweek, horizons, now.isoformat())
            self.assertIsNotNone(first["snapshot_created_this_run"])
            self.assertIsNone(second["snapshot_created_this_run"])
            self.assertEqual(len(second["prediction_snapshots"]), 1)

    def test_end_to_end_model_build(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            write_rows(data_dir / "chatgpt" / "players.csv", self.players)
            write_rows(data_dir / "chatgpt" / "teams.csv", self.teams)
            write_rows(data_dir / "chatgpt" / "fixtures.csv", self.fixtures)
            write_rows(data_dir / "chatgpt" / "player_fixtures.csv", self.history)
            write_rows(
                data_dir / "chatgpt" / "player_gameweeks.csv",
                [{"gameweek": 6, "player_id": 10, "total_points": 6}],
            )
            (data_dir / "chatgpt" / "current_gameweek.json").write_text(
                json.dumps({"current": {"id": 6}, "next": None}), encoding="utf-8"
            )
            summary = build_model(data_dir)
            self.assertEqual(summary["fixture_projection_rows"], 1)
            self.assertTrue((data_dir / "chatgpt" / "projection_summary.json").is_file())
            self.assertTrue((data_dir / "chatgpt" / "prediction_accuracy.csv").is_file())


if __name__ == "__main__":
    unittest.main()
