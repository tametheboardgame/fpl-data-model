from __future__ import annotations

import unittest

from src.player_return_simulator import simulate_player_fixture
from src.component_player_simulator import (
    build_component_inputs,
    simulate_component_player_fixture,
)


class PlayerReturnSimulatorTests(unittest.TestCase):
    def inputs(self) -> dict:
        return {
            "position": "MID",
            "appearance_probability": 0.95,
            "start_probability": 0.9,
            "expected_minutes": 80,
            "minutes_deviation": 10,
            "xg_per_90": 0.35,
            "xa_per_90": 0.25,
            "clean_sheet_probability": 0.35,
            "bonus_per_90": 0.4,
            "defensive_contribution_per_90": 7,
            "yellow_cards_per_90": 0.1,
        }

    def test_simulation_is_deterministic_and_has_distribution(self) -> None:
        first = simulate_player_fixture(
            self.inputs(), simulations=1000, seed_parts=(100, 10)
        )
        second = simulate_player_fixture(
            self.inputs(), simulations=1000, seed_parts=(100, 10)
        )
        self.assertEqual(first["expected_points"], second["expected_points"])
        self.assertLessEqual(first["points_p10"], first["points_p50"])
        self.assertLessEqual(first["points_p50"], first["points_p90"])
        self.assertGreater(first["probability_6_plus"], 0)
        self.assertEqual(len(first["points_samples"]), 1000)

    def test_player_attacking_involvement_drives_fpl_upside(self) -> None:
        ordinary = simulate_player_fixture(
            self.inputs(), simulations=3000, seed_parts=(101, 10)
        )
        explosive_inputs = {**self.inputs(), "xg_per_90": 1.2, "xa_per_90": 0.7}
        explosive = simulate_player_fixture(
            explosive_inputs, simulations=3000, seed_parts=(101, 10)
        )
        self.assertGreater(explosive["expected_points"], ordinary["expected_points"])
        self.assertGreater(explosive["probability_15_plus"], ordinary["probability_15_plus"])

    def test_component_simulation_is_auditable_and_deterministic(self) -> None:
        inputs = {
            **self.inputs(),
            "starter_minutes_mean": 82,
            "substitute_minutes_mean": 19,
        }
        first = simulate_component_player_fixture(
            inputs, simulations=2000, seed_parts=(200, 10)
        )
        second = simulate_component_player_fixture(
            inputs, simulations=2000, seed_parts=(200, 10)
        )
        self.assertEqual(first["expected_points"], second["expected_points"])
        self.assertAlmostEqual(
            sum(first["expected_points_components"].values()),
            first["expected_points"],
            places=8,
        )
        self.assertGreater(first["probability_60_plus"], 0)
        self.assertGreater(first["attacking_return_probability"], 0)

    def test_component_minutes_separate_starters_and_substitutes(self) -> None:
        feature = {
            "fixtures_6": 6,
            "start_rate_6": 0.5,
            "appearance_rate_6": 1.0,
            "starter_average_minutes_6": 84,
            "substitute_average_minutes_6": 18,
            "minutes_6": 300,
            "minutes_10": 500,
            "xg_per_90_6": 0.4,
            "xg_per_90_10": 0.3,
            "xa_per_90_6": 0.2,
            "xa_per_90_10": 0.15,
        }
        inputs = build_component_inputs(
            {**self.inputs(), "availability_probability": 1.0},
            feature,
            {
                "start_rate": 0.45,
                "appearance_rate": 0.65,
                "xg_per_90": 0.2,
                "xa_per_90": 0.16,
            },
        )
        self.assertGreater(inputs["starter_minutes_mean"], 70)
        self.assertLess(inputs["substitute_minutes_mean"], 30)
        self.assertGreater(
            inputs["appearance_probability"], inputs["start_probability"]
        )

    def test_defensive_contributions_are_scored_for_defenders(self) -> None:
        inputs = {
            **self.inputs(),
            "position": "DEF",
            "xg_per_90": 0,
            "xa_per_90": 0,
            "clean_sheet_probability": 0,
            "defensive_contribution_per_90": 20,
        }
        with_contributions = simulate_player_fixture(
            inputs, simulations=3000, seed_parts=(102, 10)
        )
        without_contributions = simulate_player_fixture(
            {**inputs, "defensive_contribution_per_90": 0},
            simulations=3000,
            seed_parts=(102, 10),
        )
        self.assertGreater(
            with_contributions["expected_points"], without_contributions["expected_points"]
        )


if __name__ == "__main__":
    unittest.main()
