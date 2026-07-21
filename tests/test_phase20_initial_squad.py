from __future__ import annotations

import unittest

from src.fpl_initial_squad import BUDGET, POSITION_LIMITS, build_initial_squad_plan


def launch_data() -> tuple[list[dict], list[dict], list[dict]]:
    players: list[dict] = []
    horizons: list[dict] = []
    projections: list[dict] = []
    player_id = 0
    position_prices = {
        "Goalkeeper": 4.0,
        "Defender": 4.5,
        "Midfielder": 6.0,
        "Forward": 6.5,
    }
    for team_id in range(1, 21):
        for position in POSITION_LIMITS:
            player_id += 1
            price = position_prices[position] + (team_id % 4) * 0.1
            points = 2.0 + team_id / 10 + list(POSITION_LIMITS).index(position) / 5
            players.append(
                {
                    "player_id": player_id,
                    "web_name": f"P{player_id}",
                    "team_id": team_id,
                    "team_name": f"Club {team_id}",
                    "position": position,
                    "price": price,
                    "status": "a",
                    "selected_by_percent": (team_id * 3) % 45,
                }
            )
            horizons.append(
                {
                    "player_id": player_id,
                    "probability_10_plus_next_3": min(0.5, points / 20),
                    "probability_15_plus_next_3": min(0.2, points / 50),
                }
            )
            for gameweek in (1, 2, 3):
                projections.append(
                    {
                        "player_id": player_id,
                        "team_id": team_id,
                        "gameweek": gameweek,
                        "fixture_id": gameweek * 1000 + player_id,
                        "expected_points": points + gameweek / 10,
                    }
                )
    return players, horizons, projections


class Phase20InitialSquadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.players, self.horizons, self.projections = launch_data()
        self.gameweek = {
            "next": {"id": 1, "deadline_time": "2026-08-14T17:30:00Z"}
        }

    def test_old_season_never_emits_a_squad(self) -> None:
        result = build_initial_squad_plan(
            self.players,
            self.horizons,
            self.projections,
            self.gameweek,
            "2025/26",
            "fpl-2025-26",
            min_player_pool=60,
        )
        self.assertEqual(result["status"], "waiting_for_launch_data")
        self.assertEqual(result["recommended_squad"], [])
        self.assertEqual(result["strategy_comparison"], [])
        self.assertIn("official_season", result["readiness"]["missing"])

    def test_builds_three_legal_launch_strategies(self) -> None:
        result = build_initial_squad_plan(
            self.players,
            self.horizons,
            self.projections,
            self.gameweek,
            "2026/27",
            "fpl-2026-27",
            min_player_pool=60,
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["recommended_strategy"], "balanced")
        self.assertEqual(len(result["recommended_squad"]), 15)
        self.assertEqual(len(result["recommended_starting_xi"]), 11)
        self.assertEqual(len(result["recommended_bench_order"]), 4)
        self.assertIsNotNone(result["captain"])
        self.assertIsNotNone(result["vice_captain"])
        self.assertEqual(
            {row["strategy"] for row in result["strategy_comparison"]},
            {"balanced", "aggressive", "ownership_protected"},
        )
        for variant in result["strategy_comparison"]:
            self.assertTrue(variant["validation"]["legal_squad"])
            self.assertTrue(variant["validation"]["within_budget"])
            self.assertLessEqual(variant["total_cost"], BUDGET)
            self.assertEqual(variant["validation"]["position_counts"], POSITION_LIMITS)
            self.assertLessEqual(variant["validation"]["maximum_from_one_club"], 3)
        self.assertEqual(result["planned_transfer_route"]["status"], "ready")

    def test_missing_prices_and_fixtures_stays_empty(self) -> None:
        players = [{**row, "price": None} for row in self.players]
        result = build_initial_squad_plan(
            players,
            self.horizons,
            [],
            self.gameweek,
            "2026/27",
            "fpl-2026-27",
            min_player_pool=60,
        )
        self.assertEqual(result["status"], "waiting_for_launch_data")
        self.assertEqual(result["recommended_squad"], [])
        self.assertIn("complete_player_pool", result["readiness"]["missing"])
        self.assertIn("future_fixture_horizon", result["readiness"]["missing"])

    def test_does_not_recommend_an_initial_squad_after_gameweek_one(self) -> None:
        result = build_initial_squad_plan(
            self.players,
            self.horizons,
            self.projections,
            {"next": {"id": 2, "deadline_time": "2026-08-21T17:30:00Z"}},
            "2026/27",
            "fpl-2026-27",
            min_player_pool=60,
        )
        self.assertEqual(result["status"], "not_applicable_after_gameweek_1")
        self.assertEqual(result["recommended_squad"], [])


if __name__ == "__main__":
    unittest.main()
