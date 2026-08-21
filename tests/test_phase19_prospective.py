from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.fpl_prospective import (
    MINIMUM_GAMEWEEKS_FOR_EVIDENCE,
    build_snapshot,
    evaluate,
    update_prospective_evaluation,
)


def player(player_id: int, position: str, ownership: float = 1) -> dict:
    return {
        "player_id": player_id,
        "web_name": f"Player {player_id}",
        "team_id": ((player_id - 1) % 8) + 1,
        "position": position,
        "selected_by_percent": ownership,
    }


class Phase19ProspectiveTests(unittest.TestCase):
    def setUp(self) -> None:
        positions = (
            ["Goalkeeper"] * 2
            + ["Defender"] * 5
            + ["Midfielder"] * 5
            + ["Forward"] * 3
        )
        self.players = [
            player(index, position, ownership=20 - index)
            for index, position in enumerate(positions, start=1)
        ]
        self.horizons = [
            {
                **row,
                "model_version": "model-1",
                "expected_points_next_1": 20 - row["player_id"],
                "quantitative_expected_points_next_1": 19 - row["player_id"],
                "expected_minutes_next_1": 90,
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
        self.now = datetime(2026, 8, 14, 10, tzinfo=timezone.utc)
        lineup = [
            {
                **row,
                "decision_expected_points": 20 - row["player_id"],
                "model_expected_points": 20 - row["player_id"],
                "ownership_percent": 20 - row["player_id"],
                "context_signal_ids": [],
            }
            for row in self.players[:11]
        ]
        bench = [
            {
                **row,
                "decision_expected_points": 20 - row["player_id"],
                "model_expected_points": 20 - row["player_id"],
                "ownership_percent": 20 - row["player_id"],
                "context_signal_ids": [],
            }
            for row in self.players[11:]
        ]
        self.decision = {
            "decision_version": "fpl-decisions-1.5",
            "model_version": "model-1",
            "status": "ready",
            "target_gameweek": 1,
            "team_id": 1,
            "recommended_lineup": lineup,
            "bench_order": bench,
            "captaincy": {"captain": lineup[0]},
            "multi_gameweek_plan": {
                "recommended_route": {
                    "gameweek_plan": [
                        {
                            "gameweek": 1,
                            "transfers": [],
                            "starter_player_ids": [row["player_id"] for row in lineup],
                            "captain_player_id": 1,
                            "hit_cost": 0,
                        }
                    ]
                }
            },
            "chip_optimisation": {"recommendation": {"action": "hold"}},
        }
        self.current = {
            "next": {
                "id": 1,
                "deadline_time": (self.now + timedelta(hours=2)).isoformat(),
            }
        }
        self.registry = {"sources": []}

    def test_builds_six_predeadline_experiment_arms(self) -> None:
        snapshot = build_snapshot(
            self.decision,
            self.horizons,
            self.players,
            self.my_team,
            self.current,
            [],
            self.registry,
            self.now.isoformat(),
        )
        self.assertIsNotNone(snapshot)
        self.assertEqual(len(snapshot["arms"]), 6)
        self.assertEqual(
            {arm["arm_id"] for arm in snapshot["arms"]},
            {
                "system_strategy",
                "full_context_selection",
                "no_odds_selection",
                "no_external_selection",
                "quantitative_only_selection",
                "ownership_baseline",
            },
        )

    def test_refuses_post_deadline_snapshot(self) -> None:
        late = (self.now + timedelta(hours=3)).isoformat()
        self.assertIsNone(
            build_snapshot(
                self.decision,
                self.horizons,
                self.players,
                self.my_team,
                self.current,
                [],
                self.registry,
                late,
            )
        )

    def test_gameweek_one_snapshot_uses_initial_plan_before_picks_exist(self) -> None:
        initial_squad = [
            {**row, "gameweek_1_expected_points": 20 - row["player_id"]}
            for row in self.players
        ]
        decision = {
            **self.decision,
            "recommended_lineup": [],
            "bench_order": [],
            "initial_squad_plan": {
                "status": "ready",
                "recommended_squad": initial_squad,
                "recommended_starting_xi": initial_squad[:11],
                "recommended_bench_order": initial_squad[11:],
                "captain": initial_squad[0],
                "planned_transfer_route": self.decision[
                    "multi_gameweek_plan"
                ],
            },
        }
        snapshot = build_snapshot(
            decision,
            self.horizons,
            self.players,
            {"available": True, "squad": []},
            self.current,
            [],
            self.registry,
            self.now.isoformat(),
        )
        self.assertIsNotNone(snapshot)
        system = next(
            arm for arm in snapshot["arms"] if arm["arm_id"] == "system_strategy"
        )
        self.assertEqual(len(system["squad_player_ids"]), 15)
        self.assertEqual(len(system["starter_player_ids"]), 11)

    def test_scores_only_finalised_gameweeks_and_uses_latest_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            update_prospective_evaluation(
                data,
                self.decision,
                self.horizons,
                self.players,
                self.my_team,
                self.current,
                [],
                self.registry,
                self.now.isoformat(),
            )
            chatgpt = data / "chatgpt"
            chatgpt.mkdir(parents=True, exist_ok=True)
            (chatgpt / "gameweeks.json").write_text(
                json.dumps([{"id": 1, "finished": True, "data_checked": False}]),
                encoding="utf-8",
            )
            (chatgpt / "player_gameweeks.csv").write_text(
                "gameweek,player_id,total_points\n"
                + "".join(f"1,{index},{index}\n" for index in range(1, 16)),
                encoding="utf-8",
            )
            rows, summary = evaluate(data)
            self.assertEqual(rows, [])
            self.assertEqual(summary["skipped_unfinalised_gameweeks"], 1)
            (chatgpt / "gameweeks.json").write_text(
                json.dumps([{"id": 1, "finished": True, "data_checked": True}]),
                encoding="utf-8",
            )
            rows, summary = evaluate(data)
            self.assertEqual(len(rows), 6)
            self.assertEqual(summary["evaluated_gameweeks"], 1)
            self.assertTrue(all(row["leakage_safe"] for row in rows))

    def test_evidence_gate_does_not_claim_value_early(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            update_prospective_evaluation(
                data,
                self.decision,
                self.horizons,
                self.players,
                self.my_team,
                self.current,
                [],
                self.registry,
                self.now.isoformat(),
            )
            chatgpt = data / "chatgpt"
            (chatgpt / "gameweeks.json").write_text(
                json.dumps([{"id": 1, "finished": True, "data_checked": True}]),
                encoding="utf-8",
            )
            (chatgpt / "player_gameweeks.csv").write_text(
                "gameweek,player_id,total_points\n"
                + "".join(f"1,{index},2\n" for index in range(1, 16)),
                encoding="utf-8",
            )
            _, summary = evaluate(data)
            self.assertEqual(summary["minimum_gameweeks_for_evidence"], MINIMUM_GAMEWEEKS_FOR_EVIDENCE)
            self.assertTrue(
                all(row["status"] == "insufficient_evidence" for row in summary["comparisons"])
            )


if __name__ == "__main__":
    unittest.main()
