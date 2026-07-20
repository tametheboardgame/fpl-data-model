from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.build_fpl_model import (
    PROJECTION_FIELDS,
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
        self.assertIn("probability_15_plus", PROJECTION_FIELDS)
        self.assertIn("quantitative_expected_points", PROJECTION_FIELDS)
        self.assertIn("component_expected_points", PROJECTION_FIELDS)
        self.assertIn("component_probability_15_plus", PROJECTION_FIELDS)
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
        self.assertGreater(projections[0]["component_expected_points"], 0)
        self.assertGreater(projections[0]["component_probability_60_plus"], 0)
        component_sum = sum(
            projections[0][field]
            for field in (
                "component_appearance_points",
                "component_goal_points",
                "component_assist_points",
                "component_clean_sheet_points",
                "component_goals_conceded_points",
                "component_save_points",
                "component_penalty_save_points",
                "component_defensive_contribution_points",
                "component_bonus_points",
                "component_discipline_points",
            )
        )
        self.assertAlmostEqual(
            component_sum, projections[0]["component_expected_points"], delta=0.01
        )
        self.assertAlmostEqual(
            horizons[0]["expected_points_next_1"], projections[0]["expected_points"], places=3
        )
        self.assertGreater(horizons[0]["component_expected_points_next_1"], 0)

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

    def test_qualitative_overlay_is_separate_and_auditable(self) -> None:
        player_features = build_player_features(self.players, self.history)
        team_features = build_team_features(self.teams, self.history, self.fixtures)
        observation = {
            "observation_id": "obs-example",
            "observed_at": "2026-01-25T17:00:00+00:00",
            "recorded_at": "2026-01-25T18:00:00+00:00",
            "observer": "David",
            "player_id": 10,
            "raw_note": "Playing higher, moving sharply and expected to start.",
            "attacking_role": 2,
            "movement_sharpness": 2,
            "fitness_energy": 1,
            "minutes_security": 1,
            "set_piece_role": 0,
            "team_reliance": 1,
            "tactical_fit": 1,
            "confidence": 1,
            "expires_at": "2026-02-10T00:00:00+00:00",
            "status": "active",
        }
        projections, _ = build_projections(
            self.players,
            player_features,
            team_features,
            self.fixtures,
            {},
            [],
            [observation],
            simulations=1000,
        )
        projection = projections[0]
        self.assertEqual(projection["qualitative_observation_count"], 1)
        self.assertEqual(projection["qualitative_observation_ids"], "obs-example")
        self.assertGreater(projection["qualitative_attack_multiplier"], 1)
        self.assertGreater(projection["qualitative_minutes_delta"], 0)
        self.assertGreater(projection["expected_points"], projection["quantitative_expected_points"])

    def test_team_features_use_fixture_club_after_transfer(self) -> None:
        history = [{**self.history[0], "fixture": 100, "team_id": 2}]
        features = build_team_features(self.teams, history, self.fixtures)
        by_team = {row["team_id"]: row for row in features}
        self.assertEqual(by_team[1]["matches_3"], 1)
        self.assertEqual(by_team[2]["matches_3"], 0)

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
            (data_dir / "chatgpt" / "manifest.json").write_text(
                json.dumps({"datasets": [{"path": "data/chatgpt/players.csv"}]}),
                encoding="utf-8",
            )
            (data_dir / "model").mkdir(parents=True)
            (data_dir / "model" / "component_model_candidate.json").write_text(
                json.dumps({"status": "candidate_not_applied_to_live_model"}),
                encoding="utf-8",
            )
            summary = build_model(data_dir)
            self.assertEqual(summary["fixture_projection_rows"], 1)
            self.assertEqual(
                summary["challenger_status"],
                "candidate_not_applied_to_live_model",
            )
            self.assertTrue((data_dir / "chatgpt" / "projection_summary.json").is_file())
            self.assertTrue((data_dir / "chatgpt" / "prediction_accuracy.csv").is_file())
            self.assertTrue((data_dir / "chatgpt" / "scouting_observations.csv").is_file())
            with (data_dir / "chatgpt" / "player_projections.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                projection_rows = list(csv.DictReader(handle))
            self.assertIn("probability_15_plus", projection_rows[0])
            self.assertIn("quantitative_expected_points", projection_rows[0])
            self.assertIn("component_expected_points", projection_rows[0])
            self.assertIn("component_appearance_points", projection_rows[0])
            manifest = json.loads(
                (data_dir / "chatgpt" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertIn(
                {"path": "data/chatgpt/projection_summary.json"}, manifest["datasets"]
            )


if __name__ == "__main__":
    unittest.main()
