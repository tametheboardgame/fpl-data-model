from __future__ import annotations

import unittest

from src.validate_captain_objective import (
    PRIMARY_SEASONS,
    build_lagged_ownership,
    evaluate_acceptance,
    normalise_price,
)


class CaptainObjectiveValidationTests(unittest.TestCase):
    def test_lagged_ownership_uses_previous_gameweek_and_deduplicates_double_rows(self) -> None:
        rows = []
        for player_id in range(1, 31):
            rows.append(
                {
                    "season": "2020-21",
                    "gameweek": 1,
                    "element": player_id,
                    "player_name": f"P{player_id}",
                    "selected": 500,
                }
            )
        # Duplicate fixture row for player 1 must not inflate the manager base.
        rows.append(
            {
                "season": "2020-21",
                "gameweek": 1,
                "element": 1,
                "player_name": "P1",
                "selected": 500,
            }
        )
        # A large target-GW count must not leak backwards into the GW2 input.
        rows.append(
            {
                "season": "2020-21",
                "gameweek": 2,
                "element": 1,
                "player_name": "P1",
                "selected": 900,
            }
        )

        lagged, managers = build_lagged_ownership(rows)
        self.assertEqual(managers[("2020-21", 1)], 1000.0)
        self.assertEqual(lagged[("2020-21", 2, "1")], 50.0)

    def test_acceptance_requires_noninferiority_and_positive_upside(self) -> None:
        metrics = {
            "gameweeks": 140,
            "ownership_coverage_rate": 0.95,
            "mean_captain_points_difference": 0.03,
            "mean_regret_difference": -0.03,
            "best_captain_hit_rate_difference": 0.0,
            "captain_10_plus_rate_difference": 0.0,
            "captain_15_plus_rate_difference": 0.0,
            "defensive_captain_rate_difference": 0.0,
            "defensive_switch_cases": 3,
            "defensive_switch_false_positive_rate": 1.0,
        }
        by_season = {
            season: {
                "gameweeks": 35,
                "mean_captain_points_difference": 0.0,
                "mean_regret_difference": 0.0,
            }
            for season in PRIMARY_SEASONS
        }
        accepted = evaluate_acceptance(metrics, by_season)
        self.assertEqual(accepted["status"], "accepted")
        self.assertTrue(accepted["recommended_for_current_gameweek_authority"])

        rejected_metrics = dict(metrics)
        rejected_metrics["mean_captain_points_difference"] = -0.2
        rejected_metrics["mean_regret_difference"] = 0.2
        rejected = evaluate_acceptance(rejected_metrics, by_season)
        self.assertEqual(rejected["status"], "rejected")
        self.assertIn("mean_captain_points_noninferior", rejected["failed_gates"])

    def test_inadequate_sample_is_inconclusive_not_rejected(self) -> None:
        metrics = {
            "gameweeks": 20,
            "ownership_coverage_rate": 0.95,
            "mean_captain_points_difference": 0.2,
            "mean_regret_difference": -0.2,
            "best_captain_hit_rate_difference": 0.1,
            "captain_10_plus_rate_difference": 0.1,
            "captain_15_plus_rate_difference": 0.1,
            "defensive_captain_rate_difference": 0.0,
            "defensive_switch_cases": 0,
            "defensive_switch_false_positive_rate": None,
        }
        by_season = {
            season: {
                "gameweeks": 5,
                "mean_captain_points_difference": 0.0,
                "mean_regret_difference": 0.0,
            }
            for season in PRIMARY_SEASONS
        }
        result = evaluate_acceptance(metrics, by_season)
        self.assertEqual(result["status"], "inconclusive")
        self.assertFalse(result["recommended_for_current_gameweek_authority"])

    def test_historical_price_normalisation_handles_tenths(self) -> None:
        self.assertEqual(normalise_price("155"), 15.5)
        self.assertEqual(normalise_price("7.5"), 7.5)


if __name__ == "__main__":
    unittest.main()
