from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.fpl_decisions import DECISION_VERSION
from src.fpl_gameweek_operations import (
    OPERATIONS_VERSION,
    build_gameweek_report,
    render_markdown,
    update_gameweek_operations,
)


GENERATED = "2026-08-14T10:00:00+00:00"
DEADLINE = "2026-08-14T16:30:00+00:00"


def player(player_id: int, position: str, status: str = "a", chance=None, news: str = "") -> dict:
    return {
        "player_id": player_id,
        "web_name": f"Player {player_id}",
        "team_id": ((player_id - 1) % 10) + 1,
        "team_name": f"Club {((player_id - 1) % 10) + 1}",
        "position": position,
        "status": status,
        "chance_of_playing_next_round": chance,
        "news": news,
    }


class Phase21OperationsTests(unittest.TestCase):
    def setUp(self) -> None:
        positions = ["Goalkeeper"] * 2 + ["Defender"] * 5 + ["Midfielder"] * 5 + ["Forward"] * 3
        self.players = [player(index, position) for index, position in enumerate(positions, start=1)]
        self.horizons = [
            {"player_id": row["player_id"], "expected_points_next_1": 20 - row["player_id"] / 2}
            for row in self.players
        ]
        self.my_team = {
            "available": True,
            "squad": [{"player_id": row["player_id"]} for row in self.players],
        }
        self.current = {
            "generated_at": GENERATED,
            "next": {"id": 1, "deadline_time": DEADLINE},
        }
        self.projections = [
            {
                "gameweek": gameweek,
                "fixture_id": gameweek * 100 + row["team_id"],
                "player_id": row["player_id"],
                "team_id": row["team_id"],
                "opponent_team_id": 20 - row["team_id"],
                "kickoff_time": f"2026-08-{14 + gameweek:02d}T14:00:00Z",
                "expected_points": 4,
            }
            for gameweek in (1, 2, 3)
            for row in self.players
        ]
        starters = list(range(1, 12))
        self.decision = {
            "status": "ready",
            "decision_version": DECISION_VERSION,
            "target_gameweek": 1,
            "bank": 0.5,
            "free_transfer_state": {"available": 1},
            "recommended_lineup": [{"player_id": value} for value in starters],
            "bench_order": [{"player_id": value} for value in range(12, 16)],
            "captaincy": {
                "captain": {"player_id": 1},
                "vice_captain": {"player_id": 2},
            },
            "multi_gameweek_plan": {
                "status": "ready",
                "horizon_gameweeks": [1, 2, 3],
                "recommended_route": {
                    "net_gain_vs_hold": 4.5,
                    "total_hit_cost": 0,
                    "gameweek_plan": [{
                        "gameweek": 1,
                        "transfers": [],
                        "free_transfers_before": 1,
                        "hit_cost": 0,
                        "bank_after": 0.5,
                        "lineup_expected_points": 62.5,
                        "net_expected_points": 62.5,
                        "starter_player_ids": starters,
                        "captain_player_id": 1,
                    }],
                },
            },
            "chip_optimisation": {
                "recommendation": {
                    "action": "hold",
                    "gameweek": 1,
                    "reason": "No chip has sufficient edge.",
                }
            },
            "initial_squad_plan": {
                "launch_validation": {"status": "passed", "issues": []},
            },
        }
        self.prospective = {
            "index": {
                "snapshot_created_this_run": "prospective/gw01/20260814T100000Z.json",
                "snapshots": ["prospective/gw01/20260814T100000Z.json"],
            }
        }

    def build(self, previous=None, generated_at: str = GENERATED):
        return build_gameweek_report(
            self.decision,
            self.horizons,
            self.players,
            self.my_team,
            self.current,
            self.projections,
            {"generated_at": generated_at, "active_signal_rows": 4, "expired_signal_rows": 0},
            self.prospective,
            [],
            generated_at,
            previous,
        )

    def test_builds_review_ready_deadline_report_and_freezes_snapshot(self) -> None:
        report = self.build()
        self.assertEqual(report["operations_version"], OPERATIONS_VERSION)
        self.assertEqual(report["status"], "ready")
        self.assertEqual(len(report["recommendation"]["starting_xi"]), 11)
        self.assertEqual(report["recommendation"]["captain"]["player_id"], 1)
        self.assertEqual(report["recommendation"]["transfer_action"], "roll_or_hold")
        self.assertEqual(report["deadline_freeze"]["status"], "frozen")
        self.assertTrue(report["operational_readiness"]["firm_advice_allowed"])
        self.assertEqual(
            report["operational_readiness"]["late_team_news_review"]["status"],
            "required_before_action",
        )
        self.assertTrue(report["advisory_only"])
        self.assertFalse(report["automatic_fpl_actions"])
        markdown = render_markdown(report)
        self.assertIn("FPL Gameweek 1 Deadline Report", markdown)
        self.assertIn("No transfers, chips or team changes are made automatically", markdown)

    def test_waiting_state_contains_no_named_recommendation(self) -> None:
        self.decision["status"] = "waiting_for_future_fixtures"
        self.current["next"] = None
        report = self.build()
        self.assertEqual(report["status"], "waiting_for_recommendations")
        self.assertEqual(report["recommendation"]["starting_xi"], [])
        self.assertEqual(report["recommendation"]["transfers"], [])
        self.assertIsNone(report["target_gameweek"])

    def test_detects_material_captain_fixture_and_availability_changes(self) -> None:
        previous = self.build()
        self.decision["multi_gameweek_plan"]["recommended_route"]["gameweek_plan"][0]["captain_player_id"] = 2
        self.players[1]["status"] = "d"
        self.players[1]["chance_of_playing_next_round"] = 50
        self.players[1]["news"] = "Knock, late test."
        self.projections[0]["kickoff_time"] = "2026-08-15T17:30:00Z"
        report = self.build(previous=previous)
        change_types = {row["type"] for row in report["material_changes"]}
        self.assertIn("captain", change_types)
        self.assertIn("risks", change_types)
        self.assertIn("fixture_signature", change_types)
        self.assertTrue(any(row["code"] == "player_availability" for row in report["warnings"]))

    def test_stale_or_contradictory_inputs_require_review(self) -> None:
        self.current["generated_at"] = "2026-08-14T01:00:00+00:00"
        self.decision["multi_gameweek_plan"]["recommended_route"]["gameweek_plan"][0]["starter_player_ids"] = list(range(1, 11))
        report = self.build()
        codes = {row["code"] for row in report["warnings"]}
        self.assertIn("stale_fpl_data", codes)
        self.assertIn("invalid_starting_xi", codes)
        self.assertEqual(report["status"], "review_required")
        self.assertFalse(report["operational_readiness"]["firm_advice_allowed"])

    def test_missing_final_snapshot_blocks_firm_advice(self) -> None:
        self.prospective = {"index": {"snapshots": []}}
        report = self.build()
        self.assertEqual(report["deadline_freeze"]["status"], "snapshot_missing")
        self.assertIn(
            "deadline_snapshot_missing",
            {row["code"] for row in report["warnings"]},
        )
        self.assertEqual(report["status"], "review_required")
        self.assertFalse(report["operational_readiness"]["firm_advice_allowed"])

    def test_reports_opposing_player_correlation_without_blocking_advice(self) -> None:
        self.decision["lineup_correlation"] = {
            "opposing_pair_count": 1,
            "negative_correlation_exposure": 0.4,
            "opposing_pairs": [
                {"defender": "Player 3", "attacker": "Player 13"}
            ],
        }
        report = self.build()
        warning = next(
            row
            for row in report["warnings"]
            if row["code"] == "opposing_player_correlation"
        )
        self.assertEqual(warning["severity"], "low")
        self.assertTrue(
            report["operational_readiness"]["firm_advice_allowed"]
        )

    def test_gameweek_one_uses_initial_squad_when_registered_team_is_empty(self) -> None:
        self.my_team = {"available": True, "squad": []}
        squad = [{"player_id": row["player_id"]} for row in self.players]
        starter_ids = [1, 3, 4, 5, 8, 9, 10, 11, 12, 13, 14]
        bench_ids = [2, 6, 7, 15]
        starters = [{"player_id": value} for value in starter_ids]
        bench = [{"player_id": value} for value in bench_ids]
        self.decision["initial_squad_plan"] = {
            "status": "ready",
            "recommended_strategy": "balanced",
            "recommended_squad": squad,
            "recommended_starting_xi": starters,
            "recommended_bench_order": bench,
            "captain": {"player_id": 8},
            "vice_captain": {"player_id": 9},
            "bank": 0.5,
            "horizon_gameweeks": [1, 2, 3],
            "strategy_comparison": [
                {
                    "strategy": "balanced",
                    "gameweek_1_expected_points_including_captain": 72,
                }
            ],
            "planned_transfer_route": self.decision["multi_gameweek_plan"],
            "launch_validation": {
                "status": "passed",
                "issues": [],
            },
        }
        report = self.build()
        self.assertEqual(report["status"], "ready")
        self.assertEqual(
            report["recommendation"]["selection_source"],
            "initial_squad_plan",
        )
        self.assertEqual(
            report["recommendation"]["transfer_action"],
            "select_initial_squad",
        )
        self.assertEqual(len(report["recommendation"]["starting_xi"]), 11)
        self.assertEqual(len(report["recommendation"]["bench_order"]), 4)
        self.assertNotIn(
            "invalid_starting_xi",
            {row["code"] for row in report["warnings"]},
        )

    def test_archives_only_materially_changed_reports(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            (data / "context").mkdir(parents=True)
            first = update_gameweek_operations(
                data, self.decision, self.horizons, self.players, self.my_team,
                self.current, self.projections,
                {"generated_at": GENERATED, "active_signal_rows": 0, "expired_signal_rows": 0},
                self.prospective, GENERATED,
            )
            self.assertIsNotNone(first["archive_created_this_run"])
            second = update_gameweek_operations(
                data, self.decision, self.horizons, self.players, self.my_team,
                self.current, self.projections,
                {"generated_at": GENERATED, "active_signal_rows": 0, "expired_signal_rows": 0},
                self.prospective, "2026-08-14T10:05:00+00:00",
            )
            self.assertFalse(second["material_change"])
            self.assertIsNone(second["archive_created_this_run"])
            self.assertEqual(len(list((data / "operations" / "gw01").glob("*.json"))), 1)
            latest = json.loads((data / "chatgpt" / "gameweek_report.json").read_text())
            self.assertEqual(latest["change_summary"], "No material change since the previous report.")


if __name__ == "__main__":
    unittest.main()
