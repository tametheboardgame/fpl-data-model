from __future__ import annotations

import unittest

from src.backtest_fpl_model import historical_defensive_contribution_rate
from src.sync_historical_fpl import DEFAULT_SEASONS, normalise_history_row


class Holdout2025SupportTests(unittest.TestCase):
    def test_historical_defensive_contributions_are_season_aware(self) -> None:
        self.assertEqual(historical_defensive_contribution_rate("2024-25", 14), 0.0)
        self.assertEqual(historical_defensive_contribution_rate("2025-26", 14), 14.0)
        self.assertEqual(historical_defensive_contribution_rate("2026-27", 9), 9.0)

    def test_historical_import_retains_defensive_contribution(self) -> None:
        row = normalise_history_row(
            {
                "GW": 1,
                "name": "Example Player",
                "position": "DEF",
                "defensive_contribution": "12",
            },
            "2025-26",
        )
        self.assertEqual(row["defensive_contribution"], "12")

    def test_default_history_now_includes_complete_2025_26_season(self) -> None:
        self.assertIn("2025-26", DEFAULT_SEASONS)


if __name__ == "__main__":
    unittest.main()
