from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.build_fpl_model import production_policy_reporting
from src.fpl_gameweek_operations import _captaincy_audit


class Fpl22DReportingTests(unittest.TestCase):
    def test_rejected_policy_prose_matches_live_control_and_zero_weights(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ensemble_production_policy.json"
            path.write_text(
                json.dumps(
                    {
                        "status": "holdout_rejected",
                        "live_model_version": "player-sim-2.0",
                        "live_point_weight": 0.0,
                        "live_probability_weights": {"6": 0.0, "10": 0.0, "15": 0.0},
                        "challenger_mode": "shadow_only",
                        "reason": "Independent holdout rejected the challenger.",
                    }
                ),
                encoding="utf-8",
            )
            result = production_policy_reporting(
                path,
                {
                    "status": "holdout_rejected",
                    "model_version": "player-sim-2.0",
                    "point_weight": 0.0,
                    "probability_weights": {"6": 0.0, "10": 0.0, "15": 0.0},
                },
                "shadow_candidate",
            )
        self.assertEqual(result["policy"]["status"], "holdout_rejected")
        self.assertEqual(result["policy"]["live_model_version"], "player-sim-2.0")
        self.assertEqual(result["policy"]["challenger_mode"], "shadow_only")
        self.assertEqual(result["policy"]["live_point_weight"], 0.0)
        self.assertEqual(result["policy"]["live_probability_weights"], {"6": 0.0, "10": 0.0, "15": 0.0})
        self.assertIn("Production uses player-sim-2.0", result["method"])
        self.assertIn("holdout_rejected", result["method"])
        self.assertNotIn("Development-selected ensemble", result["method"])

    def test_operational_captain_audit_separates_mean_xpts_from_strategy(self) -> None:
        audit = {
            "version": "strategic-captain-1.0",
            "player_id": 11,
            "captain_score": 7.25,
            "mean_expected_points": 5.4,
            "bounded_strategic_bonus": 1.3,
            "ceiling_contribution": 1.0,
            "rank_pressure_contribution": 0.3,
            "position_uncertainty_penalty": 0.0,
            "defensive_exception_margin": 0.0,
            "selection_risk_penalty": 0.2,
            "expected_minutes": 87.0,
            "availability_confidence": 1.0,
            "points_p90": 12.0,
            "probability_10_plus": 0.31,
            "probability_15_plus": 0.12,
            "ownership_percent": 58.0,
        }
        decision = {
            "captaincy": {
                "utility_version": "strategic-captain-1.0",
                "player_audits": {"11": audit},
            }
        }
        selection = {
            "captain": {"player_id": 11, "expected_points": 5.1},
            "vice_captain": {"player_id": 12, "expected_points": 4.8},
            "captain_selection_basis": "route_strategic_utility",
            "vice_captain_selection_basis": "mean_xpts_fallback",
        }
        result = _captaincy_audit(decision, selection)
        self.assertEqual(result["captain"]["displayed_mean_xpts"], 5.1)
        self.assertEqual(result["captain"]["risk_adjusted_mean_input"], 5.4)
        self.assertEqual(result["captain"]["strategic_score"], 7.25)
        self.assertEqual(result["captain"]["components"]["bounded_strategic_bonus"], 1.3)
        self.assertFalse(result["captain"]["strategic_bonus_is_expected_points"])
        self.assertFalse(result["vice_captain"]["strategic_utility_available"])
        self.assertEqual(result["vice_captain"]["selection_basis"], "mean_xpts_fallback")
        self.assertEqual(result["reported_xpts_basis"], "mean_expected_points_only")


if __name__ == "__main__":
    unittest.main()
