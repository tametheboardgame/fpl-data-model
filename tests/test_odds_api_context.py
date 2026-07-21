from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.evaluate_external_context import evaluate_external_signals
from src.external_context import resolved_context
from src.fpl_decisions import decision_projection
from src.sync_odds_api_context import (
    market_consensus,
    match_events,
    signals_from_event,
    sync,
    total_goals_from_over_probability,
)


def provider_event() -> dict:
    return {
        "id": "market-100",
        "commence_time": "2026-08-15T15:00:00Z",
        "home_team": "Manchester City",
        "away_team": "Arsenal",
        "bookmakers": [
            {
                "key": "book-a",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Manchester City", "price": 1.80},
                            {"name": "Draw", "price": 4.00},
                            {"name": "Arsenal", "price": 4.50},
                        ],
                    },
                    {
                        "key": "totals",
                        "outcomes": [
                            {"name": "Over", "price": 1.80, "point": 2.5},
                            {"name": "Under", "price": 2.05, "point": 2.5},
                        ],
                    },
                ],
            },
            {
                "key": "book-b",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Manchester City", "price": 1.85},
                            {"name": "Draw", "price": 3.90},
                            {"name": "Arsenal", "price": 4.40},
                        ],
                    }
                ],
            },
        ],
    }


def fpl_fixture() -> dict:
    return {
        "fixture_id": "100",
        "gameweek": "1",
        "kickoff_time": "2026-08-15T15:00:00Z",
        "home_team_id": "1",
        "home_team": "Man City",
        "away_team_id": "2",
        "away_team": "Arsenal",
        "home_score": "2",
        "away_score": "0",
    }


class OddsNormalisationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 14, 12, tzinfo=timezone.utc)

    def test_removes_margin_and_fits_goal_rates(self) -> None:
        consensus = market_consensus(provider_event())
        self.assertIsNotNone(consensus)
        probabilities = consensus["outcome_probabilities"]
        self.assertAlmostEqual(sum(probabilities.values()), 1)
        self.assertGreater(probabilities["home"], probabilities["away"])
        self.assertGreater(consensus["home_expected_goals"], consensus["away_expected_goals"])
        self.assertEqual(consensus["total_goals_source"], "bookmaker_totals")
        self.assertAlmostEqual(
            total_goals_from_over_probability(0.5, 2.5), 2.674, delta=0.01
        )

    def test_matches_real_fpl_fixture_column_names(self) -> None:
        self.assertEqual(match_events([provider_event()], [fpl_fixture()]), {"market-100": fpl_fixture()})
        brighton_event = {
            "id": "market-101",
            "commence_time": "2026-08-15T15:00:00Z",
            "home_team": "Brighton and Hove Albion",
            "away_team": "Aston Villa",
        }
        brighton_fixture = {
            **fpl_fixture(),
            "fixture_id": "101",
            "home_team": "Brighton",
            "away_team": "Aston Villa",
        }
        self.assertEqual(
            match_events([brighton_event], [brighton_fixture]),
            {"market-101": brighton_fixture},
        )

    def test_creates_auditable_team_signals(self) -> None:
        signals = signals_from_event(provider_event(), fpl_fixture(), self.now)
        self.assertEqual(len(signals), 8)
        self.assertEqual({row["team_id"] for row in signals}, {1, 2})
        self.assertIn("clean_sheet_probability", {row["signal_type"] for row in signals})
        self.assertTrue(all(row["source_id"] == "odds_api_market" for row in signals))

    def test_team_context_is_only_a_tiebreaker(self) -> None:
        registry = {"sources": [{
            "source_id": "odds_api_market", "reliability": 1,
            "freshness_half_life_hours": 24,
        }]}
        signals = signals_from_event(provider_event(), fpl_fixture(), self.now)
        context = resolved_context(
            signals, registry, {"player_id": 10, "team_id": 1},
            {"gameweek": 1}, self.now,
        )
        projection = decision_projection(
            {"expected_points_next_1": 6, "expected_minutes_next_1": 90}, context
        )
        self.assertEqual(projection["decision_expected_points"], 6)
        self.assertGreater(projection["external_upside_score"], 0)


class OddsSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 14, 12, tzinfo=timezone.utc)

    def _write_data(self, root: Path, kickoff: datetime) -> None:
        (root / "chatgpt").mkdir(parents=True)
        (root / "context").mkdir(parents=True)
        fixture = {**fpl_fixture(), "kickoff_time": kickoff.isoformat()}
        with (root / "chatgpt/fixtures.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(fixture))
            writer.writeheader()
            writer.writerow(fixture)
        (root / "context/sources.json").write_text(json.dumps({
            "schema_version": "external-context-1.0",
            "sources": [{
                "source_id": "odds_api_market", "reliability": 0.9,
                "freshness_half_life_hours": 18,
            }],
        }), encoding="utf-8")
        (root / "context/signals.jsonl").write_text("", encoding="utf-8")

    def test_full_sync_preserves_raw_quota_and_signals(self) -> None:
        class FakeClient:
            usage = {
                "requests_remaining": 498,
                "requests_used": 2,
                "last_request_cost": 2,
            }

            def odds(self):
                return [provider_event()]

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_data(root, self.now + timedelta(days=1, hours=3))
            status = sync(root, FakeClient(), self.now)
            self.assertEqual(status["status"], "ok")
            self.assertEqual(status["request_cost"], 2)
            self.assertEqual(status["requests_remaining"], 498)
            self.assertEqual(status["signals_appended"], 8)
            self.assertTrue((root / "raw/external/odds-api/latest/odds.json").is_file())

    def test_scheduled_sync_does_not_spend_quota_without_future_fixtures(self) -> None:
        class FailIfCalled:
            def odds(self):
                raise AssertionError("Provider should not be called")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_data(root, self.now - timedelta(days=1))
            status = sync(root, FailIfCalled(), self.now)
            self.assertEqual(status["status"], "waiting_for_fpl_fixtures")
            self.assertEqual(status["request_cost"], 0)

    def test_no_request_check_preserves_last_known_quota(self) -> None:
        class FailIfCalled:
            def odds(self):
                raise AssertionError("Provider should not be called")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_data(root, self.now - timedelta(days=1))
            (root / "context/odds_api_status.json").write_text(json.dumps({
                "generated_at": "2026-08-13T12:00:00+00:00",
                "request_count": 1,
                "requests_used": 4,
                "requests_remaining": 496,
            }), encoding="utf-8")
            status = sync(root, FailIfCalled(), self.now)
            self.assertEqual(status["requests_remaining"], 496)
            self.assertEqual(status["last_provider_check_at"], "2026-08-13T12:00:00+00:00")

    def test_scores_team_markets_only_when_observed_pre_kickoff(self) -> None:
        before = signals_from_event(provider_event(), fpl_fixture(), self.now)[0]
        after = {**before, "signal_id": "after", "observed_at": "2026-08-15T16:00:00Z"}
        rows, summary = evaluate_external_signals(
            [before, after], [], [fpl_fixture()]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["team_id"], 1)
        self.assertEqual(rows[0]["actual"], 1)
        self.assertEqual(summary["skipped_at_or_after_kickoff"], 1)


if __name__ == "__main__":
    unittest.main()
