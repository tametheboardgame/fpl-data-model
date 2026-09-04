from __future__ import annotations

import unittest

from src.fpl_gameweek_operations import build_gameweek_report, render_markdown


GENERATED = "2026-09-04T11:00:00+00:00"
DEADLINE = "2026-09-04T17:30:00+00:00"


def player(player_id: int, position: str) -> dict:
    return {
        "player_id": player_id,
        "web_name": f"Player {player_id}",
        "team_id": player_id,
        "team_name": f"Club {player_id}",
        "position": position,
        "price": 5.0,
        "status": "a",
    }


class WildcardOperationsTests(unittest.TestCase):
    def setUp(self) -> None:
        positions = (
            ["Goalkeeper"] * 2
            + ["Defender"] * 5
            + ["Midfielder"] * 5
            + ["Forward"] * 3
            + ["Goalkeeper", "Defender", "Midfielder", "Forward"]
        )
        self.players = [
            player(index, position)
            for index, position in enumerate(positions, start=1)
        ]
        self.horizons = [
            {
                "player_id": row["player_id"],
                "expected_points_next_1": 3.0 + row["player_id"] / 20,
            }
            for row in self.players
        ]
        self.current_squad = list(range(1, 16))
        self.current_starters = [1, 3, 4, 5, 8, 9, 10, 11, 12, 13, 14]
        self.current_bench = [2, 6, 7, 15]
        self.wildcard_squad = [
            1, 16,
            3, 4, 5, 6, 17,
            8, 9, 10, 11, 18,
            13, 14, 19,
        ]
        self.my_team = {
            "available": True,
            "squad": [{"player_id": player_id} for player_id in self.current_squad],
        }
        self.current = {
            "generated_at": GENERATED,
            "next": {"id": 3, "deadline_time": DEADLINE},
        }
        self.projections = [
            {
                "gameweek": gameweek,
                "fixture_id": gameweek * 1000 + row["player_id"],
                "player_id": row["player_id"],
                "team_id": row["team_id"],
                "opponent_team_id": row["team_id"] + 100,
                "kickoff_time": "2026-09-05T14:00:00Z",
                "expected_points": 3.0 + row["player_id"] / 20,
            }
            for gameweek in (3, 4, 5)
            for row in self.players
        ]
        self.decision = {
            "status": "ready",
            "decision_version": "test-decisions",
            "target_gameweek": 3,
            "bank": 0.5,
            "free_transfer_state": {"available": 2},
            "recommended_lineup": [
                {"player_id": value, "decision_expected_points": 4.0}
                for value in self.current_starters
            ],
            "bench_order": [
                {"player_id": value, "decision_expected_points": 3.0}
                for value in self.current_bench
            ],
            "captaincy": {
                "captain": {"player_id": 8},
                "vice_captain": {"player_id": 9},
            },
            "multi_gameweek_plan": {
                "status": "ready",
                "robustness": {"passed": True, "selected_action": "hold"},
                "horizon_gameweeks": [3, 4, 5],
                "recommended_route": {
                    "net_gain_vs_hold": 0.0,
                    "total_hit_cost": 0,
                    "gameweek_plan": [
                        {
                            "gameweek": 3,
                            "transfers": [],
                            "free_transfers_before": 2,
                            "hit_cost": 0,
                            "bank_after": 0.5,
                            "lineup_expected_points": 45.0,
                            "net_expected_points": 45.0,
                            "starter_player_ids": self.current_starters,
                            "captain_player_id": 8,
                        }
                    ],
                },
            },
            "chip_optimisation": {
                "recommendation": {
                    "action": "play",
                    "chip": "wildcard",
                    "chip_name": "Wildcard",
                    "gameweek": 3,
                    "incremental_expected_points": 21.177,
                    "replacement_squad_player_ids": self.wildcard_squad,
                    "starter_player_ids": [1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 19],
                    "captain_player_id": 8,
                    "gameweek_expected_points_by_player": {
                        str(player_id): (
                            7.0 if player_id == 8 else 2.0
                        )
                        for player_id in self.wildcard_squad
                    },
                    "transfers_in_rebuild": 4,
                    "squad_cost": 99.5,
                    "wildcard_objective_version": "captaincy-ceiling-test",
                    "strategic_objective_edge": 12.3,
                    "strategic_objective_score": 101.4,
                    "strategic_audit": [{"gameweek": 3, "captain_player_id": 8}],
                    "wildcard_search_audit": [{"selected": True, "seed_player_ids": [8]}],
                    "wildcard_archetype_separation_points": 1.5,
                    "reason": "The projected gain clears the save threshold within the known horizon.",
                }
            },
            "initial_squad_plan": {"status": "not_applicable_after_gameweek_1"},
        }
        self.prospective = {
            "index": {
                "snapshot_created_this_run": "prospective/gw03/test.json",
                "snapshots": ["prospective/gw03/test.json"],
            }
        }

    def build(self) -> dict:
        return build_gameweek_report(
            self.decision,
            self.horizons,
            self.players,
            self.my_team,
            self.current,
            self.projections,
            {
                "generated_at": GENERATED,
                "active_signal_rows": 0,
                "expired_signal_rows": 0,
            },
            self.prospective,
            [],
            GENERATED,
        )

    def test_wildcard_rebuild_replaces_registered_team_in_report(self) -> None:
        report = self.build()
        selection = report["recommendation"]

        self.assertEqual(report["status"], "ready")
        self.assertEqual(selection["selection_source"], "wildcard_rebuild")
        self.assertEqual(selection["transfer_action"], "play_wildcard")
        self.assertEqual(set(selection["squad_player_ids"]), set(self.wildcard_squad))
        self.assertEqual(len(selection["starting_xi"]), 11)
        self.assertEqual(len(selection["bench_order"]), 4)
        self.assertIn(
            selection["captain"]["player_id"],
            {row["player_id"] for row in selection["starting_xi"]},
        )
        self.assertEqual(
            {row["player_id"] for row in selection["chip_squad_changes"]["out"]},
            {2, 7, 12, 15},
        )
        self.assertEqual(
            {row["player_id"] for row in selection["chip_squad_changes"]["in"]},
            {16, 17, 18, 19},
        )
        self.assertEqual(
            report["chip_recommendation"]["replacement_squad_player_ids"],
            self.wildcard_squad,
        )
        self.assertEqual(report["decision_validation"]["status"], "passed")
        self.assertNotIn(
            "wildcard_rebuild_unavailable",
            {row["code"] for row in report["warnings"]},
        )

        markdown = render_markdown(report)
        self.assertIn("Action: Play Wildcard and rebuild the squad", markdown)
        self.assertIn("Wildcard out:", markdown)
        self.assertIn("Wildcard in:", markdown)
        self.assertNotIn("Roll or hold the transfer", markdown)

    def test_wildcard_preserves_optimiser_captain_and_strategy_audit(self) -> None:
        report = self.build()
        selection = report["recommendation"]
        chip = report["chip_recommendation"]

        # Player 19 has the highest raw mean in this synthetic Wildcard XI, so
        # preserving player 8 proves the operator did not silently recalculate
        # captaincy from mean expected points.
        self.assertEqual(selection["captain"]["player_id"], 8)
        self.assertEqual(selection["wildcard_lineup_source"], "chip_optimisation")
        self.assertEqual(selection["wildcard_objective_version"], "captaincy-ceiling-test")
        self.assertEqual(selection["wildcard_strategic_objective_edge"], 12.3)
        self.assertEqual(chip["captain_player_id"], 8)
        self.assertEqual(chip["wildcard_objective_version"], "captaincy-ceiling-test")
        self.assertEqual(chip["strategic_objective_edge"], 12.3)
        self.assertEqual(chip["strategic_audit"][0]["captain_player_id"], 8)
        self.assertTrue(chip["wildcard_search_audit"][0]["selected"])

    def test_wildcard_report_uses_optimiser_gameweek_mean_basis(self) -> None:
        report = self.build()
        selection = report["recommendation"]
        starter_points = {
            row["player_id"]: row["expected_points"]
            for row in selection["starting_xi"]
        }

        self.assertEqual(selection["wildcard_points_source"], "chip_optimisation_target_gameweek")
        self.assertEqual(starter_points[8], 7.0)
        # Ten other starters at 2.0, captain 8 at 7.0, then captain doubled.
        self.assertEqual(selection["expected_points"], 34.0)
        self.assertEqual(selection["net_expected_points"], 34.0)

    def test_wildcard_report_falls_back_to_horizon_points_without_scoring_map(self) -> None:
        self.decision["chip_optimisation"]["recommendation"].pop(
            "gameweek_expected_points_by_player"
        )

        report = self.build()

        self.assertEqual(
            report["recommendation"]["wildcard_points_source"],
            "horizon_fallback",
        )

    def test_wildcard_lineup_falls_back_when_optimiser_metadata_is_missing(self) -> None:
        recommendation = self.decision["chip_optimisation"]["recommendation"]
        recommendation.pop("starter_player_ids")
        recommendation.pop("captain_player_id")

        report = self.build()
        selection = report["recommendation"]

        self.assertEqual(selection["selection_source"], "wildcard_rebuild")
        self.assertEqual(selection["wildcard_lineup_source"], "mean_lineup_fallback")
        self.assertIn(
            selection["captain"]["player_id"],
            {row["player_id"] for row in selection["starting_xi"]},
        )

    def test_invalid_wildcard_rebuild_blocks_firm_advice(self) -> None:
        self.decision["chip_optimisation"]["recommendation"][
            "replacement_squad_player_ids"
        ] = self.wildcard_squad[:-1]

        report = self.build()

        self.assertEqual(report["status"], "review_required")
        self.assertEqual(
            report["recommendation"]["selection_source"], "registered_team"
        )
        self.assertIn(
            "wildcard_rebuild_unavailable",
            {row["code"] for row in report["warnings"]},
        )
        self.assertFalse(
            report["operational_readiness"]["firm_advice_allowed"]
        )


if __name__ == "__main__":
    unittest.main()
