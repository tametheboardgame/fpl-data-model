from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.backtest_fpl_model import walk_forward_season
from src.build_fpl_model import (
    FALLBACK_PRIORS,
    build_player_features,
    build_projections,
    load_ensemble_config,
)
from src.component_player_simulator import COMPONENT_MODEL_VERSION, build_component_inputs


class ComponentEarlySeasonPriorTests(unittest.TestCase):
    def test_component_uses_player_specific_usage_prior_after_two_starts(self) -> None:
        feature = {
            "fixtures_6": 2,
            "start_rate_6": 1.0,
            "appearance_rate_6": 1.0,
            "starter_average_minutes_6": 90,
            "substitute_average_minutes_6": 0,
            "minutes_6": 180,
            "minutes_10": 180,
            "xg_per_90_6": 0.7,
            "xg_per_90_10": 0.7,
            "xa_per_90_6": 0.1,
            "xa_per_90_10": 0.1,
        }
        base = {
            "position": "FWD",
            "availability_probability": 1.0,
            "start_probability": 1.0,
            "appearance_probability": 1.0,
            "expected_minutes": 90,
        }
        prior = {"start_rate": 0.43, "appearance_rate": 0.62}
        nailed = build_component_inputs(
            {
                **base,
                "player_start_rate_prior": 0.92,
                "player_appearance_rate_prior": 0.97,
            },
            feature,
            prior,
        )
        fringe = build_component_inputs(
            {
                **base,
                "player_start_rate_prior": 0.10,
                "player_appearance_rate_prior": 0.20,
            },
            feature,
            prior,
        )
        self.assertGreater(nailed["start_probability"], 0.9)
        self.assertLess(fringe["start_probability"], 0.6)
        self.assertGreater(nailed["expected_minutes"], fringe["expected_minutes"] + 25)

    def test_live_projection_wires_previous_season_usage_into_component(self) -> None:
        players = [
            {
                "player_id": 1,
                "player_code": 101,
                "web_name": "Nailed",
                "team_id": 1,
                "team_name": "Home",
                "position": "Forward",
                "price": 10.0,
                "status": "a",
            },
            {
                "player_id": 2,
                "player_code": 102,
                "web_name": "Fringe",
                "team_id": 1,
                "team_name": "Home",
                "position": "Forward",
                "price": 6.0,
                "status": "a",
            },
        ]
        history = []
        for player in players:
            for fixture in (1, 2):
                history.append(
                    {
                        "player_id": player["player_id"],
                        "fixture": fixture,
                        "kickoff_time": f"2026-08-{20 + fixture:02d}T15:00:00Z",
                        "minutes": 90,
                        "starts": 1,
                        "total_points": 6,
                        "expected_goals": 0.6,
                        "expected_assists": 0.1,
                        "expected_goal_involvements": 0.7,
                        "bonus": 1,
                    }
                )
        past = [
            {
                **players[0],
                "season_name": "2025/26",
                "minutes": 3000,
                "starts": 35,
                "expected_goals": 22,
                "expected_assists": 4,
                "total_points": 200,
                "bonus": 25,
            },
            {
                **players[1],
                "season_name": "2025/26",
                "minutes": 300,
                "starts": 2,
                "expected_goals": 2,
                "expected_assists": 1,
                "total_points": 25,
                "bonus": 2,
            },
        ]
        fixtures = [
            {
                "fixture_id": 3,
                "gameweek": 3,
                "kickoff_time": "2026-09-04T19:00:00Z",
                "finished": False,
                "home_team_id": 1,
                "home_team": "Home",
                "away_team_id": 2,
                "away_team": "Away",
                "home_difficulty": 3,
                "away_difficulty": 3,
            }
        ]
        projections, _ = build_projections(
            players,
            build_player_features(players, history),
            [],
            fixtures,
            {"FWD": dict(FALLBACK_PRIORS["FWD"])},
            past,
            simulations=1200,
        )
        by_id = {row["player_id"]: row for row in projections}
        nailed = by_id[1]
        fringe = by_id[2]
        self.assertAlmostEqual(nailed["component_start_rate_prior"], 35 / 38, places=3)
        self.assertAlmostEqual(fringe["component_start_rate_prior"], 2 / 38, places=3)
        self.assertGreater(nailed["component_expected_minutes"], 75)
        self.assertLess(fringe["component_expected_minutes"], 60)
        self.assertGreater(
            nailed["component_expected_minutes"],
            fringe["component_expected_minutes"] + 25,
        )

    def test_stale_ensemble_weights_are_disabled_after_component_version_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ensemble.json"
            candidate = {
                "status": "recommended_for_live_promotion",
                "assessment": {
                    "component_model_version": "player-sim-older",
                    "selection": {
                        "selected_point_weight": 0.2,
                        "selected_probability_weights": {"6": 0.5, "10": 0.4, "15": 1.0},
                    },
                },
            }
            path.write_text(json.dumps(candidate), encoding="utf-8")
            stale = load_ensemble_config(path)
            self.assertFalse(stale["enabled"])
            self.assertEqual(stale["status"], "candidate_component_version_mismatch")

            candidate["assessment"]["component_model_version"] = COMPONENT_MODEL_VERSION
            path.write_text(json.dumps(candidate), encoding="utf-8")
            current = load_ensemble_config(path)
            self.assertTrue(current["enabled"])
            self.assertEqual(current["point_weight"], 0.2)

    def test_backtest_uses_previous_season_usage_without_changing_control_arm(self) -> None:
        target = []
        for gameweek in range(1, 9):
            target.append(
                {
                    "season": "2024-25",
                    "gameweek": gameweek,
                    "player_name": "Target",
                    "position": "FWD",
                    "team": "Home FC",
                    "element": 1,
                    "fixture": gameweek,
                    "was_home": True,
                    "kickoff_time": f"2025-01-{gameweek:02d}T15:00:00Z",
                    "minutes": 90,
                    "starts": 1,
                    "total_points": 5,
                    "goals_scored": 0,
                    "assists": 0,
                    "clean_sheets": 0,
                    "goals_conceded": 1,
                    "expected_goals": 0.5,
                    "expected_assists": 0.1,
                    "expected_goal_involvements": 0.6,
                    "expected_goals_conceded": 1.0,
                    "saves": 0,
                    "bonus": 0,
                    "yellow_cards": 0,
                    "red_cards": 0,
                    "own_goals": 0,
                    "penalties_missed": 0,
                    "penalties_saved": 0,
                }
            )
        nailed_prior = [
            {
                "player_name": "Target",
                "minutes": 90 if fixture <= 35 else 0,
                "starts": 1 if fixture <= 35 else 0,
            }
            for fixture in range(1, 39)
        ]
        fringe_prior = [
            {
                "player_name": "Target",
                "minutes": 90 if fixture <= 2 else 0,
                "starts": 1 if fixture <= 2 else 0,
            }
            for fixture in range(1, 39)
        ]
        nailed = walk_forward_season(target, nailed_prior, simulations=600)
        fringe = walk_forward_season(target, fringe_prior, simulations=600)
        nailed_gw4 = next(row for row in nailed if row["gameweek"] == 4)
        fringe_gw4 = next(row for row in fringe if row["gameweek"] == 4)
        self.assertEqual(
            nailed_gw4["player_sim_prediction"],
            fringe_gw4["player_sim_prediction"],
        )
        self.assertGreater(
            nailed_gw4["component_predicted_minutes"],
            fringe_gw4["component_predicted_minutes"] + 20,
        )


if __name__ == "__main__":
    unittest.main()
