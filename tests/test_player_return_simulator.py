from __future__ import annotations

import unittest

from src.player_return_simulator import simulate_player_fixture


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
