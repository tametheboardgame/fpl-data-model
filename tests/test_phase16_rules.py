from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.evaluate_external_context import evaluate_external_signals
from src.fpl_chips import derive_chip_state
from src.fpl_rules import apply_bonus_transition, load_scoring_rules
from src.fpl_transfers import derive_free_transfer_state, transfer_hit_cost


class ScoringRulesTests(unittest.TestCase):
    def test_2026_rules_are_season_aware_and_transition_fades(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "rules.json"
            path.write_text(json.dumps({"seasons": {"2026/27": {
                "version": "fpl-2026-27",
                "bonus_transition": {
                    "enabled": True,
                    "fade_after_player_fixtures": 8,
                    "position_multipliers": {"MID": 1.08},
                },
            }}}), encoding="utf-8")
            rules = load_scoring_rules(path, "2026/27")
        adjusted, first_multiplier = apply_bonus_transition(0.5, "MID", 0, rules)
        _, mature_multiplier = apply_bonus_transition(0.5, "MID", 8, rules)
        self.assertEqual(rules["version"], "fpl-2026-27")
        self.assertAlmostEqual(adjusted, 0.54)
        self.assertAlmostEqual(first_multiplier, 1.08)
        self.assertEqual(mature_multiplier, 1.0)

    def test_unknown_season_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            rules = load_scoring_rules(Path(temporary) / "missing.json", "2030/31")
        self.assertEqual(rules["status"], "rules_not_configured")


class ChipAndTransferRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = {
            "allowances": {"wildcard": 2, "freehit": 2, "bboost": 2, "3xc": 2},
            "periods": [
                {"id": "first_half", "start_gameweek": 1, "end_gameweek": 19,
                 "allowances": {"wildcard": 1, "freehit": 1, "bboost": 1, "3xc": 1}},
                {"id": "second_half", "start_gameweek": 20, "end_gameweek": 38,
                 "allowances": {"wildcard": 1, "freehit": 1, "bboost": 1, "3xc": 1}},
            ],
            "transfer_rules": {"maximum_free_transfers": 5, "hit_cost": 4},
        }

    def test_first_half_chip_expires_and_second_half_remains(self) -> None:
        state = derive_chip_state(
            {"chips": [{"name": "wildcard", "event": 5}]},
            "2026/27",
            {"seasons": {"2026/27": self.rules}},
            target_gameweek=20,
        )
        self.assertEqual(state["periods"][0]["status"], "expired")
        self.assertEqual(state["chips"]["wildcard"]["remaining"], 1)
        self.assertEqual(state["chips"]["freehit"]["remaining"], 1)

    def test_replays_free_transfers_and_prices_hits(self) -> None:
        history = {
            "current": [
                {"event": 1, "event_transfers": 0, "event_transfers_cost": 0},
                {"event": 2, "event_transfers": 0, "event_transfers_cost": 0},
                {"event": 3, "event_transfers": 2, "event_transfers_cost": 0},
            ],
            "chips": [],
        }
        state = derive_free_transfer_state(history, 4, self.rules)
        self.assertEqual(state["available"], 1)
        self.assertEqual(transfer_hit_cost(1, state["available"]), 0)
        self.assertEqual(transfer_hit_cost(2, state["available"]), 4)


class FinalityTests(unittest.TestCase):
    def test_external_signals_wait_for_finished_and_checked_event(self) -> None:
        signal = {
            "signal_id": "before", "source_id": "provider",
            "signal_type": "start_probability", "player_id": 10,
            "fixture_id": 100, "value": 0.8,
            "observed_at": "2026-08-15T14:00:00+00:00",
        }
        fixtures = [{
            "fixture_id": 100, "gameweek": 1,
            "kickoff_time": "2026-08-15T15:00:00+00:00",
        }]
        players = [{"player_id": 10, "fixture": 100, "minutes": 90, "starts": 1}]
        rows, summary = evaluate_external_signals(
            [signal], players, fixtures,
            [{"id": 1, "finished": True, "data_checked": False}],
        )
        self.assertEqual(rows, [])
        self.assertEqual(summary["skipped_unfinalised"], 1)
        rows, _ = evaluate_external_signals(
            [signal], players, fixtures,
            [{"id": 1, "finished": True, "data_checked": True}],
        )
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
