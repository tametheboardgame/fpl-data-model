from __future__ import annotations

import unittest
from unittest.mock import patch

from src.fpl_chip_optimizer import optimise_chip_plan
from src.fpl_decisions import build_decision_support


def player(player_id: int, position: str) -> dict:
    return {
        "player_id": player_id,
        "web_name": f"Player {player_id}",
        "position": position,
        "team_id": player_id,
        "price": 5.0,
        "selected_by_percent": "10.0",
        "status": "a",
    }


class ChipContextWiringTests(unittest.TestCase):
    def test_first_gameweek_multiplier_changes_chip_captain_and_threshold(self) -> None:
        positions = (
            ["Goalkeeper"] * 2
            + ["Defender"] * 5
            + ["Midfielder"] * 5
            + ["Forward"] * 3
        )
        players = [
            player(index, position)
            for index, position in enumerate(positions, start=1)
        ]
        squad = [
            {"player_id": row["player_id"], "selling_price": 50}
            for row in players
        ]
        projections = []
        for row in players:
            player_id = row["player_id"]
            if player_id == 15:
                projections.extend(
                    [
                        {
                            "player_id": player_id,
                            "team_id": row["team_id"],
                            "gameweek": 3,
                            "fixture_id": 3001,
                            "expected_points": 2.0,
                        },
                        {
                            "player_id": player_id,
                            "team_id": row["team_id"],
                            "gameweek": 3,
                            "fixture_id": 3002,
                            "expected_points": 2.0,
                        },
                    ]
                )
                continue
            projections.append(
                {
                    "player_id": player_id,
                    "team_id": row["team_id"],
                    "gameweek": 3,
                    "fixture_id": 3000 + player_id,
                    "expected_points": 5.0 if player_id == 12 else 2.0,
                }
            )

        route = {
            "status": "ready",
            "horizon_gameweeks": [3],
            "routes": [
                {
                    "gameweek_plan": [
                        {
                            "gameweek": 3,
                            "transfers": [],
                            "net_expected_points": 30.0,
                            "hit_cost": 0,
                        }
                    ]
                }
            ],
        }
        chip_state = {
            "status": "ready",
            "chips": {
                "wildcard": {"remaining": 0},
                "freehit": {"remaining": 0},
                "bboost": {"remaining": 0},
                "3xc": {"remaining": 1},
            },
            "periods": [
                {
                    "status": "current",
                    "end_gameweek": 19,
                    "chips": {
                        "wildcard": {"remaining": 0},
                        "freehit": {"remaining": 0},
                        "bboost": {"remaining": 0},
                        "3xc": {"remaining": 1},
                    },
                }
            ],
        }

        raw = optimise_chip_plan(
            projections, players, squad, 0.0, chip_state, route, 3
        )
        self.assertEqual(raw["best_by_chip"]["3xc"]["captain_player_id"], 12)
        self.assertEqual(raw["best_by_chip"]["3xc"]["status"], "hold")

        adjusted = optimise_chip_plan(
            projections,
            players,
            squad,
            0.0,
            chip_state,
            route,
            3,
            first_gameweek_multiplier={15: 2.0},
        )
        self.assertEqual(
            adjusted["best_by_chip"]["3xc"]["captain_player_id"], 15
        )
        self.assertEqual(
            adjusted["best_by_chip"]["3xc"]["incremental_expected_points"],
            8.0,
        )
        self.assertEqual(adjusted["best_by_chip"]["3xc"]["status"], "play")
        self.assertEqual(adjusted["recommendation"]["action"], "play")
        self.assertTrue(
            adjusted["context_wiring"]["first_gameweek_multiplier_applied"]
        )
        self.assertEqual(adjusted["context_wiring"]["adjusted_player_count"], 1)

    def test_decision_layer_forwards_selection_multiplier_to_chip_optimizer(self) -> None:
        horizons = [
            {
                "model_version": "player-ensemble-test",
                "player_id": 1,
                "web_name": "Forward",
                "team_id": 1,
                "team_name": "Club 1",
                "position": "Forward",
                "price": 5.0,
                "expected_points_next_1": 4.0,
                "expected_points_next_3": 12.0,
                "expected_minutes_next_1": 90.0,
                "points_p90_next_1": 8.0,
                "probability_10_plus_next_1": 0.1,
                "probability_15_plus_next_1": 0.02,
            }
        ]
        players = [
            {
                "player_id": 1,
                "team_id": 1,
                "position": "Forward",
                "price": 5.0,
                "selected_by_percent": "10.0",
                "status": "d",
                "chance_of_playing_next_round": 50,
                "starts": 2,
                "minutes": 180,
            }
        ]
        route = {
            "status": "ready",
            "horizon_gameweeks": [3],
            "routes": [
                {
                    "gameweek_plan": [
                        {
                            "gameweek": 3,
                            "transfers": [],
                            "net_expected_points": 4.0,
                        }
                    ]
                }
            ],
        }

        with (
            patch(
                "src.fpl_decisions.derive_chip_state",
                return_value={"status": "ready"},
            ),
            patch(
                "src.fpl_decisions.derive_free_transfer_state",
                return_value={
                    "status": "ready",
                    "available": 2,
                    "maximum": 5,
                    "hit_cost": 4,
                },
            ),
            patch(
                "src.fpl_decisions.optimise_multi_gameweek_route",
                return_value=route,
            ) as mock_route,
            patch(
                "src.fpl_decisions.optimise_chip_plan",
                return_value={"status": "ready", "recommendation": None},
            ) as mock_chip,
            patch(
                "src.fpl_decisions.build_initial_squad_plan",
                return_value={"status": "not_applicable_after_gameweek_1"},
            ),
        ):
            build_decision_support(
                horizons,
                players,
                {"team_id": 1, "available": False, "entry_history": {"bank": 0}},
                {"next": {"id": 3}},
                [],
                {"schema_version": "external-context-1.0", "sources": []},
                generated_at="2026-09-04T12:00:00+00:00",
                fixture_projections=[],
            )

        route_multiplier = mock_route.call_args.kwargs["first_gameweek_multiplier"]
        chip_multiplier = mock_chip.call_args.kwargs["first_gameweek_multiplier"]
        self.assertAlmostEqual(route_multiplier[1], 0.825, places=3)
        self.assertEqual(chip_multiplier, route_multiplier)


if __name__ == "__main__":
    unittest.main()
