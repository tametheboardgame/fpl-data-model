from __future__ import annotations

import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from src.backtest_fpl_model import run_backtest, walk_forward_season
from src.sync_historical_fpl import HISTORICAL_FIELDS


def synthetic_rows(season: str) -> list[dict]:
    players = [
        (1, "Alpha", "MID", "Home FC", True, 90, 0.35, 0.20),
        (2, "Bravo", "DEF", "Home FC", True, 90, 0.05, 0.08),
        (3, "Charlie", "FWD", "Away FC", False, 80, 0.45, 0.10),
        (4, "Delta", "GK", "Away FC", False, 90, 0.00, 0.00),
    ]
    rows = []
    for gameweek in range(1, 9):
        for element, name, position, team, was_home, minutes, xg, xa in players:
            goals = int(name == "Alpha" and gameweek % 3 == 0)
            assists = int(name == "Charlie" and gameweek % 4 == 0)
            points = 2 + goals * (5 if position == "MID" else 4) + assists * 3
            row = {field: "" for field in HISTORICAL_FIELDS}
            row.update(
                {
                    "season": season,
                    "gameweek": gameweek,
                    "player_name": name,
                    "position": position,
                    "team": team,
                    "element": element,
                    "fixture": gameweek,
                    "opponent_team": 2 if team == "Home FC" else 1,
                    "was_home": was_home,
                    "kickoff_time": f"2025-01-{gameweek:02d}T15:00:00Z",
                    "minutes": minutes,
                    "starts": 1,
                    "total_points": points,
                    "goals_scored": goals,
                    "assists": assists,
                    "clean_sheets": int(gameweek % 2 == 0),
                    "goals_conceded": int(gameweek % 2 == 1),
                    "saves": 3 if position == "GK" else 0,
                    "bonus": goals,
                    "expected_goals": xg,
                    "expected_assists": xa,
                    "expected_goal_involvements": xg + xa,
                    "expected_goals_conceded": 1.0,
                    "yellow_cards": 0,
                    "red_cards": 0,
                    "own_goals": 0,
                    "penalties_missed": 0,
                    "penalties_saved": 0,
                }
            )
            rows.append(row)
    return rows


class BacktestTests(unittest.TestCase):
    def test_target_results_cannot_change_pre_gameweek_prediction(self) -> None:
        rows = synthetic_rows("2024-25")
        original = walk_forward_season(rows, simulations=100)
        changed = [dict(row) for row in rows]
        for row in changed:
            if row["gameweek"] == 4 and row["player_name"] == "Alpha":
                row["total_points"] = 30
                row["goals_scored"] = 5
                row["expected_goals"] = 4.5
        repeated = walk_forward_season(changed, simulations=100)
        original_gw4 = next(
            row for row in original if row["gameweek"] == 4 and row["player_name"] == "Alpha"
        )
        repeated_gw4 = next(
            row for row in repeated if row["gameweek"] == 4 and row["player_name"] == "Alpha"
        )
        self.assertEqual(
            original_gw4["player_sim_prediction"], repeated_gw4["player_sim_prediction"]
        )
        self.assertEqual(
            original_gw4["component_sim_prediction"],
            repeated_gw4["component_sim_prediction"],
        )
        self.assertNotEqual(original_gw4["actual_points"], repeated_gw4["actual_points"])

    def test_previous_season_usage_is_used_by_control_then_fades_by_fixture_six(self) -> None:
        rows = synthetic_rows("2024-25")
        nailed_prior = []
        fringe_prior = []
        for fixture in range(1, 39):
            for player in ("Alpha", "Bravo", "Charlie", "Delta"):
                base = {
                    "player_name": player,
                    "minutes": 90,
                    "starts": 1,
                }
                nailed_prior.append(dict(base))
                fringe_prior.append(
                    {
                        **base,
                        "minutes": 90 if player != "Alpha" or fixture <= 2 else 0,
                        "starts": 1 if player != "Alpha" or fixture <= 2 else 0,
                    }
                )
        nailed = walk_forward_season(rows, nailed_prior, simulations=200)
        fringe = walk_forward_season(rows, fringe_prior, simulations=200)
        nailed_gw4 = next(
            row for row in nailed if row["gameweek"] == 4 and row["player_name"] == "Alpha"
        )
        fringe_gw4 = next(
            row for row in fringe if row["gameweek"] == 4 and row["player_name"] == "Alpha"
        )
        self.assertEqual(nailed_gw4["control_usage_prior_weight"], 0.5)
        self.assertGreater(nailed_gw4["predicted_minutes"], fringe_gw4["predicted_minutes"] + 20)
        self.assertEqual(
            nailed_gw4["component_predicted_minutes"],
            fringe_gw4["component_predicted_minutes"],
        )

        nailed_gw7 = next(
            row for row in nailed if row["gameweek"] == 7 and row["player_name"] == "Alpha"
        )
        fringe_gw7 = next(
            row for row in fringe if row["gameweek"] == 7 and row["player_name"] == "Alpha"
        )
        self.assertEqual(nailed_gw7["control_usage_prior_weight"], 0.0)
        self.assertEqual(nailed_gw7["predicted_minutes"], fringe_gw7["predicted_minutes"])

    def test_end_to_end_backtest_writes_held_out_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            path = data_dir / "history" / "historical_player_gameweeks.csv.gz"
            path.parent.mkdir(parents=True)
            rows = [
                *synthetic_rows("2022-23"),
                *synthetic_rows("2023-24"),
                *synthetic_rows("2024-25"),
            ]
            with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=HISTORICAL_FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            summary = run_backtest(data_dir, simulations=100)
            self.assertEqual(summary["held_out_season"], "2024-25")
            self.assertGreater(summary["eligible_prediction_rows"], 0)
            self.assertTrue(
                (data_dir / "backtests" / "backtest_player_predictions.csv.gz").is_file()
            )
            self.assertTrue((data_dir / "backtests" / "model_comparison.csv").is_file())
            self.assertTrue(
                (data_dir / "model" / "candidate_calibration_parameters.json").is_file()
            )
            self.assertTrue(
                (data_dir / "model" / "component_model_candidate.json").is_file()
            )
            self.assertTrue(
                (data_dir / "model" / "ensemble_model_candidate.json").is_file()
            )
            self.assertIn("held_out_component_sim_metrics", summary)
            self.assertIn("component_model_assessment", summary)
            self.assertIn("held_out_hybrid_sim_metrics", summary)
            self.assertIn("hybrid_model_assessment", summary)
            selection = summary["hybrid_model_assessment"]["selection"]
            self.assertIn(selection["selected_point_weight"], [index / 10 for index in range(11)])
            self.assertEqual(
                set(selection["selected_probability_weights"]),
                {"6", "10", "15"},
            )
            calibration = json.loads(
                (data_dir / "backtests" / "calibration_report.json").read_text()
            )
            assessment = calibration["expected_points_calibration_assessment"]
            self.assertEqual(
                calibration["expected_points_calibration_recommended"],
                assessment["recommended"],
            )
            self.assertEqual(assessment["gameweeks"], 5)
            self.assertIn("calibration_materially_improves_held_out_mae", summary["success_criteria"])


if __name__ == "__main__":
    unittest.main()
