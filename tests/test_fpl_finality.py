from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.build_fpl_model import evaluate_predictions
from src.fpl_finality import gameweek_finality


class FplFinalityTests(unittest.TestCase):
    def test_live_bootstrap_overrides_stale_historical_gameweeks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            (data / "raw" / "latest").mkdir(parents=True)
            (data / "chatgpt").mkdir(parents=True)
            (data / "raw" / "latest" / "bootstrap-static.json").write_text(
                json.dumps(
                    {"events": [{"id": 1, "finished": False, "data_checked": False}]}
                ),
                encoding="utf-8",
            )
            (data / "chatgpt" / "gameweeks.json").write_text(
                json.dumps([{"id": 1, "finished": True, "data_checked": True}]),
                encoding="utf-8",
            )

            finality, source = gameweek_finality(data)

            self.assertFalse(finality[1])
            self.assertEqual(source, "raw/latest/bootstrap-static.json")

    def test_prediction_evaluation_audits_the_submitted_starting_xi(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            (data / "raw" / "latest").mkdir(parents=True)
            (data / "chatgpt").mkdir(parents=True)
            prediction_dir = data / "predictions" / "gw01"
            prediction_dir.mkdir(parents=True)
            (data / "raw" / "latest" / "bootstrap-static.json").write_text(
                json.dumps(
                    {"events": [{"id": 1, "finished": True, "data_checked": True}]}
                ),
                encoding="utf-8",
            )
            picks = [
                {
                    "element": player_id,
                    "multiplier": 2 if player_id == 1 else (1 if player_id <= 11 else 0),
                    "is_captain": player_id == 1,
                }
                for player_id in range(1, 16)
            ]
            (data / "raw" / "latest" / "latest-picks.json").write_text(
                json.dumps({"entry_history": {"event": 1, "points": 24}, "picks": picks}),
                encoding="utf-8",
            )
            with (prediction_dir / "snapshot.csv").open(
                "w", newline="", encoding="utf-8"
            ) as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "target_gameweek",
                        "model_version",
                        "player_id",
                        "expected_points_next_1",
                    ],
                )
                writer.writeheader()
                for player_id in range(1, 16):
                    writer.writerow(
                        {
                            "target_gameweek": 1,
                            "model_version": "test",
                            "player_id": player_id,
                            "expected_points_next_1": 4,
                        }
                    )
            with (data / "chatgpt" / "player_gameweeks.csv").open(
                "w", newline="", encoding="utf-8"
            ) as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=["gameweek", "player_id", "total_points"]
                )
                writer.writeheader()
                for player_id in range(1, 16):
                    writer.writerow(
                        {"gameweek": 1, "player_id": player_id, "total_points": 2}
                    )

            result = evaluate_predictions(data)

            audit = result["managed_team_latest"]
            self.assertEqual(audit["selected_xi_players_evaluated"], 11)
            self.assertEqual(audit["selected_xi_mean_absolute_error"], 2)
            self.assertEqual(audit["submitted_team_actual_points"], 24)
            self.assertEqual(audit["bench_actual_points"], 8)


if __name__ == "__main__":
    unittest.main()
