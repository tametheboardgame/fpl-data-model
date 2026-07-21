from __future__ import annotations

import unittest

from src.fpl_chip_optimizer import (
    fixture_counts,
    gameweek_structure,
    optimise_chip_plan,
)


def player(player_id: int, position: str, team_id: int, price: float = 5.0) -> dict:
    return {
        "player_id": player_id,
        "web_name": f"Player {player_id}",
        "position": position,
        "team_id": team_id,
        "price": price,
    }


class Phase18ChipOptimiserTests(unittest.TestCase):
    def setUp(self) -> None:
        positions = (
            ["Goalkeeper"] * 2
            + ["Defender"] * 5
            + ["Midfielder"] * 5
            + ["Forward"] * 3
        )
        self.players = [
            player(index, position, ((index - 1) % 8) + 1)
            for index, position in enumerate(positions, start=1)
        ]
        self.squad = [
            {"player_id": row["player_id"], "selling_price": 50}
            for row in self.players
        ]
        self.route = {
            "status": "ready",
            "horizon_gameweeks": [10, 11],
            "routes": [{
                "gameweek_plan": [
                    {"gameweek": 10, "transfers": [], "net_expected_points": 36},
                    {"gameweek": 11, "transfers": [], "net_expected_points": 72},
                ]
            }],
        }
        self.chips = {
            "status": "ready",
            "chips": {
                name: {"remaining": 1}
                for name in ("wildcard", "freehit", "bboost", "3xc")
            },
            "periods": [{
                "id": "first_half",
                "status": "current",
                "end_gameweek": 19,
                "chips": {
                    name: {"remaining": 1}
                    for name in ("wildcard", "freehit", "bboost", "3xc")
                },
            }],
        }

    def projections(self) -> list[dict]:
        rows = []
        for row in self.players:
            for gameweek, fixtures in ((10, 1), (11, 2)):
                for fixture in range(fixtures):
                    rows.append({
                        "player_id": row["player_id"],
                        "team_id": row["team_id"],
                        "gameweek": gameweek,
                        "fixture_id": gameweek * 100 + fixture,
                        "expected_points": 3.0,
                    })
        return rows

    def test_detects_blank_and_double_gameweeks(self) -> None:
        rows = self.projections()
        rows = [
            row for row in rows
            if not (row["gameweek"] == 10 and row["team_id"] == 8)
        ]
        counts = fixture_counts(rows, self.players, [10, 11])
        self.assertEqual(gameweek_structure(counts[10])["type"], "blank")
        self.assertEqual(gameweek_structure(counts[11])["type"], "double")

    def test_triple_captain_prefers_double_gameweek(self) -> None:
        result = optimise_chip_plan(
            self.projections(), self.players, self.squad, 25.0,
            self.chips, self.route, 10,
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["best_by_chip"]["3xc"]["gameweek"], 11)
        self.assertEqual(
            result["best_by_chip"]["3xc"]["incremental_expected_points"], 6.0
        )
        self.assertEqual(result["best_by_chip"]["3xc"]["status"], "hold")

    def test_expiry_pressure_can_make_best_double_actionable(self) -> None:
        self.chips["periods"][0]["end_gameweek"] = 11
        result = optimise_chip_plan(
            self.projections(), self.players, self.squad, 25.0,
            self.chips, self.route, 10,
        )
        self.assertEqual(result["best_by_chip"]["3xc"]["status"], "play")
        self.assertEqual(
            len({row["gameweek"] for row in result["schedule"]}),
            len(result["schedule"]),
        )
        self.assertEqual(result["recommendation"]["action"], "hold")

    def test_used_chip_is_not_considered(self) -> None:
        self.chips["periods"][0]["chips"]["freehit"]["remaining"] = 0
        result = optimise_chip_plan(
            self.projections(), self.players, self.squad, 25.0,
            self.chips, self.route, 10,
        )
        self.assertNotIn("freehit", {row["chip"] for row in result["candidates"]})

    def test_waits_without_transfer_routes(self) -> None:
        result = optimise_chip_plan(
            [], self.players, self.squad, 0, self.chips,
            {"status": "waiting_for_projections", "horizon_gameweeks": [], "routes": []},
            None,
        )
        self.assertEqual(result["status"], "waiting_for_routes")
        self.assertIsNone(result["recommendation"])


if __name__ == "__main__":
    unittest.main()
