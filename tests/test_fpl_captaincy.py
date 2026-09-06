from __future__ import annotations

import unittest

from src.fpl_captaincy import (
    CAPTAIN_UTILITY_VERSION,
    captain_utility,
    ownership_pressure,
    select_strategic_captain,
)
from src.fpl_decisions import selection_risk_adjustment
from src.fpl_multiweek import optimise_gameweek_lineup


class SharedCaptainUtilityTests(unittest.TestCase):
    def test_audit_uses_risk_adjusted_mean_once(self) -> None:
        audit = captain_utility(
            player_id=1,
            mean_expected_points=5.4,
            reference_mean_expected_points=6.0,
            points_p90=12.0,
            probability_10_plus=0.35,
            probability_15_plus=0.12,
            ownership_percent=70.0,
            position="Forward",
            expected_minutes=72.0,
            availability_confidence=0.8,
            selection_risk_penalty=0.6,
        )
        self.assertEqual(audit["version"], CAPTAIN_UTILITY_VERSION)
        self.assertEqual(audit["mean_expected_points"], 5.4)
        self.assertEqual(audit["reference_mean_expected_points"], 6.0)
        self.assertEqual(audit["selection_reliability_ratio"], 0.9)
        self.assertEqual(audit["expected_minutes"], 72.0)
        self.assertEqual(audit["availability_confidence"], 0.8)
        self.assertFalse(audit["strategic_bonus_is_expected_points"])

    def test_ownership_is_bounded_and_cannot_rescue_bad_mean(self) -> None:
        strong = captain_utility(
            player_id=1,
            mean_expected_points=7.0,
            points_p90=8.0,
            probability_10_plus=0.05,
            probability_15_plus=0.0,
            ownership_percent=5.0,
            position="Forward",
        )
        weak_popular = captain_utility(
            player_id=2,
            mean_expected_points=4.0,
            points_p90=5.0,
            probability_10_plus=0.05,
            probability_15_plus=0.0,
            ownership_percent=100.0,
            position="Forward",
        )
        self.assertEqual(ownership_pressure(5.0), 0.0)
        self.assertEqual(ownership_pressure(100.0), 1.0)
        self.assertGreater(strong["captain_score"], weak_popular["captain_score"])

    def test_small_defender_edge_is_rejected_but_exceptional_edge_survives(self) -> None:
        players = {
            1: {"player_id": 1, "position": "Defender", "selected_by_percent": 75.0},
            2: {"player_id": 2, "position": "Forward", "selected_by_percent": 50.0},
        }
        self.assertEqual(
            select_strategic_captain(
                {1, 2},
                players,
                {1: 6.0, 2: 5.8},
                {1: 8.0, 2: 8.5},
                {1: 0.10, 2: 0.10},
                {1: 0.0, 2: 0.01},
            ),
            2,
        )
        self.assertEqual(
            select_strategic_captain(
                {1, 2},
                players,
                {1: 9.0, 2: 5.0},
                {1: 14.0, 2: 8.0},
                {1: 0.40, 2: 0.08},
                {1: 0.10, 2: 0.01},
            ),
            1,
        )

    def test_weekly_decision_score_is_the_shared_utility(self) -> None:
        player = {
            "player_id": 9,
            "position": "Forward",
            "selected_by_percent": 75.0,
            "status": "a",
            "starts": 3,
            "minutes": 270,
        }
        horizon = {
            "player_id": 9,
            "position": "Forward",
            "expected_points_next_1": 6.0,
            "expected_minutes_next_1": 90.0,
            "points_p90_next_1": 13.0,
            "probability_10_plus_next_1": 0.4,
            "probability_15_plus_next_1": 0.12,
            "current_season_fixture_count": 3,
        }
        result = selection_risk_adjustment(
            player,
            horizon,
            {"decision_expected_points": 6.0, "market_adjustment_points": 0.0},
            4,
        )
        direct = captain_utility(
            player_id=9,
            mean_expected_points=result["selection_expected_points"],
            reference_mean_expected_points=6.0,
            points_p90=13.0,
            probability_10_plus=0.4,
            probability_15_plus=0.12,
            ownership_percent=75.0,
            position="Forward",
            expected_minutes=90.0,
            availability_confidence=1.0,
            selection_risk_penalty=0.0,
        )
        self.assertEqual(result["captain_score"], direct["captain_score"])
        self.assertEqual(result["captain_utility"]["version"], CAPTAIN_UTILITY_VERSION)

    def test_multiweek_lineup_doubles_shared_captain_mean_only(self) -> None:
        positions = (
            ["Goalkeeper"] * 2
            + ["Defender"] * 5
            + ["Midfielder"] * 5
            + ["Forward"] * 3
        )
        players = {
            player_id: {
                "player_id": player_id,
                "position": position,
                "team_id": player_id,
                "selected_by_percent": 75.0 if player_id == 13 else 5.0,
            }
            for player_id, position in enumerate(positions, start=1)
        }
        points = {player_id: 4.0 for player_id in players}
        points[8] = 6.2
        points[13] = 5.9
        p90 = {player_id: points[player_id] + 1.0 for player_id in players}
        p90[13] = 14.0
        p10 = {player_id: 0.02 for player_id in players}
        p10[13] = 0.50
        p15 = {player_id: 0.0 for player_id in players}
        p15[13] = 0.20
        score_map = {
            player_id: captain_utility(
                player_id=player_id,
                mean_expected_points=points[player_id],
                points_p90=p90[player_id],
                probability_10_plus=p10[player_id],
                probability_15_plus=p15[player_id],
                ownership_percent=players[player_id]["selected_by_percent"],
                position=players[player_id]["position"],
            )["captain_score"]
            for player_id in players
        }
        lineup_score, starters, captain = optimise_gameweek_lineup(
            tuple(players),
            players,
            points,
            captain_scores_by_player=score_map,
        )
        self.assertEqual(captain, 13)
        self.assertEqual(
            lineup_score,
            sum(points[player_id] for player_id in starters) + points[13],
        )

    def test_ties_are_deterministic(self) -> None:
        players = {
            1: {"player_id": 1, "position": "Forward", "selected_by_percent": 10.0},
            2: {"player_id": 2, "position": "Forward", "selected_by_percent": 10.0},
        }
        selected = select_strategic_captain(
            {2, 1},
            players,
            {1: 6.0, 2: 6.0},
            {1: 10.0, 2: 10.0},
            {1: 0.2, 2: 0.2},
            {1: 0.05, 2: 0.05},
        )
        self.assertEqual(selected, 1)


if __name__ == "__main__":
    unittest.main()
