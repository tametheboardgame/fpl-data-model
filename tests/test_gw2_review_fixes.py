from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src.fpl_gameweek_operations import _selection
from src.fpl_prospective import build_snapshot


POSITIONS = (
    ["Goalkeeper"] * 2
    + ["Defender"] * 5
    + ["Midfielder"] * 5
    + ["Forward"] * 3
)


def player(player_id: int, position: str, team_id: int | None = None) -> dict:
    return {
        "player_id": player_id,
        "web_name": f"Player {player_id}",
        "team_id": team_id or ((player_id - 1) % 8) + 1,
        "team_name": f"Team {team_id or ((player_id - 1) % 8) + 1}",
        "position": position,
        "selected_by_percent": 20 - player_id,
        "status": "a",
    }


class Gw2ReviewFixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.players = [
            player(index, position)
            for index, position in enumerate(POSITIONS, start=1)
        ]
        self.players[2]["team_id"] = 1
        self.players[2]["team_name"] = "Team 1"
        self.players[7]["team_id"] = 2
        self.players[7]["team_name"] = "Team 2"
        self.player_by_id = {row["player_id"]: row for row in self.players}
        self.horizons = [
            {
                **row,
                "expected_points_next_1": 20 - row["player_id"],
                "quantitative_expected_points_next_1": 19 - row["player_id"],
            }
            for row in self.players
        ]
        self.my_team = {
            "available": True,
            "squad": [
                {"player_id": row["player_id"], "position": row["position"]}
                for row in self.players
            ],
        }
        starter_ids = [1, 3, 4, 5, 8, 9, 10, 11, 12, 13, 14]
        lineup = [
            {
                **self.player_by_id[player_id],
                "decision_expected_points": 20 - player_id,
                "selection_expected_points": 20 - player_id,
            }
            for player_id in starter_ids
        ]
        bench = [
            {
                **self.player_by_id[player_id],
                "decision_expected_points": 20 - player_id,
                "selection_expected_points": 20 - player_id,
            }
            for player_id in [2, 6, 7, 15]
        ]
        self.decision = {
            "status": "ready",
            "target_gameweek": 2,
            "recommended_lineup": lineup,
            "bench_order": bench,
            "captaincy": {
                "captain": {"player_id": 8},
                "vice_captain": {"player_id": 9},
            },
            "lineup_correlation": {
                "opposing_pairs": [],
                "opposing_pair_count": 0,
                "negative_correlation_exposure": 0,
            },
            "multi_gameweek_plan": {
                "recommended_route": {
                    "gameweek_plan": [
                        {
                            "gameweek": 2,
                            "transfers": [],
                            "starter_player_ids": starter_ids,
                            "captain_player_id": 8,
                            "hit_cost": 0,
                        }
                    ]
                }
            },
            "chip_optimisation": {"recommendation": {"action": "hold"}},
        }

    def test_operations_recomputes_correlation_for_route_selected_xi(self) -> None:
        fixtures = [
            {
                "gameweek": 2,
                "fixture_id": 100,
                "player_id": 3,
                "team_id": 1,
                "opponent_team_id": 2,
                "clean_sheet_probability": 0.45,
                "component_clean_sheet_points": 1.8,
                "expected_minutes": 90,
            },
            {
                "gameweek": 2,
                "fixture_id": 100,
                "player_id": 8,
                "team_id": 2,
                "opponent_team_id": 1,
                "expected_goals": 0.5,
                "expected_assists": 0.2,
            },
        ]
        selection = _selection(
            self.decision,
            self.player_by_id,
            self.horizons,
            self.my_team,
            2,
            fixtures,
        )
        correlation = selection["lineup_correlation"]
        self.assertEqual(correlation["opposing_pair_count"], 1)
        pair = correlation["opposing_pairs"][0]
        self.assertEqual(pair["defender_player_id"], 3)
        self.assertEqual(pair["attacker_player_id"], 8)

    def test_snapshot_excludes_context_for_players_outside_every_arm(self) -> None:
        outsider = player(16, "Forward", team_id=9)
        players = self.players + [outsider]
        horizons = self.horizons + [
            {
                **outsider,
                "expected_points_next_1": 30,
                "quantitative_expected_points_next_1": 30,
            }
        ]
        now = datetime(2026, 8, 25, 10, tzinfo=timezone.utc)
        current = {
            "next": {
                "id": 2,
                "deadline_time": (now + timedelta(hours=2)).isoformat(),
            }
        }

        def fake_resolved_context(signals, registry, row, fixture, created_at):
            return {
                "signal_ids": [f"signal-{row['player_id']}"],
                "values": {},
                "strengths": {},
            }

        with patch(
            "src.fpl_prospective.resolved_context",
            side_effect=fake_resolved_context,
        ):
            snapshot = build_snapshot(
                self.decision,
                horizons,
                players,
                self.my_team,
                current,
                [{"signal_id": "placeholder"}],
                {"sources": []},
                now.isoformat(),
            )

        self.assertIsNotNone(snapshot)
        self.assertNotIn("signal-16", snapshot["active_context_signal_ids"])
        self.assertIn("signal-3", snapshot["active_context_signal_ids"])
        self.assertEqual(len(snapshot["active_context_signal_ids"]), 15)


if __name__ == "__main__":
    unittest.main()
