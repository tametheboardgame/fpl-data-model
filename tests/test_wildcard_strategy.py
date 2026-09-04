from __future__ import annotations

import unittest

from src.fpl_chip_optimizer import (
    WILDCARD_OBJECTIVE_VERSION,
    _captain_utility,
    _ownership_pressure,
    _select_near_optimal_wildcard_variant,
    _strategic_gameweek_score,
    _wildcard_search_heuristic,
    optimise_budget_squad,
)


def player(
    player_id: int,
    position: str,
    *,
    ownership: float = 0.0,
    team_id: int | None = None,
    price: float = 5.0,
) -> dict:
    return {
        "player_id": player_id,
        "web_name": f"Player {player_id}",
        "position": position,
        "team_id": team_id or player_id,
        "price": price,
        "selected_by_percent": ownership,
    }


class WildcardStrategyTests(unittest.TestCase):
    def test_high_ceiling_attacker_can_beat_slightly_higher_mean_captain(self) -> None:
        players = {
            1: player(1, "Midfielder", ownership=5.0),
            2: player(2, "Forward", ownership=75.0),
        }
        expected = {1: 6.2, 2: 5.9}
        p90 = {1: 8.0, 2: 14.0}
        p10 = {1: 0.05, 2: 0.50}
        p15 = {1: 0.0, 2: 0.20}

        efficient = _captain_utility(1, players, expected, p90, p10, p15)[0]
        explosive = _captain_utility(2, players, expected, p90, p10, p15)[0]

        self.assertGreater(explosive, efficient)

    def test_ownership_pressure_is_bounded_and_cannot_rescue_bad_mean(self) -> None:
        players = {
            1: player(1, "Forward", ownership=5.0),
            2: player(2, "Forward", ownership=100.0),
        }
        expected = {1: 7.0, 2: 4.0}
        p90 = {1: 8.0, 2: 5.0}
        p10 = {1: 0.05, 2: 0.05}
        p15 = {1: 0.0, 2: 0.0}

        strong = _captain_utility(1, players, expected, p90, p10, p15)[0]
        weak_popular = _captain_utility(2, players, expected, p90, p10, p15)[0]

        self.assertEqual(_ownership_pressure(players[1]), 0.0)
        self.assertEqual(_ownership_pressure(players[2]), 1.0)
        self.assertGreater(strong, weak_popular)

    def test_explosive_attacker_beats_defender_with_small_mean_edge(self) -> None:
        players = {
            1: player(1, "Midfielder", ownership=50.0),
            2: player(2, "Defender", ownership=75.0),
        }
        expected = {1: 5.7, 2: 5.9}
        p90 = {1: 11.0, 2: 8.0}
        p10 = {1: 0.35, 2: 0.10}
        p15 = {1: 0.10, 2: 0.0}

        attacker = _captain_utility(1, players, expected, p90, p10, p15)[0]
        defender = _captain_utility(2, players, expected, p90, p10, p15)[0]

        self.assertGreater(attacker, defender)

    def test_beam_search_heuristic_keeps_explosive_premium_visible(self) -> None:
        players = {
            1: player(1, "Midfielder", ownership=5.0),
            2: player(2, "Forward", ownership=75.0),
        }
        gameweeks = [3]
        matrix = {3: {1: 6.2, 2: 5.9}}
        p90 = {3: {1: 8.0, 2: 14.0}}
        p10 = {3: {1: 0.05, 2: 0.50}}
        p15 = {3: {1: 0.0, 2: 0.20}}

        heuristic = _wildcard_search_heuristic(
            players,
            gameweeks,
            0,
            matrix,
            p90,
            p10,
            p15,
            0.96,
        )

        self.assertGreater(heuristic[2], heuristic[1])

    def test_strategic_lineup_captain_uses_ceiling_without_fabricating_mean(self) -> None:
        positions = {
            1: "Goalkeeper",
            2: "Defender",
            3: "Defender",
            4: "Defender",
            5: "Defender",
            6: "Defender",
            7: "Midfielder",
            8: "Midfielder",
            9: "Midfielder",
            10: "Midfielder",
            11: "Midfielder",
            12: "Forward",
            13: "Forward",
            14: "Forward",
            15: "Goalkeeper",
        }
        players = {
            pid: player(
                pid,
                position,
                ownership=75.0 if pid == 12 else 5.0,
                team_id=pid,
            )
            for pid, position in positions.items()
        }
        expected = {pid: 4.0 for pid in players}
        expected[7] = 6.2
        expected[12] = 5.9
        p90 = {pid: expected[pid] + 1.0 for pid in players}
        p90[12] = 14.0
        p10 = {pid: 0.02 for pid in players}
        p10[12] = 0.50
        p15 = {pid: 0.0 for pid in players}
        p15[12] = 0.20

        strategic, mean_score, starters, captain, components = _strategic_gameweek_score(
            tuple(players),
            players,
            expected,
            p90,
            p10,
            p15,
        )

        self.assertIn(12, starters)
        self.assertEqual(captain, 12)
        self.assertGreater(strategic, mean_score)
        self.assertGreater(components["strategic_bonus"], 0.0)

    def test_beam_reserves_budget_for_a_legal_completion(self) -> None:
        players = {}
        points = {}
        player_id = 1
        for position, required in (("Goalkeeper", 2), ("Defender", 5), ("Midfielder", 5), ("Forward", 3)):
            # Enough expensive, high-heuristic choices to strand the old beam, plus
            # cheap alternatives that make a legal squad possible under the budget.
            for _ in range(required):
                players[player_id] = player(
                    player_id, position, team_id=player_id, price=10.0
                )
                points[player_id] = 10.0
                player_id += 1
            for _ in range(required):
                players[player_id] = player(
                    player_id, position, team_id=player_id, price=4.0
                )
                points[player_id] = 1.0
                player_id += 1

        result = optimise_budget_squad(
            players, points, budget=100.0, beam_width=1
        )

        self.assertIsNotNone(result)
        squad_ids, cost, _, _, _ = result
        self.assertEqual(len(squad_ids), 15)
        self.assertLessEqual(cost, 100.0)

    def test_preselected_premium_can_complete_budget_legal_squad(self) -> None:
        players = {}
        points = {}
        player_id = 1
        premium_id = 999
        for position, required in (("Goalkeeper", 2), ("Defender", 5), ("Midfielder", 5), ("Forward", 3)):
            for _ in range(required + 2):
                price = 4.0 if position != "Forward" else 5.0
                players[player_id] = player(
                    player_id, position, team_id=player_id, price=price
                )
                points[player_id] = 2.0
                player_id += 1
        players[premium_id] = player(
            premium_id, "Forward", team_id=90, price=15.5
        )
        points[premium_id] = 12.0

        result = optimise_budget_squad(
            players,
            points,
            budget=100.0,
            beam_width=10,
            preselected_player_ids=(premium_id,),
        )

        self.assertIsNotNone(result)
        self.assertIn(premium_id, result[0])
        self.assertEqual(len(result[0]), 15)
        self.assertLessEqual(result[1], 100.0)

    def test_near_optimal_wildcard_prefers_stronger_current_attacking_captain(self) -> None:
        players = {
            1: player(1, "Forward", team_id=1),
            2: player(2, "Forward", team_id=2),
        }
        expected = {1: 7.0, 2: 5.0}
        p90 = {1: 14.0, 2: 9.0}
        p10 = {1: 0.35, 2: 0.10}
        p15 = {1: 0.12, 2: 0.02}
        variants = [
            {"result": ((2,), 5.0, 100.0, [2], 2), "seed_player_ids": ()},
            {"result": ((1,), 5.0, 98.6, [1], 1), "seed_player_ids": (1,)},
        ]

        selected, audit = _select_near_optimal_wildcard_variant(
            variants, players, expected, p90, p10, p15
        )

        self.assertEqual(selected["result"][0], (1,))
        self.assertTrue(next(row for row in audit if row["seed_player_ids"] == [1])["selected"])

    def test_wildcard_separation_band_does_not_rescue_materially_worse_archetype(self) -> None:
        players = {
            1: player(1, "Forward", team_id=1),
            2: player(2, "Forward", team_id=2),
        }
        expected = {1: 7.0, 2: 5.0}
        p90 = {1: 14.0, 2: 9.0}
        p10 = {1: 0.35, 2: 0.10}
        p15 = {1: 0.12, 2: 0.02}
        variants = [
            {"result": ((2,), 5.0, 100.0, [2], 2), "seed_player_ids": ()},
            {"result": ((1,), 5.0, 98.4, [1], 1), "seed_player_ids": (1,)},
        ]

        selected, _ = _select_near_optimal_wildcard_variant(
            variants, players, expected, p90, p10, p15
        )

        self.assertEqual(selected["result"][0], (2,))

    def test_objective_version_records_beam_search_fix(self) -> None:
        self.assertEqual(WILDCARD_OBJECTIVE_VERSION, "captaincy-ceiling-1.3")


if __name__ == "__main__":
    unittest.main()
