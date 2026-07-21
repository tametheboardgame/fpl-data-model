from __future__ import annotations

import unittest

from src.fpl_multiweek import optimise_multi_gameweek_route


def player(player_id: int, position: str, team_id: int, price: float = 5.0) -> dict:
    return {
        "player_id": player_id,
        "web_name": f"Player {player_id}",
        "position": position,
        "team_id": team_id,
        "team_name": f"Club {team_id}",
        "price": price,
    }


class MultiGameweekOptimiserTests(unittest.TestCase):
    def setUp(self) -> None:
        positions = (
            ["Goalkeeper"] * 2
            + ["Defender"] * 5
            + ["Midfielder"] * 5
            + ["Forward"] * 3
        )
        self.players = [
            player(index, position, ((index - 1) % 10) + 1)
            for index, position in enumerate(positions, start=1)
        ]
        self.squad = [
            {"player_id": row["player_id"], "selling_price": 50}
            for row in self.players
        ]

    def projections(self, points: float = 3.0) -> list[dict]:
        return [
            {
                "player_id": row["player_id"],
                "gameweek": gameweek,
                "expected_points": points,
            }
            for row in self.players
            for gameweek in (1, 2, 3)
        ]

    def test_delays_transfer_when_future_target_blanks_first(self) -> None:
        projections = self.projections()
        future = player(99, "Forward", 20)
        self.players.append(future)
        projections.extend(
            {"player_id": 99, "gameweek": gameweek, "expected_points": points}
            for gameweek, points in ((1, 0), (2, 10), (3, 10))
        )
        result = optimise_multi_gameweek_route(
            projections,
            self.players,
            self.squad,
            bank=0,
            free_transfers=1,
            target_gameweek=1,
            horizon=3,
        )
        self.assertEqual(result["status"], "ready")
        plan = result["recommended_route"]["gameweek_plan"]
        self.assertEqual(plan[0]["transfers"], [])
        self.assertTrue(
            any(move["buy_player_id"] == 99 for move in plan[1]["transfers"])
        )
        self.assertGreater(result["recommended_route"]["net_gain_vs_hold"], 0)

    def test_rejects_small_gain_when_it_costs_a_hit(self) -> None:
        projections = self.projections()
        marginal = player(99, "Forward", 20)
        self.players.append(marginal)
        projections.append({"player_id": 99, "gameweek": 1, "expected_points": 4.5})
        result = optimise_multi_gameweek_route(
            projections,
            self.players,
            self.squad,
            bank=0,
            free_transfers=0,
            target_gameweek=1,
            horizon=1,
        )
        self.assertEqual(
            result["recommended_route"]["gameweek_plan"][0]["transfers"], []
        )
        self.assertEqual(result["recommended_route"]["total_hit_cost"], 0)

    def test_waits_without_fixture_projections(self) -> None:
        result = optimise_multi_gameweek_route(
            [], self.players, self.squad, bank=0, free_transfers=1
        )
        self.assertEqual(result["status"], "waiting_for_projections")
        self.assertEqual(result["routes"], [])


if __name__ == "__main__":
    unittest.main()
