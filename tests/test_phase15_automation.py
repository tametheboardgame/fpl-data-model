from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.evaluate_external_context import evaluate_external_signals
from src.fpl_chips import derive_chip_state
from src.finalise_external_context import finalise
from src.sync_api_football_context import (
    injury_availability,
    match_fixtures,
    match_player,
    signals_from_injuries,
    signals_from_lineup,
    sync,
)


class ApiFootballNormalisationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 15, 12, tzinfo=timezone.utc)
        self.player = {
            "player_id": "10", "team_id": "1", "team_name": "Man City",
            "first_name": "Erling", "second_name": "Haaland", "web_name": "Haaland",
        }
        self.fixture = {
            "fixture_id": "100", "gameweek": "1", "kickoff_time": "2026-08-15T15:00:00+00:00",
            "home_team_name": "Man City", "away_team_name": "Arsenal",
        }

    def test_matches_team_alias_player_and_fixture(self) -> None:
        self.assertEqual(
            match_player({"id": 99, "name": "E. Haaland"}, "Manchester City", [self.player]),
            self.player,
        )
        provider = [{
            "fixture": {"id": 500, "date": "2026-08-15T15:00:00+00:00"},
            "teams": {"home": {"name": "Manchester City"}, "away": {"name": "Arsenal"}},
        }]
        self.assertEqual(match_fixtures(provider, [self.fixture])[500], self.fixture)

    def test_normalises_injury_and_confirmed_lineup(self) -> None:
        injury_payload = {"response": [{
            "player": {"id": 99, "name": "E. Haaland", "reason": "Doubtful"},
            "team": {"name": "Manchester City"}, "fixture": {"id": 500},
        }]}
        injuries, misses = signals_from_injuries(
            injury_payload, [self.player], {500: self.fixture}, self.now
        )
        self.assertEqual(misses, 0)
        self.assertEqual(injuries[0]["value"], 0.25)
        lineup_payload = {"response": [{
            "team": {"name": "Manchester City"},
            "startXI": [{"player": {"id": 99, "name": "E. Haaland"}}],
            "substitutes": [],
        }]}
        lineups, misses = signals_from_lineup(
            lineup_payload, [self.player], self.fixture, 500, self.now
        )
        self.assertEqual(misses, 0)
        self.assertEqual(lineups[0]["signal_type"], "start_probability")
        self.assertEqual(lineups[0]["value"], 1)
        self.assertEqual(injury_availability("Suspended"), 0)

    def test_full_sync_with_fake_provider_preserves_raw_and_appends_signal(self) -> None:
        class FakeClient:
            max_requests = 8
            request_count = 0

            def get(inner, endpoint, **params):
                inner.request_count += 1
                if endpoint == "fixtures":
                    return {"response": [{
                        "fixture": {"id": 500, "date": "2026-08-15T15:00:00+00:00"},
                        "teams": {"home": {"name": "Manchester City"}, "away": {"name": "Arsenal"}},
                    }]}
                if endpoint == "injuries":
                    return {"response": [{
                        "player": {"id": 99, "name": "E. Haaland", "reason": "Doubtful"},
                        "team": {"name": "Manchester City"}, "fixture": {"id": 500},
                    }]}
                return {"response": []}

        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            (data / "chatgpt").mkdir(parents=True)
            (data / "context").mkdir(parents=True)
            for name, rows in (("players.csv", [self.player]), ("fixtures.csv", [self.fixture])):
                with (data / "chatgpt" / name).open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                    writer.writeheader(); writer.writerows(rows)
            (data / "chatgpt" / "manifest.json").write_text(
                json.dumps({"season": "2026/27"}), encoding="utf-8"
            )
            (data / "context" / "sources.json").write_text(json.dumps({
                "schema_version": "external-context-1.0", "sources": [{
                    "source_id": "api_football_injury", "reliability": 0.85,
                    "freshness_half_life_hours": 48,
                }, {
                    "source_id": "api_football_confirmed_lineup", "reliability": 0.98,
                    "freshness_half_life_hours": 8,
                }],
            }), encoding="utf-8")
            status = sync(data, FakeClient(), self.now)
            self.assertEqual(status["signals_appended"], 1)
            self.assertTrue((data / "raw/external/api-football/latest/injuries.json").is_file())
            self.assertIn("api-football-availability_probability", (data / "context/signals.jsonl").read_text())


class ProspectiveEvaluationTests(unittest.TestCase):
    def test_scores_only_pre_kickoff_signals(self) -> None:
        signals = [
            {"signal_id": "before", "source_id": "provider", "signal_type": "start_probability",
             "player_id": 10, "fixture_id": 100, "value": 0.8, "observed_at": "2026-08-15T14:00:00+00:00"},
            {"signal_id": "after", "source_id": "provider", "signal_type": "start_probability",
             "player_id": 10, "fixture_id": 100, "value": 1, "observed_at": "2026-08-15T16:00:00+00:00"},
        ]
        rows, summary = evaluate_external_signals(
            signals,
            [{"player_id": 10, "fixture": 100, "minutes": 90, "starts": 1}],
            [{"fixture_id": 100, "kickoff_time": "2026-08-15T15:00:00+00:00"}],
        )
        self.assertEqual([row["signal_id"] for row in rows], ["before"])
        self.assertAlmostEqual(rows[0]["error"], 0.04)
        self.assertEqual(summary["skipped_at_or_after_kickoff"], 1)


class ChipStateTests(unittest.TestCase):
    def test_derives_remaining_chips_and_refuses_unknown_rules(self) -> None:
        history = {"chips": [{"name": "freehit"}, {"name": "wildcard"}]}
        rules = {"seasons": {"2025/26": {"allowances": {
            "wildcard": 2, "freehit": 2, "bboost": 2, "3xc": 2,
        }}}}
        state = derive_chip_state(history, "2025/26", rules)
        self.assertEqual(state["chips"]["freehit"]["remaining"], 1)
        self.assertEqual(state["chips"]["bboost"]["remaining"], 2)
        self.assertEqual(
            derive_chip_state(history, "2026/27", rules)["status"],
            "rules_not_configured",
        )

    def test_finaliser_writes_evaluation_and_attaches_chip_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            (data / "chatgpt").mkdir(parents=True)
            (data / "context").mkdir(parents=True)
            (data / "context/sources.json").write_text(json.dumps({
                "schema_version": "external-context-1.0", "sources": [{
                    "source_id": "provider", "reliability": 1,
                    "freshness_half_life_hours": 24,
                }],
            }), encoding="utf-8")
            (data / "context/signals.jsonl").write_text("", encoding="utf-8")
            (data / "context/chip_rules.json").write_text(json.dumps({"seasons": {
                "2025/26": {"allowances": {"wildcard": 2, "freehit": 2, "bboost": 2, "3xc": 2}}
            }}), encoding="utf-8")
            (data / "chatgpt/manifest.json").write_text(json.dumps({"season": "2025/26"}), encoding="utf-8")
            (data / "chatgpt/manager_history.json").write_text(json.dumps({"chips": [{"name": "3xc"}]}), encoding="utf-8")
            (data / "chatgpt/fpl_decisions.json").write_text(json.dumps({"chip_indicators": {}}), encoding="utf-8")
            result = finalise(data)
            decision = json.loads((data / "chatgpt/fpl_decisions.json").read_text())
            self.assertEqual(result["chip_state"]["chips"]["3xc"]["remaining"], 1)
            self.assertEqual(decision["decision_version"], "fpl-decisions-1.1")
            self.assertTrue((data / "chatgpt/external_context_evaluation.json").is_file())


if __name__ == "__main__":
    unittest.main()
