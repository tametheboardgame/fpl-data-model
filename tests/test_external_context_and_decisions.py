from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.external_context import (
    ContextValidationError,
    context_summary,
    load_source_registry,
    read_context_signals,
    resolved_context,
)
from src.fpl_decisions import (
    build_decision_support,
    fixture_decision_projection,
    selection_risk_adjustment,
)


class ExternalContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 1, 10, tzinfo=timezone.utc)
        self.registry = {
            "schema_version": "external-context-1.0",
            "sources": [
                {
                    "source_id": "confirmed_lineup",
                    "reliability": 1.0,
                    "freshness_half_life_hours": 8,
                },
                {
                    "source_id": "market",
                    "reliability": 0.8,
                    "freshness_half_life_hours": 24,
                },
            ],
        }

    def test_resolves_only_matching_active_signals(self) -> None:
        signals = [
            {
                "signal_id": "lineup-10",
                "observed_at": self.now.isoformat(),
                "source_id": "confirmed_lineup",
                "signal_type": "start_probability",
                "value": 1,
                "confidence": 1,
                "player_id": 10,
                "fixture_id": 100,
                "status": "active",
            },
            {
                "signal_id": "wrong-player",
                "observed_at": self.now.isoformat(),
                "source_id": "market",
                "signal_type": "anytime_goal_probability",
                "value": 0.5,
                "confidence": 1,
                "player_id": 11,
                "fixture_id": 100,
                "status": "active",
            },
            {
                "signal_id": "expired",
                "observed_at": (self.now - timedelta(days=2)).isoformat(),
                "source_id": "market",
                "signal_type": "expected_minutes",
                "value": 20,
                "confidence": 1,
                "player_id": 10,
                "fixture_id": 100,
                "expires_at": (self.now - timedelta(hours=1)).isoformat(),
                "status": "active",
            },
        ]
        result = resolved_context(
            signals,
            self.registry,
            {"player_id": 10, "team_id": 1},
            {"fixture_id": 100, "gameweek": 1},
            self.now,
        )
        self.assertEqual(result["signal_count"], 1)
        self.assertEqual(result["signal_ids"], ["lineup-10"])
        self.assertEqual(result["values"]["start_probability"], 1)

    def test_player_signal_can_resolve_at_horizon_without_fixture_id(self) -> None:
        signal = {
            "signal_id": "lineup-10",
            "observed_at": self.now.isoformat(),
            "source_id": "confirmed_lineup",
            "signal_type": "start_probability",
            "value": 1,
            "confidence": 1,
            "player_id": 10,
            "fixture_id": 100,
            "gameweek": 1,
            "status": "active",
        }
        result = resolved_context(
            [signal],
            self.registry,
            {"player_id": 10, "team_id": 1},
            {"gameweek": 1},
            self.now,
        )
        self.assertEqual(result["signal_ids"], ["lineup-10"])

    def test_only_latest_snapshot_from_same_source_affects_decision(self) -> None:
        signals = [
            {
                "signal_id": "old", "observed_at": (self.now - timedelta(hours=1)).isoformat(),
                "source_id": "market", "signal_type": "start_probability", "value": 0,
                "player_id": 10, "fixture_id": 100, "status": "active",
            },
            {
                "signal_id": "new", "observed_at": self.now.isoformat(),
                "source_id": "market", "signal_type": "start_probability", "value": 1,
                "player_id": 10, "fixture_id": 100, "status": "active",
            },
        ]
        result = resolved_context(
            signals, self.registry, {"player_id": 10, "team_id": 1},
            {"fixture_id": 100}, self.now,
        )
        self.assertEqual(result["signal_ids"], ["new"])
        self.assertEqual(result["values"]["start_probability"], 1)
        self.assertEqual(result["signals"][0]["state"], "superseded")

    def test_fixture_only_signal_does_not_leak_without_fixture_context(self) -> None:
        signal = {
            "signal_id": "fixture-only",
            "observed_at": self.now.isoformat(),
            "source_id": "confirmed_lineup",
            "signal_type": "clean_sheet_probability",
            "value": 0.8,
            "confidence": 1,
            "fixture_id": 100,
            "status": "active",
        }
        result = resolved_context(
            [signal],
            self.registry,
            {"player_id": 10, "team_id": 1},
            {"gameweek": 1},
            self.now,
        )
        self.assertEqual(result["signal_count"], 0)

    def test_validates_append_only_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources = root / "sources.json"
            signals = root / "signals.jsonl"
            sources.write_text(json.dumps(self.registry), encoding="utf-8")
            signals.write_text(
                json.dumps(
                    {
                        "signal_id": "market-10",
                        "observed_at": self.now.isoformat(),
                        "source_id": "market",
                        "signal_type": "anytime_goal_probability",
                        "value": 0.42,
                        "confidence": 0.9,
                        "player_id": 10,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            registry = load_source_registry(sources)
            rows = read_context_signals(signals, registry)
            self.assertEqual(len(rows), 1)
            self.assertEqual(context_summary(rows, registry, self.now.isoformat())["active_signal_rows"], 1)

    def test_rejects_unregistered_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "signals.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "signal_id": "bad",
                        "observed_at": self.now.isoformat(),
                        "source_id": "unknown",
                        "signal_type": "start_probability",
                        "value": 1,
                        "player_id": 10,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ContextValidationError):
                read_context_signals(path, self.registry)


class DecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 1, 10, tzinfo=timezone.utc)
        self.registry = {
            "schema_version": "external-context-1.0",
            "sources": [
                {
                    "source_id": "confirmed_lineup",
                    "reliability": 1.0,
                    "freshness_half_life_hours": 8,
                }
            ],
        }

    def test_builds_lineup_captain_transfers_and_differentials(self) -> None:
        positions = (
            ["Goalkeeper"] * 2
            + ["Defender"] * 5
            + ["Midfielder"] * 5
            + ["Forward"] * 3
        )
        horizons = []
        players = []
        squad = []
        for index, position in enumerate(positions, start=1):
            horizons.append(
                {
                    "model_version": "player-ensemble-1.0",
                    "player_id": index,
                    "web_name": f"Player {index}",
                    "team_id": (index % 10) + 1,
                    "team_name": f"Club {(index % 10) + 1}",
                    "position": position,
                    "price": 5.0,
                    "expected_points_next_1": 3 + index / 10,
                    "expected_points_next_3": 9 + index / 10,
                    "expected_minutes_next_1": 80,
                    "points_p90_next_1": 8 + index / 10,
                    "probability_10_plus_next_1": index / 100,
                    "probability_15_plus_next_1": index / 200,
                }
            )
            players.append(
                {
                    "player_id": index,
                    "team_id": (index % 10) + 1,
                    "selected_by_percent": "12.0",
                }
            )
            squad.append({"player_id": index, "selling_price": 50})
        horizons.append(
            {
                "model_version": "player-ensemble-1.0",
                "player_id": 99,
                "web_name": "Differential",
                "team_id": 20,
                "team_name": "Upside FC",
                "position": "Forward",
                "price": 5.0,
                "expected_points_next_1": 8,
                "expected_points_next_3": 22,
                "expected_minutes_next_1": 90,
                "points_p90_next_1": 15,
                "probability_10_plus_next_1": 0.35,
                "probability_15_plus_next_1": 0.12,
            }
        )
        players.append(
            {"player_id": 99, "team_id": 20, "selected_by_percent": "4.2"}
        )
        context_signals = [
            {
                "signal_id": "market-99",
                "observed_at": self.now.isoformat(),
                "source_id": "confirmed_lineup",
                "signal_type": "anytime_goal_probability",
                "value": 0.6,
                "confidence": 1,
                "player_id": 99,
                "gameweek": 1,
                "status": "active",
            }
        ]
        decision = build_decision_support(
            horizons,
            players,
            {
                "team_id": 6435140,
                "available": True,
                "entry_history": {"bank": 0},
                "squad": squad,
            },
            {"next": {"id": 1}},
            context_signals,
            self.registry,
            self.now.isoformat(),
        )
        self.assertEqual(decision["status"], "ready")
        self.assertEqual(len(decision["recommended_lineup"]), 11)
        self.assertIsNotNone(decision["captaincy"]["captain"])
        self.assertEqual(decision["differentials"][0]["player_id"], 99)
        self.assertGreater(
            decision["differentials"][0]["external_upside_score"], 0
        )
        self.assertTrue(
            any(item["buy"]["player_id"] == 99 for item in decision["transfer_shortlist"])
        )

    def test_waits_cleanly_without_future_fixtures(self) -> None:
        decision = build_decision_support(
            [],
            [],
            {"team_id": 6435140, "available": True, "squad": []},
            {"next": None},
            [],
            self.registry,
            self.now.isoformat(),
        )
        self.assertEqual(decision["status"], "waiting_for_future_fixtures")
        self.assertEqual(decision["recommended_lineup"], [])
        self.assertIsNone(decision["captaincy"]["captain"])
        self.assertEqual(decision["transfer_shortlist"], [])

    def test_selection_risk_penalises_unproven_minutes_after_gameweek_one(self) -> None:
        adjustment = selection_risk_adjustment(
            {
                "position": "Midfielder",
                "starts": 0,
                "minutes": 25,
                "status": "a",
            },
            {
                "ensemble_status": "recommended_for_live_promotion",
                "ensemble_point_weight": 0.2,
                "expected_minutes_next_1": 81,
                "control_expected_points_next_1": 5.5,
                "component_expected_points_next_1": 3.5,
                "points_p90_next_1": 9,
                "probability_10_plus_next_1": 0.15,
                "probability_15_plus_next_1": 0.04,
            },
            {"decision_expected_points": 5.0},
            target_gameweek=2,
        )
        self.assertGreater(adjustment["minutes_risk_penalty"], 0)
        self.assertGreater(adjustment["model_disagreement_penalty"], 0)
        self.assertLess(adjustment["selection_expected_points"], 5.0)
        self.assertIn("observed usage", adjustment["selection_risk_reasons"][0])

    def test_role_supported_component_minutes_gap_is_not_double_penalised(self) -> None:
        horizon = {
            "ensemble_status": "recommended_for_live_promotion",
            "ensemble_point_weight": 0.2,
            "expected_minutes_next_1": 81,
            "component_expected_minutes_next_1": 50,
            "control_expected_points_next_1": 6.0,
            "component_expected_points_next_1": 3.8,
            "points_p90_next_1": 11,
            "probability_10_plus_next_1": 0.2,
            "probability_15_plus_next_1": 0.05,
        }
        supported = selection_risk_adjustment(
            {"position": "Forward", "starts": 2, "minutes": 180, "status": "a"},
            horizon,
            {"decision_expected_points": 6.4, "market_adjustment_points": 0.9},
            target_gameweek=3,
        )
        self.assertGreater(supported["role_supported_disagreement"], 2.0)
        self.assertLess(supported["model_disagreement_penalty"], 0.05)
        self.assertGreater(supported["selection_expected_points"], 6.35)

        unsupported_market = selection_risk_adjustment(
            {"position": "Forward", "starts": 2, "minutes": 180, "status": "a"},
            horizon,
            {"decision_expected_points": 6.4, "market_adjustment_points": -0.2},
            target_gameweek=3,
        )
        self.assertEqual(unsupported_market["role_supported_disagreement"], 0)
        self.assertGreater(unsupported_market["model_disagreement_penalty"], 0.5)

    def test_role_disagreement_relief_requires_proven_current_usage(self) -> None:
        adjustment = selection_risk_adjustment(
            {"position": "Forward", "starts": 0, "minutes": 30, "status": "a"},
            {
                "ensemble_status": "recommended_for_live_promotion",
                "ensemble_point_weight": 0.2,
                "expected_minutes_next_1": 81,
                "component_expected_minutes_next_1": 50,
                "control_expected_points_next_1": 6.0,
                "component_expected_points_next_1": 3.8,
                "points_p90_next_1": 11,
                "probability_10_plus_next_1": 0.2,
                "probability_15_plus_next_1": 0.05,
            },
            {"decision_expected_points": 6.4, "market_adjustment_points": 0.9},
            target_gameweek=3,
        )
        self.assertEqual(adjustment["role_supported_disagreement"], 0)
        self.assertGreater(adjustment["minutes_risk_penalty"], 0)
        self.assertGreater(adjustment["model_disagreement_penalty"], 0.5)

    def test_market_context_adjusts_relevant_expected_point_components(self) -> None:
        context = {
            "signal_count": 2,
            "signal_ids": ["market-xg", "market-cs"],
            "source_ids": ["market"],
            "values": {
                "team_expected_goals": 1.8,
                "clean_sheet_probability": 0.2,
            },
            "strengths": {
                "team_expected_goals": 1.0,
                "clean_sheet_probability": 1.0,
            },
        }
        defender = fixture_decision_projection(
            {
                "fixture_id": 100,
                "position": "Defender",
                "expected_points": 4.0,
                "expected_minutes": 90,
                "appearance_probability": 1.0,
                "expected_goals": 0.1,
                "expected_assists": 0.1,
                "clean_sheet_probability": 0.4,
                "component_clean_sheet_points": 1.6,
                "model_team_expected_goals": 1.2,
            },
            context,
        )
        forward = fixture_decision_projection(
            {
                "fixture_id": 100,
                "position": "Forward",
                "expected_points": 4.0,
                "expected_minutes": 90,
                "appearance_probability": 1.0,
                "expected_goals": 0.5,
                "expected_assists": 0.1,
                "clean_sheet_probability": 0.4,
                "model_team_expected_goals": 1.2,
            },
            context,
        )
        self.assertLess(defender["decision_expected_points"], 4.0)
        self.assertGreater(forward["decision_expected_points"], 4.0)
        self.assertLess(
            defender["market_adjustment_components"]["clean_sheet_market"],
            0,
        )
        self.assertGreater(
            forward["market_adjustment_components"]["team_attack_market"],
            0,
        )


if __name__ == "__main__":
    unittest.main()
