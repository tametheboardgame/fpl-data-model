from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.external_context import integer, number, parse_time


EVALUATION_VERSION = "external-context-evaluation-1.0"


def _actual_value(signal_type: str, row: dict[str, Any]) -> float | None:
    minutes = number(row.get("minutes"))
    if signal_type == "availability_probability":
        return float(minutes > 0)
    if signal_type == "start_probability":
        if row.get("starts") not in {None, ""}:
            return float(number(row.get("starts")) > 0)
        return float(minutes >= 60)
    if signal_type == "expected_minutes":
        return minutes
    if signal_type == "anytime_goal_probability":
        return float(number(row.get("goals_scored")) > 0)
    if signal_type == "clean_sheet_probability":
        return float(number(row.get("clean_sheets")) > 0)
    return None


def _team_actual_value(
    signal_type: str, team_id: int, fixture: dict[str, Any]
) -> float | None:
    home_id = integer(fixture.get("home_team_id"))
    away_id = integer(fixture.get("away_team_id"))
    if team_id not in {home_id, away_id}:
        return None
    home_score = fixture.get("home_score")
    away_score = fixture.get("away_score")
    if home_score in {None, ""} or away_score in {None, ""}:
        return None
    own_score, opponent_score = (
        (number(home_score), number(away_score))
        if team_id == home_id
        else (number(away_score), number(home_score))
    )
    if signal_type == "match_win_probability":
        return float(own_score > opponent_score)
    if signal_type == "team_score_probability":
        return float(own_score > 0)
    if signal_type == "clean_sheet_probability":
        return float(opponent_score == 0)
    if signal_type == "team_expected_goals":
        return own_score
    return None


def evaluate_external_signals(
    signals: list[dict[str, Any]],
    player_fixtures: list[dict[str, Any]],
    fixtures: list[dict[str, Any]],
    gameweeks: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    actual = {
        (integer(row.get("player_id")), integer(row.get("fixture"))): row
        for row in player_fixtures
        if integer(row.get("player_id")) and integer(row.get("fixture"))
    }
    kickoff_by_fixture = {
        integer(row.get("fixture_id")): parse_time(row.get("kickoff_time"))
        for row in fixtures
        if integer(row.get("fixture_id"))
    }
    fixture_by_id = {
        integer(row.get("fixture_id")): row
        for row in fixtures
        if integer(row.get("fixture_id"))
    }
    gameweek_by_fixture = {
        integer(row.get("fixture_id")): integer(row.get("gameweek"))
        for row in fixtures
        if integer(row.get("fixture_id"))
    }
    finality = {
        integer(row.get("id")): (
            str(row.get("finished")).strip().lower() in {"true", "1", "yes"}
            and str(row.get("data_checked")).strip().lower() in {"true", "1", "yes"}
        )
        for row in (gameweeks or [])
        if integer(row.get("id"))
    }
    evaluated: list[dict[str, Any]] = []
    skipped_after_kickoff = 0
    skipped_unfinalised = 0
    for signal in signals:
        player_id = integer(signal.get("player_id"))
        team_id = integer(signal.get("team_id"))
        fixture_id = integer(signal.get("fixture_id"))
        gameweek = gameweek_by_fixture.get(fixture_id)
        if gameweeks is not None and not finality.get(gameweek, False):
            skipped_unfinalised += 1
            continue
        row = actual.get((player_id, fixture_id))
        observed = parse_time(signal.get("observed_at"))
        kickoff = kickoff_by_fixture.get(fixture_id)
        if not observed or not kickoff or observed >= kickoff:
            skipped_after_kickoff += 1
            continue
        signal_type = str(signal.get("signal_type"))
        target = _actual_value(signal_type, row) if row else None
        if target is None and team_id:
            target = _team_actual_value(
                signal_type, team_id, fixture_by_id.get(fixture_id, {})
            )
        if target is None:
            continue
        prediction = number(signal.get("value"))
        probability = str(signal.get("signal_type")) != "expected_minutes"
        error = (prediction - target) ** 2 if probability else abs(prediction - target)
        evaluated.append(
            {
                "signal_id": signal.get("signal_id"),
                "source_id": signal.get("source_id"),
                "signal_type": signal.get("signal_type"),
                "player_id": player_id,
                "team_id": team_id,
                "fixture_id": fixture_id,
                "observed_at": signal.get("observed_at"),
                "kickoff_time": kickoff.isoformat(),
                "predicted": round(prediction, 6),
                "actual": round(target, 6),
                "metric": "brier_score" if probability else "mean_absolute_error",
                "error": round(error, 6),
                "leakage_safe": True,
            }
        )

    groups: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for row in evaluated:
        groups[(str(row["source_id"]), str(row["signal_type"]), str(row["metric"]))].append(
            number(row["error"])
        )
    by_source_and_type = [
        {
            "source_id": source_id,
            "signal_type": signal_type,
            "metric": metric,
            "evaluated_signals": len(errors),
            "score": round(sum(errors) / len(errors), 6),
        }
        for (source_id, signal_type, metric), errors in sorted(groups.items())
    ]
    summary = {
        "evaluation_version": EVALUATION_VERSION,
        "evaluated_signals": len(evaluated),
        "skipped_at_or_after_kickoff": skipped_after_kickoff,
        "skipped_unfinalised": skipped_unfinalised,
        "by_source_and_type": by_source_and_type,
        "principle": (
            "Only signals timestamped before kickoff are scored, and production "
            "evaluation waits for finished=true and data_checked=true."
        ),
    }
    return evaluated, summary


def write_external_evaluation(
    output_dir: Path, rows: list[dict[str, Any]], summary: dict[str, Any]
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fields = [
        "signal_id", "source_id", "signal_type", "player_id", "team_id", "fixture_id",
        "observed_at", "kickoff_time", "predicted", "actual", "metric", "error",
        "leakage_safe",
    ]
    with (output_dir / "external_context_accuracy.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        **summary,
    }
    (output_dir / "external_context_evaluation.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
