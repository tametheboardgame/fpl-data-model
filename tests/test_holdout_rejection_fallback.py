from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.build_fpl_model import load_ensemble_config
from src.fpl_decisions import selection_risk_adjustment


class HoldoutRejectionFallbackTests(unittest.TestCase):
    def test_rejected_ensemble_falls_back_to_control_weights(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.json"
            path.write_text(
                json.dumps(
                    {
                        "status": "holdout_rejected",
                        "assessment": {
                            "selection": {
                                "selected_point_weight": 0.2,
                                "selected_probability_weights": {
                                    "6": 0.5,
                                    "10": 0.4,
                                    "15": 1.0,
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            config = load_ensemble_config(path)
        self.assertFalse(config["enabled"])
        self.assertEqual(config["status"], "holdout_rejected")
        self.assertEqual(config["point_weight"], 0.0)
        self.assertEqual(config["probability_weights"], {"6": 0.0, "10": 0.0, "15": 0.0})

    def test_sticky_production_policy_blocks_repromoted_development_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model_dir = Path(directory)
            candidate = model_dir / "ensemble_model_candidate.json"
            candidate.write_text(
                json.dumps(
                    {
                        "status": "recommended_for_live_promotion",
                        "assessment": {
                            "selection": {
                                "selected_point_weight": 0.2,
                                "selected_probability_weights": {
                                    "6": 0.5,
                                    "10": 0.4,
                                    "15": 1.0,
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            (model_dir / "ensemble_production_policy.json").write_text(
                json.dumps({"status": "holdout_rejected"}),
                encoding="utf-8",
            )
            config = load_ensemble_config(candidate)

        self.assertFalse(config["enabled"])
        self.assertEqual(config["status"], "holdout_rejected")
        self.assertEqual(config["model_version"], "player-sim-2.0")
        self.assertEqual(config["point_weight"], 0.0)
        self.assertEqual(
            config["probability_weights"],
            {"6": 0.0, "10": 0.0, "15": 0.0},
        )

    def test_production_policy_requires_explicit_approval_before_candidate_can_go_live(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model_dir = Path(directory)
            candidate = model_dir / "ensemble_model_candidate.json"
            candidate.write_text(
                json.dumps(
                    {
                        "status": "recommended_for_live_promotion",
                        "assessment": {
                            "selection": {
                                "selected_point_weight": 0.2,
                                "selected_probability_weights": {
                                    "6": 0.5,
                                    "10": 0.4,
                                    "15": 1.0,
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            policy = model_dir / "ensemble_production_policy.json"
            policy.write_text(
                json.dumps({"status": "prospective_review_pending"}),
                encoding="utf-8",
            )
            blocked = load_ensemble_config(candidate)
            policy.write_text(
                json.dumps({"status": "approved_for_live"}),
                encoding="utf-8",
            )
            approved = load_ensemble_config(candidate)

        self.assertFalse(blocked["enabled"])
        self.assertEqual(blocked["status"], "prospective_review_pending")
        self.assertTrue(approved["enabled"])
        self.assertEqual(approved["status"], "recommended_for_live_promotion")
        self.assertEqual(approved["point_weight"], 0.2)

    def test_unreadable_production_policy_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model_dir = Path(directory)
            candidate = model_dir / "ensemble_model_candidate.json"
            candidate.write_text(
                json.dumps({"status": "recommended_for_live_promotion"}),
                encoding="utf-8",
            )
            (model_dir / "ensemble_production_policy.json").write_text(
                "{not-json", encoding="utf-8"
            )
            config = load_ensemble_config(candidate)

        self.assertFalse(config["enabled"])
        self.assertEqual(config["status"], "production_policy_unreadable")

    def test_rejected_shadow_challenger_cannot_penalise_control_selection(self) -> None:
        adjustment = selection_risk_adjustment(
            {
                "position": "Forward",
                "starts": 2,
                "minutes": 180,
                "status": "a",
            },
            {
                "ensemble_status": "holdout_rejected",
                "ensemble_point_weight": 0.0,
                "current_season_fixture_count": 2,
                "expected_minutes_next_1": 81,
                "component_expected_minutes_next_1": 50,
                "control_expected_points_next_1": 6.0,
                "component_expected_points_next_1": 3.8,
                "points_p90_next_1": 11,
                "probability_10_plus_next_1": 0.2,
                "probability_15_plus_next_1": 0.05,
            },
            {"decision_expected_points": 6.4, "market_adjustment_points": 0.0},
            target_gameweek=4,
        )
        self.assertEqual(adjustment["observed_fixture_count"], 2)
        self.assertEqual(adjustment["minutes_risk_penalty"], 0.0)
        self.assertEqual(adjustment["model_disagreement_penalty"], 0.0)
        self.assertEqual(adjustment["selection_expected_points"], 6.4)

    def test_usage_denominator_is_actual_observed_fixtures_not_open_gameweek_number(self) -> None:
        adjustment = selection_risk_adjustment(
            {
                "position": "Forward",
                "starts": 2,
                "minutes": 180,
                "status": "a",
            },
            {
                "ensemble_status": "recommended_for_live_promotion",
                "ensemble_point_weight": 0.2,
                "current_season_fixture_count": 2,
                "expected_minutes_next_1": 81,
                "control_expected_points_next_1": 5.0,
                "component_expected_points_next_1": 5.0,
                "points_p90_next_1": 9,
                "probability_10_plus_next_1": 0.1,
                "probability_15_plus_next_1": 0.02,
            },
            {"decision_expected_points": 5.0, "market_adjustment_points": 0.0},
            target_gameweek=4,
        )
        self.assertEqual(adjustment["observed_fixture_count"], 2)
        self.assertEqual(adjustment["observed_usage_rate"], 1.0)
        self.assertEqual(adjustment["minutes_risk_penalty"], 0.0)

    def test_active_ensemble_can_still_use_model_disagreement_risk(self) -> None:
        adjustment = selection_risk_adjustment(
            {
                "position": "Forward",
                "starts": 0,
                "minutes": 30,
                "status": "a",
            },
            {
                "ensemble_status": "recommended_for_live_promotion",
                "ensemble_point_weight": 0.2,
                "current_season_fixture_count": 2,
                "expected_minutes_next_1": 81,
                "component_expected_minutes_next_1": 50,
                "control_expected_points_next_1": 6.0,
                "component_expected_points_next_1": 3.8,
                "points_p90_next_1": 11,
                "probability_10_plus_next_1": 0.2,
                "probability_15_plus_next_1": 0.05,
            },
            {"decision_expected_points": 6.0, "market_adjustment_points": 0.0},
            target_gameweek=3,
        )
        self.assertGreater(adjustment["model_disagreement_penalty"], 0.0)
        self.assertGreater(adjustment["minutes_risk_penalty"], 0.0)


if __name__ == "__main__":
    unittest.main()
