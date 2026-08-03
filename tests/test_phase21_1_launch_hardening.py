from __future__ import annotations

import unittest

from src.build_fpl_model import build_player_features, build_projections
from src.component_player_simulator import build_component_inputs
from src.fpl_initial_squad import build_initial_squad_plan
from src.fpl_multiweek import POSITION_LIMITS


def launch_pool(points: float = 5.0) -> tuple[list[dict], list[dict], list[dict]]:
    players = []
    horizons = []
    projections = []
    player_id = 0
    prices = {
        "Goalkeeper": 4.0,
        "Defender": 4.5,
        "Midfielder": 6.0,
        "Forward": 7.0,
    }
    for team_id in range(1, 21):
        for position in POSITION_LIMITS:
            player_id += 1
            value = points + team_id / 100
            players.append(
                {
                    "player_id": player_id,
                    "player_code": 1000 + player_id,
                    "web_name": f"P{player_id}",
                    "team_id": team_id,
                    "team_name": f"Club {team_id}",
                    "position": position,
                    "price": prices[position],
                    "status": "a",
                    "selected_by_percent": 5,
                }
            )
            horizons.append(
                {
                    "player_id": player_id,
                    "player_code": 1000 + player_id,
                    "team_id": team_id,
                    "position": position,
                    "expected_points_next_1": value,
                    "probability_10_plus_next_3": 0.15,
                    "probability_15_plus_next_3": 0.05,
                }
            )
            for gameweek in (1, 2, 3):
                projections.append(
                    {
                        "player_id": player_id,
                        "team_id": team_id,
                        "position": position,
                        "gameweek": gameweek,
                        "fixture_id": gameweek * 1000 + player_id,
                        "expected_points": value,
                    }
                )
    return players, horizons, projections


class Phase211LaunchHardeningTests(unittest.TestCase):
    def test_previous_season_evidence_separates_elite_from_average_forward(self) -> None:
        players = [
            {
                "player_id": 1,
                "player_code": 101,
                "web_name": "Elite",
                "team_id": 1,
                "team_name": "Home",
                "position": "Forward",
                "price": 14.0,
                "status": "a",
            },
            {
                "player_id": 2,
                "player_code": 102,
                "web_name": "Average",
                "team_id": 1,
                "team_name": "Home",
                "position": "Forward",
                "price": 6.0,
                "status": "a",
            },
        ]
        teams = [
            {"team_id": 1, "team_code": 1, "name": "Home"},
            {"team_id": 2, "team_code": 2, "name": "Away"},
        ]
        fixtures = [
            {
                "fixture_id": 1,
                "gameweek": 1,
                "kickoff_time": "2026-08-21T19:00:00Z",
                "finished": False,
                "home_team_id": 1,
                "home_team": "Home",
                "away_team_id": 2,
                "away_team": "Away",
                "home_difficulty": 3,
                "away_difficulty": 3,
            }
        ]
        past = []
        for player, expected_goals, total_points in (
            (players[0], 30, 250),
            (players[1], 6, 100),
        ):
            past.append(
                {
                    **player,
                    "season_name": "2025/26",
                    "minutes": 3000,
                    "starts": 35,
                    "expected_goals": expected_goals,
                    "expected_assists": 4,
                    "total_points": total_points,
                    "bonus": 25,
                }
            )
        priors = {
            "FWD": {
                "start_rate": 0.43,
                "appearance_rate": 0.62,
                "average_minutes_per_fixture": 45,
                "points_per_90": 4.3,
                "xg_per_90": 0.36,
                "xa_per_90": 0.12,
                "bonus_per_90": 0.25,
            }
        }
        projections, horizons = build_projections(
            players,
            build_player_features(players, []),
            [],
            fixtures,
            priors,
            past,
            simulations=2000,
        )
        by_name = {row["web_name"]: row for row in projections}
        self.assertEqual(
            by_name["Elite"]["projection_evidence_source"],
            "previous_season",
        )
        self.assertGreater(
            by_name["Elite"]["expected_points"],
            by_name["Average"]["expected_points"] + 1,
        )
        self.assertGreater(
            by_name["Elite"]["component_probability_start"],
            0.8,
        )
        self.assertGreater(
            horizons[0]["expected_points_next_1"],
            horizons[1]["expected_points_next_1"],
        )

    def test_component_launch_minutes_retain_player_specific_start_rate(self) -> None:
        result = build_component_inputs(
            {
                "position": "FWD",
                "availability_probability": 1,
                "start_probability": 0.92,
                "appearance_probability": 0.97,
                "expected_minutes": 80,
            },
            {"fixtures_6": 0},
            {"start_rate": 0.43, "appearance_rate": 0.62},
        )
        self.assertAlmostEqual(result["start_probability"], 0.92)
        self.assertAlmostEqual(result["appearance_probability"], 0.97)
        self.assertGreater(result["expected_minutes"], 75)

    def test_compressed_launch_projections_block_ready_status(self) -> None:
        players, horizons, projections = launch_pool(points=2.0)
        result = build_initial_squad_plan(
            players,
            horizons,
            projections,
            {"next": {"id": 1, "deadline_time": "2026-08-21T17:30:00Z"}},
            "2026/27",
            "fpl-2026-27",
            min_player_pool=60,
        )
        self.assertEqual(result["status"], "review_required")
        self.assertFalse(result["readiness"]["ready"])
        codes = {
            row["code"] for row in result["launch_validation"]["issues"]
        }
        self.assertIn("compressed_projection_scale", codes)
        self.assertIn("captaincy_sanity_failed", codes)


if __name__ == "__main__":
    unittest.main()
