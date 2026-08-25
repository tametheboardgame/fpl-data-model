from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.player_return_simulator import (
    DEFAULT_SIMULATIONS,
    SCORING_RULES_VERSION,
    percentile,
    simulate_player_fixture,
)
from src.component_player_simulator import (
    COMPONENT_MODEL_VERSION,
    build_component_inputs,
    simulate_component_player_fixture,
)
from src.scouting_observations import SIGNAL_FIELDS, qualitative_adjustment, read_observations
from src.external_context import (
    context_summary,
    load_source_registry,
    read_context_signals,
    write_signal_csv,
)
from src.fpl_decisions import build_decision_support, write_decision_support
from src.fpl_finality import gameweek_finality as official_gameweek_finality
from src.fpl_gameweek_operations import update_gameweek_operations
from src.fpl_prospective import update_prospective_evaluation
from src.fpl_rules import apply_bonus_transition, load_scoring_rules
from src.update_fpl_data import utc_now, write_csv, write_json


MODEL_VERSION = "player-sim-2.0"
ENSEMBLE_MODEL_VERSION = "player-ensemble-1.0"
DEFAULT_ENSEMBLE_CONFIG = {
    "enabled": True,
    "status": "recommended_for_live_promotion",
    "model_version": ENSEMBLE_MODEL_VERSION,
    "point_weight": 0.2,
    "probability_weights": {"6": 0.5, "10": 0.4, "15": 1.0},
}
FORECAST_GAMEWEEKS = 6
MODEL_DATASETS = [
    "player_rolling_features.csv",
    "team_rolling_features.csv",
    "player_projections.csv",
    "player_projection_horizons.csv",
    "projection_summary.json",
    "prediction_index.json",
    "prediction_accuracy.csv",
    "prediction_evaluation.json",
    "scouting_observations.csv",
    "qualitative_signal_summary.json",
    "external_context_signals.csv",
    "external_context_summary.json",
    "fpl_decisions.json",
    "initial_squad_plan.json",
    "launch_validation.json",
    "prospective_index.json",
    "prospective_evaluation.csv",
    "prospective_evaluation.json",
    "gameweek_report.json",
    "gameweek_report.md",
]
PROJECTION_FIELDS = [
    "model_version",
    "control_model_version",
    "challenger_model_version",
    "ensemble_status",
    "ensemble_point_weight",
    "ensemble_probability_6_plus_weight",
    "ensemble_probability_10_plus_weight",
    "ensemble_probability_15_plus_weight",
    "scoring_rules_version",
    "projection_evidence_source",
    "previous_season",
    "previous_season_minutes",
    "bonus_transition_multiplier",
    "simulation_count",
    "gameweek",
    "fixture_id",
    "kickoff_time",
    "player_id",
    "player_code",
    "web_name",
    "team_id",
    "team_name",
    "position",
    "price",
    "opponent_team_id",
    "opponent",
    "is_home",
    "difficulty",
    "availability_probability",
    "appearance_probability",
    "start_probability",
    "quantitative_expected_minutes",
    "qualitative_minutes_delta",
    "expected_minutes",
    "minutes_p10",
    "minutes_p50",
    "minutes_p90",
    "expected_goals",
    "expected_assists",
    "clean_sheet_probability",
    "quantitative_expected_points",
    "qualitative_expected_points_delta",
    "expected_points",
    "points_p10",
    "points_p50",
    "points_p90",
    "probability_6_plus",
    "probability_10_plus",
    "probability_15_plus",
    "probability_3_or_fewer",
    "control_quantitative_expected_points",
    "control_qualitative_expected_points_delta",
    "control_expected_points",
    "control_points_p10",
    "control_points_p50",
    "control_points_p90",
    "control_probability_6_plus",
    "control_probability_10_plus",
    "control_probability_15_plus",
    "control_probability_3_or_fewer",
    "component_quantitative_expected_points",
    "component_qualitative_expected_points_delta",
    "component_expected_points",
    "component_expected_minutes",
    "component_probability_start",
    "component_probability_60_plus",
    "component_expected_goals",
    "component_expected_assists",
    "component_expected_saves",
    "component_goal_return_probability",
    "component_assist_return_probability",
    "component_attacking_return_probability",
    "component_clean_sheet_return_probability",
    "component_points_p10",
    "component_points_p50",
    "component_points_p90",
    "component_probability_6_plus",
    "component_probability_10_plus",
    "component_probability_15_plus",
    "component_probability_3_or_fewer",
    "component_appearance_points",
    "component_goal_points",
    "component_assist_points",
    "component_clean_sheet_points",
    "component_goals_conceded_points",
    "component_save_points",
    "component_penalty_save_points",
    "component_defensive_contribution_points",
    "component_bonus_points",
    "component_discipline_points",
    "qualitative_observation_count",
    "qualitative_observation_ids",
    "qualitative_confidence",
    "qualitative_attack_multiplier",
    "qualitative_attacking_role",
    "qualitative_movement_sharpness",
    "qualitative_fitness_energy",
    "qualitative_minutes_security",
    "qualitative_set_piece_role",
    "qualitative_team_reliance",
    "qualitative_tactical_fit",
]
POSITION_CODES = {
    "Goalkeeper": "GK",
    "Defender": "DEF",
    "Midfielder": "MID",
    "Forward": "FWD",
    "GK": "GK",
    "DEF": "DEF",
    "MID": "MID",
    "FWD": "FWD",
}
FALLBACK_PRIORS = {
    "GK": {"start_rate": 0.55, "appearance_rate": 0.58, "average_minutes_per_fixture": 50, "points_per_90": 4.0, "xg_per_90": 0, "xa_per_90": 0.01, "saves_per_90": 3.0, "bonus_per_90": 0.25, "defensive_contribution_per_90": 0, "yellow_cards_per_90": 0.05},
    "DEF": {"start_rate": 0.48, "appearance_rate": 0.62, "average_minutes_per_fixture": 48, "points_per_90": 3.8, "xg_per_90": 0.05, "xa_per_90": 0.07, "saves_per_90": 0, "bonus_per_90": 0.18, "defensive_contribution_per_90": 8.0, "yellow_cards_per_90": 0.16},
    "MID": {"start_rate": 0.45, "appearance_rate": 0.65, "average_minutes_per_fixture": 47, "points_per_90": 4.2, "xg_per_90": 0.20, "xa_per_90": 0.16, "saves_per_90": 0, "bonus_per_90": 0.22, "defensive_contribution_per_90": 6.0, "yellow_cards_per_90": 0.15},
    "FWD": {"start_rate": 0.43, "appearance_rate": 0.62, "average_minutes_per_fixture": 45, "points_per_90": 4.3, "xg_per_90": 0.36, "xa_per_90": 0.12, "saves_per_90": 0, "bonus_per_90": 0.25, "defensive_contribution_per_90": 3.0, "yellow_cards_per_90": 0.12},
}


def number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def integer(value: Any) -> int:
    return int(number(value))


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_ensemble_config(path: Path) -> dict[str, Any]:
    disabled = {
        "enabled": False,
        "status": "candidate_not_available",
        "model_version": MODEL_VERSION,
        "point_weight": 0.0,
        "probability_weights": {"6": 0.0, "10": 0.0, "15": 0.0},
    }
    if not path.is_file():
        return disabled
    try:
        candidate = json.loads(path.read_text(encoding="utf-8"))
        if candidate.get("status") != "recommended_for_live_promotion":
            return {**disabled, "status": str(candidate.get("status") or "not_recommended")}
        selection = candidate.get("assessment", {}).get("selection", {})
        point_weight = max(0.0, min(1.0, number(selection.get("selected_point_weight"))))
        probability_weights = {
            str(threshold): max(
                0.0,
                min(
                    1.0,
                    number(
                        selection.get("selected_probability_weights", {}).get(
                            str(threshold)
                        )
                    ),
                ),
            )
            for threshold in (6, 10, 15)
        }
        return {
            "enabled": True,
            "status": "recommended_for_live_promotion",
            "model_version": ENSEMBLE_MODEL_VERSION,
            "point_weight": point_weight,
            "probability_weights": probability_weights,
        }
    except (json.JSONDecodeError, OSError, TypeError, AttributeError):
        return {**disabled, "status": "candidate_assessment_unreadable"}


def ordered_fields(rows: list[dict[str, Any]], preferred: list[str]) -> list[str]:
    extras = sorted({key for row in rows for key in row}.difference(preferred))
    return preferred + extras


def recent_metrics(rows: list[dict[str, Any]], window: int) -> dict[str, Any]:
    selected = rows[-window:]
    fixture_count = len(selected)
    minutes_values = [number(row.get("minutes")) for row in selected]
    minutes = sum(minutes_values)
    appearances = sum(value > 0 for value in minutes_values)
    starts = sum(
        number(row.get("starts")) > 0 or number(row.get("minutes")) >= 60
        for row in selected
    )
    starter_minutes = [
        number(row.get("minutes"))
        for row in selected
        if number(row.get("starts")) > 0 or number(row.get("minutes")) >= 60
    ]
    substitute_minutes = [
        number(row.get("minutes"))
        for row in selected
        if 0 < number(row.get("minutes")) < 60
        and not number(row.get("starts")) > 0
    ]
    sixty_plus = sum(number(row.get("minutes")) >= 60 for row in selected)

    def total(field: str) -> float:
        return sum(number(row.get(field)) for row in selected)

    per90 = 90 / minutes if minutes else 0
    return {
        f"fixtures_{window}": fixture_count,
        f"appearance_rate_{window}": round(appearances / fixture_count, 4) if fixture_count else 0,
        f"start_rate_{window}": round(starts / fixture_count, 4) if fixture_count else 0,
        f"average_minutes_{window}": round(minutes / fixture_count, 2) if fixture_count else 0,
        f"average_minutes_when_appearing_{window}": round(minutes / appearances, 2) if appearances else 0,
        f"starter_average_minutes_{window}": round(statistics.fmean(starter_minutes), 2) if starter_minutes else 0,
        f"substitute_average_minutes_{window}": round(statistics.fmean(substitute_minutes), 2) if substitute_minutes else 0,
        f"sixty_plus_rate_{window}": round(sixty_plus / fixture_count, 4) if fixture_count else 0,
        f"minutes_standard_deviation_{window}": round(statistics.pstdev(minutes_values), 2) if len(minutes_values) > 1 else 0,
        f"minutes_{window}": round(minutes, 2),
        f"points_per_90_{window}": round(total("total_points") * per90, 4),
        f"xg_per_90_{window}": round(total("expected_goals") * per90, 4),
        f"xa_per_90_{window}": round(total("expected_assists") * per90, 4),
        f"xgi_per_90_{window}": round(total("expected_goal_involvements") * per90, 4),
        f"saves_per_90_{window}": round(total("saves") * per90, 4),
        f"bonus_per_90_{window}": round(total("bonus") * per90, 4),
        f"defensive_contribution_per_90_{window}": round(total("defensive_contribution") * per90, 4),
        f"yellow_cards_per_90_{window}": round(total("yellow_cards") * per90, 4),
        f"red_cards_per_90_{window}": round(total("red_cards") * per90, 4),
        f"own_goals_per_90_{window}": round(total("own_goals") * per90, 4),
        f"penalties_missed_per_90_{window}": round(total("penalties_missed") * per90, 4),
        f"penalties_saved_per_90_{window}": round(total("penalties_saved") * per90, 4),
        f"clean_sheet_rate_{window}": round(total("clean_sheets") / starts, 4) if starts else 0,
    }


def build_player_features(
    players: list[dict[str, Any]], fixture_history: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in fixture_history:
        by_player[integer(row.get("player_id"))].append(row)
    for rows in by_player.values():
        rows.sort(key=lambda row: (row.get("kickoff_time") or "", integer(row.get("fixture"))))

    features: list[dict[str, Any]] = []
    for player in players:
        player_id = integer(player.get("player_id"))
        history = by_player.get(player_id, [])
        row: dict[str, Any] = {
            "player_id": player_id,
            "player_code": player.get("player_code"),
            "web_name": player.get("web_name"),
            "team_id": integer(player.get("team_id")),
            "team_name": player.get("team_name"),
            "position": player.get("position"),
            "price": number(player.get("price")),
            "history_fixture_count": len(history),
            "last_fixture_time": history[-1].get("kickoff_time") if history else None,
        }
        for window in (3, 6, 10):
            row.update(recent_metrics(history, window))
        features.append(row)
    return features


def build_team_features(
    teams: list[dict[str, Any]],
    fixture_history: list[dict[str, Any]],
    fixtures: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    fixture_teams = {
        integer(row.get("fixture_id")): (
            integer(row.get("home_team_id")),
            integer(row.get("away_team_id")),
        )
        for row in fixtures or []
    }
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in fixture_history:
        fixture_id = integer(row.get("fixture"))
        home_team, away_team = fixture_teams.get(fixture_id, (0, 0))
        team_id = (
            home_team if truthy(row.get("was_home")) else away_team
        ) or integer(row.get("team_id"))
        if team_id and fixture_id:
            grouped[(team_id, fixture_id)].append(row)

    matches: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for (team_id, fixture_id), rows in grouped.items():
        sample = rows[0]
        was_home = truthy(sample.get("was_home"))
        home_score = number(sample.get("team_h_score"))
        away_score = number(sample.get("team_a_score"))
        xg_for = sum(number(row.get("expected_goals")) for row in rows)
        goalkeeper_xgc = [
            number(row.get("expected_goals_conceded"))
            for row in rows
            if str(row.get("position")) in {"Goalkeeper", "GK"}
            and number(row.get("minutes")) > 0
        ]
        xg_against = max(goalkeeper_xgc, default=max(
            (number(row.get("expected_goals_conceded")) for row in rows), default=0
        ))
        matches[team_id].append(
            {
                "fixture": fixture_id,
                "kickoff_time": sample.get("kickoff_time"),
                "xg_for": xg_for,
                "xg_against": xg_against,
                "goals_for": home_score if was_home else away_score,
                "goals_against": away_score if was_home else home_score,
            }
        )
    for rows in matches.values():
        rows.sort(key=lambda row: row.get("kickoff_time") or "")

    output: list[dict[str, Any]] = []
    for team in teams:
        team_id = integer(team.get("team_id"))
        row: dict[str, Any] = {
            "team_id": team_id,
            "team_code": team.get("team_code"),
            "team_name": team.get("name"),
        }
        history = matches.get(team_id, [])
        for window in (3, 6, 10):
            selected = history[-window:]
            count = len(selected)
            row[f"matches_{window}"] = count
            for field in ("xg_for", "xg_against", "goals_for", "goals_against"):
                row[f"{field}_per_match_{window}"] = round(
                    sum(number(item.get(field)) for item in selected) / count, 4
                ) if count else 0
            row[f"clean_sheet_rate_{window}"] = round(
                sum(number(item.get("goals_against")) == 0 for item in selected) / count, 4
            ) if count else 0
        output.append(row)
    return output


def load_priors(path: Path) -> dict[str, dict[str, Any]]:
    priors = {
        position: {**values, "position": position}
        for position, values in FALLBACK_PRIORS.items()
    }
    for row in read_csv(path):
        if row.get("season") == "ALL" and row.get("position") in priors:
            priors[row["position"]].update(row)
    return priors


def availability_probability(player: dict[str, Any]) -> float:
    chance = player.get("chance_of_playing_next_round")
    if chance not in {None, ""}:
        return max(0, min(1, number(chance) / 100))
    return {
        "a": 1.0,
        "d": 0.75,
        "i": 0.1,
        "s": 0.0,
        "u": 0.0,
        "n": 0.0,
    }.get(str(player.get("status") or "a"), 0.8)


def blended_rate(player_value: float, minutes: float, prior_value: float, prior_minutes: float = 720) -> float:
    weight = max(0, min(1, minutes / (minutes + prior_minutes)))
    return player_value * weight + prior_value * (1 - weight)


def latest_past_seasons(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    latest: dict[int, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: item.get("season_name") or ""):
        latest[integer(row.get("player_code"))] = row
    return latest


def _past_rate(past: dict[str, Any] | None, field: str) -> float:
    if not past:
        return 0.0
    minutes = number(past.get("minutes"))
    if minutes <= 0:
        return 0.0
    return number(past.get(field)) * 90 / minutes


def _player_prior_rate(
    past: dict[str, Any] | None,
    field: str,
    positional_prior: float,
    prior_minutes: float = 720,
) -> float:
    if not past or number(past.get("minutes")) <= 0:
        return positional_prior
    return blended_rate(
        _past_rate(past, field),
        number(past.get("minutes")),
        positional_prior,
        prior_minutes,
    )


def projection_inputs(
    player: dict[str, Any],
    feature: dict[str, Any],
    prior: dict[str, Any],
    past: dict[str, Any] | None,
) -> dict[str, Any]:
    availability = availability_probability(player)
    fixtures_6 = integer(feature.get("fixtures_6"))
    past_minutes = number((past or {}).get("minutes"))
    if past_minutes:
        past_average_minutes = min(90, past_minutes / 38)
        past_start_rate = min(1, number(past.get("starts")) / 38)
        past_appearance_rate = min(
            1,
            max(past_start_rate, past_minutes / (38 * 60)),
        )
    else:
        past_average_minutes = number(prior.get("average_minutes_per_fixture"))
        past_start_rate = number(prior.get("start_rate"))
        past_appearance_rate = number(prior.get("appearance_rate"))

    if fixtures_6:
        current_average_minutes = (
            0.7 * number(feature.get("average_minutes_6"))
            + 0.3 * number(feature.get("average_minutes_3"))
        )
        current_start_rate = (
            0.7 * number(feature.get("start_rate_6"))
            + 0.3 * number(feature.get("start_rate_3"))
        )
        current_appearance_rate = (
            0.7 * number(feature.get("appearance_rate_6"))
            + 0.3 * number(feature.get("appearance_rate_3"))
        )
        current_weight = min(1.0, fixtures_6 / 6)
        average_minutes = (
            current_weight * current_average_minutes
            + (1 - current_weight) * past_average_minutes
        )
        start_rate = (
            current_weight * current_start_rate
            + (1 - current_weight) * past_start_rate
        )
        appearance_rate = (
            current_weight * current_appearance_rate
            + (1 - current_weight) * past_appearance_rate
        )
        evidence_source = (
            "current_and_previous_season"
            if current_weight < 1 and past_minutes
            else "current_season"
        )
    else:
        average_minutes = past_average_minutes
        start_rate = past_start_rate
        appearance_rate = past_appearance_rate
        evidence_source = "previous_season" if past_minutes else "position_prior"

    minutes_10 = number(feature.get("minutes_10"))
    rate_specs = {
        "points_per_90": "total_points",
        "xg_per_90": "expected_goals",
        "xa_per_90": "expected_assists",
        "saves_per_90": "saves",
        "bonus_per_90": "bonus",
        "defensive_contribution_per_90": "defensive_contribution",
        "yellow_cards_per_90": "yellow_cards",
        "red_cards_per_90": "red_cards",
        "own_goals_per_90": "own_goals",
        "penalties_missed_per_90": "penalties_missed",
        "penalties_saved_per_90": "penalties_saved",
    }
    player_priors = {
        output_field: _player_prior_rate(
            past,
            past_field,
            number(prior.get(output_field)),
        )
        for output_field, past_field in rate_specs.items()
    }
    return {
        "projection_evidence_source": evidence_source,
        "previous_season": (past or {}).get("season_name"),
        "previous_season_minutes": past_minutes,
        "availability_probability": availability,
        "start_probability": max(0, min(1, availability * start_rate)),
        "appearance_probability": max(
            0,
            min(1, availability * max(start_rate, appearance_rate)),
        ),
        "expected_minutes": max(0, min(90, availability * average_minutes)),
        "minutes_deviation": max(
            6,
            number(feature.get("minutes_standard_deviation_6")),
        ),
        **{
            field: blended_rate(
                number(feature.get(f"{field}_10")),
                minutes_10,
                player_prior,
            )
            for field, player_prior in player_priors.items()
        },
    }


def clean_sheet_probability(
    difficulty: int,
    is_home: bool,
    team_feature: dict[str, Any] | None,
    opponent_feature: dict[str, Any] | None,
) -> float:
    default_lambda = {1: 0.65, 2: 0.9, 3: 1.2, 4: 1.55, 5: 2.0}.get(difficulty, 1.2)
    estimates = []
    if team_feature and number(team_feature.get("matches_6")):
        estimates.append(number(team_feature.get("xg_against_per_match_6")))
    if opponent_feature and number(opponent_feature.get("matches_6")):
        estimates.append(number(opponent_feature.get("xg_for_per_match_6")))
    expected_against = sum(estimates) / len(estimates) if estimates else default_lambda
    expected_against = 0.65 * expected_against + 0.35 * default_lambda
    expected_against *= 0.95 if is_home else 1.05
    return max(0.05, min(0.70, math.exp(-max(0.1, expected_against))))


def build_projections(
    players: list[dict[str, Any]],
    player_features: list[dict[str, Any]],
    team_features: list[dict[str, Any]],
    fixtures: list[dict[str, Any]],
    priors: dict[str, dict[str, Any]],
    past_seasons: list[dict[str, Any]],
    observations: list[dict[str, Any]] | None = None,
    simulations: int = DEFAULT_SIMULATIONS,
    ensemble_config: dict[str, Any] | None = None,
    scoring_rules: dict[str, Any] | None = None,
    target_gameweek: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    scoring_rules = scoring_rules or {"version": SCORING_RULES_VERSION}
    scoring_rules_version = str(scoring_rules.get("version") or SCORING_RULES_VERSION)
    feature_by_player = {integer(row.get("player_id")): row for row in player_features}
    feature_by_team = {integer(row.get("team_id")): row for row in team_features}
    past_by_code = latest_past_seasons(past_seasons)
    observations = observations or []
    ensemble_config = ensemble_config or DEFAULT_ENSEMBLE_CONFIG
    ensemble_point_weight = max(
        0.0, min(1.0, number(ensemble_config.get("point_weight")))
    )
    ensemble_probability_weights = {
        str(threshold): max(
            0.0,
            min(
                1.0,
                number(
                    ensemble_config.get("probability_weights", {}).get(
                        str(threshold)
                    )
                ),
            ),
        )
        for threshold in (6, 10, 15)
    }
    live_model_version = str(
        ensemble_config.get("model_version") or MODEL_VERSION
    )
    future = [
        row
        for row in fixtures
        if not truthy(row.get("finished"))
        and integer(row.get("gameweek"))
        and (
            not target_gameweek
            or integer(row.get("gameweek")) >= integer(target_gameweek)
        )
    ]
    future.sort(key=lambda row: (integer(row.get("gameweek")), row.get("kickoff_time") or ""))
    forecast_gameweeks = sorted({integer(row.get("gameweek")) for row in future})[
        :FORECAST_GAMEWEEKS
    ]
    future = [row for row in future if integer(row.get("gameweek")) in forecast_gameweeks]

    projections: list[dict[str, Any]] = []
    samples_by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for player in players:
        player_id = integer(player.get("player_id"))
        team_id = integer(player.get("team_id"))
        position = POSITION_CODES.get(str(player.get("position")), "MID")
        prior = priors.get(position, FALLBACK_PRIORS[position])
        player_feature = feature_by_player.get(player_id, {})
        inputs = projection_inputs(
            player,
            player_feature,
            prior,
            past_by_code.get(integer(player.get("player_code"))),
        )
        inputs["bonus_per_90"], bonus_transition_multiplier = apply_bonus_transition(
            number(inputs.get("bonus_per_90")),
            position,
            integer(player_feature.get("fixtures_6")),
            scoring_rules,
        )
        inputs["bonus_transition_multiplier"] = bonus_transition_multiplier
        for fixture in future:
            home_team = integer(fixture.get("home_team_id"))
            away_team = integer(fixture.get("away_team_id"))
            if team_id not in {home_team, away_team}:
                continue
            is_home = team_id == home_team
            opponent_id = away_team if is_home else home_team
            difficulty = integer(
                fixture.get("home_difficulty") if is_home else fixture.get("away_difficulty")
            ) or 3
            attack_factor = max(
                0.60,
                min(1.45, 1 + (3 - difficulty) * 0.12 + (0.04 if is_home else -0.02)),
            )
            cs_probability = clean_sheet_probability(
                difficulty,
                is_home,
                feature_by_team.get(team_id),
                feature_by_team.get(opponent_id),
            )
            qualitative = qualitative_adjustment(
                observations, player, str(fixture.get("kickoff_time") or utc_now())
            )
            base_simulation_inputs = {
                **inputs,
                "position": position,
                "clean_sheet_probability": cs_probability,
                "xg_per_90": inputs["xg_per_90"] * attack_factor,
                "xa_per_90": inputs["xa_per_90"] * attack_factor,
            }
            adjusted_simulation_inputs = {
                **base_simulation_inputs,
                "expected_minutes": max(
                    0, min(90, inputs["expected_minutes"] + qualitative["minutes_delta"])
                ),
                "xg_per_90": base_simulation_inputs["xg_per_90"]
                * qualitative["attack_multiplier"],
                "xa_per_90": base_simulation_inputs["xa_per_90"]
                * qualitative["attack_multiplier"],
            }
            component_prior = {
                **prior,
                **{
                    field: inputs[field]
                    for field in (
                        "points_per_90",
                        "xg_per_90",
                        "xa_per_90",
                        "saves_per_90",
                        "bonus_per_90",
                        "defensive_contribution_per_90",
                        "yellow_cards_per_90",
                        "red_cards_per_90",
                        "own_goals_per_90",
                        "penalties_missed_per_90",
                        "penalties_saved_per_90",
                    )
                },
            }
            component_base_inputs = build_component_inputs(
                base_simulation_inputs, player_feature, component_prior
            )
            component_base_inputs["xg_per_90"] *= attack_factor
            component_base_inputs["xa_per_90"] *= attack_factor
            component_adjusted_inputs = {
                **component_base_inputs,
                "starter_minutes_mean": max(
                    45,
                    min(
                        90,
                        number(component_base_inputs.get("starter_minutes_mean"))
                        + qualitative["minutes_delta"],
                    ),
                ),
                "substitute_minutes_mean": max(
                    1,
                    min(
                        45,
                        number(component_base_inputs.get("substitute_minutes_mean"))
                        + qualitative["minutes_delta"] * 0.25,
                    ),
                ),
                "xg_per_90": component_base_inputs["xg_per_90"]
                * qualitative["attack_multiplier"],
                "xa_per_90": component_base_inputs["xa_per_90"]
                * qualitative["attack_multiplier"],
            }
            seed = (integer(fixture.get("fixture_id")), player_id)
            quantitative = simulate_player_fixture(
                base_simulation_inputs,
                simulations=simulations,
                seed_parts=(*seed, "shared"),
                scoring_rules_version=scoring_rules_version,
            )
            adjusted = simulate_player_fixture(
                adjusted_simulation_inputs,
                simulations=simulations,
                seed_parts=(*seed, "shared"),
                scoring_rules_version=scoring_rules_version,
            )
            component_quantitative = simulate_component_player_fixture(
                component_base_inputs,
                simulations=simulations,
                seed_parts=(*seed, "component-shared"),
                scoring_rules_version=scoring_rules_version,
            )
            component_adjusted = simulate_component_player_fixture(
                component_adjusted_inputs,
                simulations=simulations,
                seed_parts=(*seed, "component-shared"),
                scoring_rules_version=scoring_rules_version,
            )
            ensemble_quantitative_samples = [
                (1 - ensemble_point_weight) * control
                + ensemble_point_weight * component
                for control, component in zip(
                    quantitative["points_samples"],
                    component_quantitative["points_samples"],
                )
            ]
            ensemble_adjusted_samples = [
                (1 - ensemble_point_weight) * control
                + ensemble_point_weight * component
                for control, component in zip(
                    adjusted["points_samples"],
                    component_adjusted["points_samples"],
                )
            ]
            ensemble_quantitative_expected_points = statistics.fmean(
                ensemble_quantitative_samples
            )
            ensemble_expected_points = statistics.fmean(
                ensemble_adjusted_samples
            )
            ensemble_probabilities = {
                str(threshold): (
                    (1 - ensemble_probability_weights[str(threshold)])
                    * number(adjusted.get(f"probability_{threshold}_plus"))
                    + ensemble_probability_weights[str(threshold)]
                    * number(
                        component_adjusted.get(
                            f"probability_{threshold}_plus"
                        )
                    )
                )
                for threshold in (6, 10, 15)
            }
            ensemble_probability_3_or_fewer = (
                (1 - ensemble_point_weight)
                * number(adjusted.get("probability_3_or_fewer"))
                + ensemble_point_weight
                * number(component_adjusted.get("probability_3_or_fewer"))
            )
            quantitative_expected_minutes = quantitative["expected_minutes_simulated"]
            expected_minutes = adjusted["expected_minutes_simulated"]
            expected_goals = (
                adjusted_simulation_inputs["xg_per_90"] * expected_minutes / 90
            )
            expected_assists = (
                adjusted_simulation_inputs["xa_per_90"] * expected_minutes / 90
            )
            projection = {
                "model_version": live_model_version,
                "control_model_version": MODEL_VERSION,
                "challenger_model_version": COMPONENT_MODEL_VERSION,
                "ensemble_status": ensemble_config.get("status"),
                "ensemble_point_weight": ensemble_point_weight,
                "ensemble_probability_6_plus_weight": ensemble_probability_weights["6"],
                "ensemble_probability_10_plus_weight": ensemble_probability_weights["10"],
                "ensemble_probability_15_plus_weight": ensemble_probability_weights["15"],
                "scoring_rules_version": scoring_rules_version,
                "projection_evidence_source": inputs["projection_evidence_source"],
                "previous_season": inputs["previous_season"],
                "previous_season_minutes": round(
                    number(inputs["previous_season_minutes"]), 0
                ),
                "bonus_transition_multiplier": round(bonus_transition_multiplier, 4),
                "simulation_count": simulations,
                "gameweek": integer(fixture.get("gameweek")),
                "fixture_id": integer(fixture.get("fixture_id")),
                "kickoff_time": fixture.get("kickoff_time"),
                "player_id": player_id,
                "player_code": player.get("player_code"),
                "web_name": player.get("web_name"),
                "team_id": team_id,
                "team_name": player.get("team_name"),
                "position": player.get("position"),
                "price": number(player.get("price")),
                "opponent_team_id": opponent_id,
                "opponent": fixture.get("away_team") if is_home else fixture.get("home_team"),
                "is_home": is_home,
                "difficulty": difficulty,
                "availability_probability": round(inputs["availability_probability"], 4),
                "appearance_probability": round(inputs["appearance_probability"], 4),
                "start_probability": round(inputs["start_probability"], 4),
                "quantitative_expected_minutes": round(quantitative_expected_minutes, 2),
                "qualitative_minutes_delta": qualitative["minutes_delta"],
                "expected_minutes": round(expected_minutes, 2),
                "minutes_p10": adjusted["minutes_p10"],
                "minutes_p50": adjusted["minutes_p50"],
                "minutes_p90": adjusted["minutes_p90"],
                "expected_goals": round(expected_goals, 4),
                "expected_assists": round(expected_assists, 4),
                "clean_sheet_probability": round(cs_probability, 4),
                "quantitative_expected_points": round(
                    ensemble_quantitative_expected_points, 4
                ),
                "qualitative_expected_points_delta": round(
                    ensemble_expected_points
                    - ensemble_quantitative_expected_points,
                    4,
                ),
                "expected_points": round(ensemble_expected_points, 4),
                "points_p10": percentile(ensemble_adjusted_samples, 0.10),
                "points_p50": percentile(ensemble_adjusted_samples, 0.50),
                "points_p90": percentile(ensemble_adjusted_samples, 0.90),
                "probability_6_plus": round(ensemble_probabilities["6"], 4),
                "probability_10_plus": round(ensemble_probabilities["10"], 4),
                "probability_15_plus": round(ensemble_probabilities["15"], 4),
                "probability_3_or_fewer": round(
                    ensemble_probability_3_or_fewer, 4
                ),
                "control_quantitative_expected_points": round(
                    quantitative["expected_points"], 4
                ),
                "control_qualitative_expected_points_delta": round(
                    adjusted["expected_points"] - quantitative["expected_points"],
                    4,
                ),
                "control_expected_points": round(adjusted["expected_points"], 4),
                "control_points_p10": adjusted["points_p10"],
                "control_points_p50": adjusted["points_p50"],
                "control_points_p90": adjusted["points_p90"],
                "control_probability_6_plus": round(
                    adjusted["probability_6_plus"], 4
                ),
                "control_probability_10_plus": round(
                    adjusted["probability_10_plus"], 4
                ),
                "control_probability_15_plus": round(
                    adjusted["probability_15_plus"], 4
                ),
                "control_probability_3_or_fewer": round(
                    adjusted["probability_3_or_fewer"], 4
                ),
                "component_quantitative_expected_points": round(
                    component_quantitative["expected_points"], 4
                ),
                "component_qualitative_expected_points_delta": round(
                    component_adjusted["expected_points"]
                    - component_quantitative["expected_points"],
                    4,
                ),
                "component_expected_points": round(component_adjusted["expected_points"], 4),
                "component_expected_minutes": round(
                    component_adjusted["expected_minutes_simulated"], 2
                ),
                "component_probability_start": round(
                    component_adjusted["probability_start"], 4
                ),
                "component_probability_60_plus": round(
                    component_adjusted["probability_60_plus"], 4
                ),
                "component_expected_goals": round(
                    component_adjusted["expected_goals_simulated"], 4
                ),
                "component_expected_assists": round(
                    component_adjusted["expected_assists_simulated"], 4
                ),
                "component_expected_saves": round(
                    component_adjusted["expected_saves_simulated"], 4
                ),
                "component_goal_return_probability": round(
                    component_adjusted["goal_return_probability"], 4
                ),
                "component_assist_return_probability": round(
                    component_adjusted["assist_return_probability"], 4
                ),
                "component_attacking_return_probability": round(
                    component_adjusted["attacking_return_probability"], 4
                ),
                "component_clean_sheet_return_probability": round(
                    component_adjusted["clean_sheet_return_probability"], 4
                ),
                "component_points_p10": component_adjusted["points_p10"],
                "component_points_p50": component_adjusted["points_p50"],
                "component_points_p90": component_adjusted["points_p90"],
                "component_probability_6_plus": round(
                    component_adjusted["probability_6_plus"], 4
                ),
                "component_probability_10_plus": round(
                    component_adjusted["probability_10_plus"], 4
                ),
                "component_probability_15_plus": round(
                    component_adjusted["probability_15_plus"], 4
                ),
                "component_probability_3_or_fewer": round(
                    component_adjusted["probability_3_or_fewer"], 4
                ),
                "qualitative_observation_count": qualitative["observation_count"],
                "qualitative_observation_ids": "|".join(qualitative["observation_ids"]),
                "qualitative_confidence": qualitative["combined_confidence"],
                "qualitative_attack_multiplier": qualitative["attack_multiplier"],
            }
            for field, value in component_adjusted["expected_points_components"].items():
                projection[f"component_{field}"] = round(value, 4)
            for field, value in qualitative["signals"].items():
                projection[f"qualitative_{field}"] = value
            projections.append(projection)
            samples_by_player[player_id].append(
                {
                    "gameweek": projection["gameweek"],
                    "quantitative": ensemble_quantitative_samples,
                    "adjusted": ensemble_adjusted_samples,
                    "control_quantitative": quantitative["points_samples"],
                    "control_adjusted": adjusted["points_samples"],
                    "component_quantitative": component_quantitative["points_samples"],
                    "component_adjusted": component_adjusted["points_samples"],
                }
            )

    future_gameweeks = sorted({integer(row.get("gameweek")) for row in projections})
    by_player: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in projections:
        by_player[integer(row.get("player_id"))].append(row)
    horizons: list[dict[str, Any]] = []
    for player in players:
        player_id = integer(player.get("player_id"))
        rows = by_player.get(player_id, [])
        base = {
            "model_version": live_model_version,
            "control_model_version": MODEL_VERSION,
            "challenger_model_version": COMPONENT_MODEL_VERSION,
            "ensemble_status": ensemble_config.get("status"),
            "ensemble_point_weight": ensemble_point_weight,
            "ensemble_probability_6_plus_weight": ensemble_probability_weights["6"],
            "ensemble_probability_10_plus_weight": ensemble_probability_weights["10"],
            "ensemble_probability_15_plus_weight": ensemble_probability_weights["15"],
            "scoring_rules_version": scoring_rules_version,
            "projection_evidence_source": (
                rows[0].get("projection_evidence_source") if rows else None
            ),
            "previous_season": rows[0].get("previous_season") if rows else None,
            "previous_season_minutes": number(
                rows[0].get("previous_season_minutes") if rows else 0
            ),
            "bonus_transition_multiplier": (
                rows[0].get("bonus_transition_multiplier") if rows else 1.0
            ),
            "player_id": player_id,
            "player_code": player.get("player_code"),
            "web_name": player.get("web_name"),
            "team_id": integer(player.get("team_id")),
            "team_name": player.get("team_name"),
            "position": player.get("position"),
            "price": number(player.get("price")),
        }
        for horizon in (1, 3, 5, 6):
            included = set(future_gameweeks[:horizon])
            selected = [row for row in rows if integer(row.get("gameweek")) in included]
            points = sum(number(row.get("expected_points")) for row in selected)
            quantitative_points = sum(
                number(row.get("quantitative_expected_points")) for row in selected
            )
            minutes = sum(number(row.get("expected_minutes")) for row in selected)
            sample_rows = [
                row
                for row in samples_by_player.get(player_id, [])
                if integer(row.get("gameweek")) in included
            ]
            combined_samples = [
                sum(row["adjusted"][index] for row in sample_rows)
                for index in range(simulations)
            ] if sample_rows else []
            combined_component_samples = [
                sum(row["component_adjusted"][index] for row in sample_rows)
                for index in range(simulations)
            ] if sample_rows else []
            combined_control_samples = [
                sum(row["control_adjusted"][index] for row in sample_rows)
                for index in range(simulations)
            ] if sample_rows else []
            base[f"expected_points_next_{horizon}"] = round(points, 3)
            base[f"quantitative_expected_points_next_{horizon}"] = round(
                quantitative_points, 3
            )
            base[f"qualitative_points_delta_next_{horizon}"] = round(
                points - quantitative_points, 3
            )
            base[f"expected_minutes_next_{horizon}"] = round(minutes, 2)
            base[f"value_next_{horizon}"] = round(points / number(player.get("price")), 4) if number(player.get("price")) else 0
            base[f"points_p10_next_{horizon}"] = percentile(combined_samples, 0.10)
            base[f"points_p50_next_{horizon}"] = percentile(combined_samples, 0.50)
            base[f"points_p90_next_{horizon}"] = percentile(combined_samples, 0.90)
            for threshold in (6, 10, 15):
                base[f"probability_{threshold}_plus_next_{horizon}"] = round(
                    sum(value >= threshold for value in combined_samples)
                    / len(combined_samples)
                    if combined_samples
                    else 0,
                    4,
                )
            base[f"probability_3_or_fewer_next_{horizon}"] = round(
                sum(value <= 3 for value in combined_samples)
                / len(combined_samples)
                if combined_samples
                else 0,
                4,
            )
            base[f"control_expected_points_next_{horizon}"] = round(
                statistics.fmean(combined_control_samples)
                if combined_control_samples
                else 0,
                3,
            )
            base[f"control_points_p10_next_{horizon}"] = percentile(
                combined_control_samples, 0.10
            )
            base[f"control_points_p50_next_{horizon}"] = percentile(
                combined_control_samples, 0.50
            )
            base[f"control_points_p90_next_{horizon}"] = percentile(
                combined_control_samples, 0.90
            )
            base[f"component_expected_points_next_{horizon}"] = round(
                statistics.fmean(combined_component_samples)
                if combined_component_samples
                else 0,
                3,
            )
            base[f"component_points_p10_next_{horizon}"] = percentile(
                combined_component_samples, 0.10
            )
            base[f"component_points_p50_next_{horizon}"] = percentile(
                combined_component_samples, 0.50
            )
            base[f"component_points_p90_next_{horizon}"] = percentile(
                combined_component_samples, 0.90
            )
            base[f"component_probability_10_plus_next_{horizon}"] = round(
                sum(value >= 10 for value in combined_component_samples)
                / len(combined_component_samples)
                if combined_component_samples
                else 0,
                4,
            )
            base[f"component_probability_15_plus_next_{horizon}"] = round(
                sum(value >= 15 for value in combined_component_samples)
                / len(combined_component_samples)
                if combined_component_samples
                else 0,
                4,
            )
        horizons.append(base)
    return projections, horizons


def top_projection_rows(rows: list[dict[str, Any]], field: str, limit: int = 20) -> list[dict[str, Any]]:
    selected = sorted(
        (row for row in rows if number(row.get(field)) > 0),
        key=lambda row: number(row.get(field)),
        reverse=True,
    )[:limit]
    fields = ["player_id", "web_name", "team_name", "position", "price", field]
    return [{key: row.get(key) for key in fields} for row in selected]


def write_prediction_snapshot(
    data_dir: Path,
    current_gameweek: dict[str, Any],
    horizons: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    next_event = current_gameweek.get("next") or {}
    deadline_text = next_event.get("deadline_time")
    created: str | None = None
    if deadline_text:
        deadline = datetime.fromisoformat(deadline_text.replace("Z", "+00:00"))
        observed = datetime.fromisoformat(generated_at)
        hours = (deadline - observed).total_seconds() / 3600
        if 0 <= hours <= 8:
            gameweek = integer(next_event.get("id"))
            timestamp = observed.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            path = data_dir / "predictions" / f"gw{gameweek:02d}" / f"{timestamp}.csv"
            if not path.exists():
                rows = [
                    {
                        **row,
                        "prediction_created_at": generated_at,
                        "target_gameweek": gameweek,
                        "deadline_time": deadline_text,
                    }
                    for row in horizons
                ]
                fields = [
                    "prediction_created_at",
                    "target_gameweek",
                    "deadline_time",
                    "model_version",
                    "control_model_version",
                    "challenger_model_version",
                    "ensemble_status",
                    "ensemble_point_weight",
                    "ensemble_probability_6_plus_weight",
                    "ensemble_probability_10_plus_weight",
                    "ensemble_probability_15_plus_weight",
                    "scoring_rules_version",
                    "bonus_transition_multiplier",
                    "player_id",
                    "player_code",
                    "web_name",
                    "team_id",
                    "team_name",
                    "position",
                    "price",
                    "quantitative_expected_points_next_1",
                    "qualitative_points_delta_next_1",
                    "expected_points_next_1",
                    "expected_minutes_next_1",
                    "points_p10_next_1",
                    "points_p50_next_1",
                    "points_p90_next_1",
                    "value_next_1",
                    "control_expected_points_next_1",
                    "control_points_p10_next_1",
                    "control_points_p50_next_1",
                    "control_points_p90_next_1",
                    "component_expected_points_next_1",
                    "component_points_p10_next_1",
                    "component_points_p50_next_1",
                    "component_points_p90_next_1",
                    "component_probability_10_plus_next_1",
                    "component_probability_15_plus_next_1",
                ]
                write_csv(path, rows, fields)
                created = str(path.relative_to(data_dir)).replace("\\", "/")

    files = sorted(
        str(path.relative_to(data_dir)).replace("\\", "/")
        for path in (data_dir / "predictions").glob("gw*/*.csv")
    )
    index = {
        "generated_at": generated_at,
        "model_version": (
            horizons[0].get("model_version") if horizons else MODEL_VERSION
        ),
        "snapshot_created_this_run": created,
        "prediction_snapshots": files,
    }
    write_json(data_dir / "chatgpt" / "prediction_index.json", index)
    return index


def gameweek_finality(data_dir: Path) -> dict[int, bool]:
    finality, _ = official_gameweek_finality(data_dir)
    return finality


def managed_team_prediction_audit(
    data_dir: Path,
    gameweek: int,
    prediction_rows: list[dict[str, Any]],
    actual: dict[tuple[int, int], float],
) -> dict[str, Any] | None:
    """Score the manager's submitted XI, not just the full player population."""

    path = data_dir / "raw" / "latest" / "latest-picks.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entry_history = payload.get("entry_history") or {}
    if integer(entry_history.get("event")) != gameweek:
        return None
    picks = payload.get("picks") or []
    predicted = {
        integer(row.get("player_id")): number(row.get("expected_points_next_1"))
        for row in prediction_rows
    }
    starters = [row for row in picks if integer(row.get("multiplier")) > 0]
    if len(starters) != 11:
        return None
    comparable = [
        row
        for row in starters
        if integer(row.get("element")) in predicted
        and (gameweek, integer(row.get("element"))) in actual
    ]
    if len(comparable) != 11:
        return None
    errors = [
        predicted[integer(row.get("element"))]
        - actual[(gameweek, integer(row.get("element")))]
        for row in comparable
    ]
    model_starting_points = sum(
        predicted[integer(row.get("element"))] for row in starters
    )
    actual_starting_points = sum(
        actual[(gameweek, integer(row.get("element")))] for row in starters
    )
    model_total = sum(
        predicted.get(integer(row.get("element")), 0)
        * integer(row.get("multiplier"))
        for row in picks
    )
    actual_total = sum(
        actual.get((gameweek, integer(row.get("element"))), 0)
        * integer(row.get("multiplier"))
        for row in picks
    )
    bench_points = sum(
        actual.get((gameweek, integer(row.get("element"))), 0)
        for row in picks
        if integer(row.get("multiplier")) == 0
    )
    captain = next((row for row in picks if row.get("is_captain")), {})
    return {
        "gameweek": gameweek,
        "selected_xi_players_evaluated": len(errors),
        "selected_xi_mean_absolute_error": round(
            sum(abs(error) for error in errors) / len(errors), 4
        ),
        "selected_xi_mean_bias": round(sum(errors) / len(errors), 4),
        "starting_xi_predicted_points_before_captain": round(
            model_starting_points, 3
        ),
        "starting_xi_actual_points_before_captain": round(
            actual_starting_points, 3
        ),
        "submitted_team_predicted_points": round(model_total, 3),
        "submitted_team_actual_points": round(actual_total, 3),
        "official_manager_points": number(entry_history.get("points")),
        "captain_player_id": integer(captain.get("element")) or None,
        "bench_actual_points": round(bench_points, 3),
    }


def evaluate_predictions(data_dir: Path) -> dict[str, Any]:
    actual_rows = read_csv(data_dir / "chatgpt" / "player_gameweeks.csv")
    actual: dict[tuple[int, int], float] = {}
    for row in actual_rows:
        actual[(integer(row.get("gameweek")), integer(row.get("player_id")))] = number(row.get("total_points"))

    results: list[dict[str, Any]] = []
    finality, finality_source = official_gameweek_finality(data_dir)
    skipped_unfinalised = 0
    prediction_root = data_dir / "predictions"
    for gameweek_dir in sorted(prediction_root.glob("gw*")):
        snapshots = sorted(gameweek_dir.glob("*.csv"))
        if not snapshots:
            continue
        rows = read_csv(snapshots[-1])
        gameweek = integer(rows[0].get("target_gameweek")) if rows else 0
        if not finality.get(gameweek, False):
            skipped_unfinalised += 1
            continue
        errors = []
        quantitative_errors = []
        predictions = []
        actual_values = []
        for row in rows:
            player_id = integer(row.get("player_id"))
            if (gameweek, player_id) not in actual:
                continue
            predicted = number(row.get("expected_points_next_1"))
            quantitative_predicted = number(
                row.get("quantitative_expected_points_next_1")
                if row.get("quantitative_expected_points_next_1") not in {None, ""}
                else predicted
            )
            observed = actual[(gameweek, player_id)]
            errors.append(predicted - observed)
            quantitative_errors.append(quantitative_predicted - observed)
            predictions.append(predicted)
            actual_values.append(observed)
        if not errors:
            continue
        mae = sum(abs(error) for error in errors) / len(errors)
        quantitative_mae = sum(abs(error) for error in quantitative_errors) / len(
            quantitative_errors
        )
        rmse = math.sqrt(sum(error * error for error in errors) / len(errors))
        managed_team = managed_team_prediction_audit(
            data_dir, gameweek, rows, actual
        )
        results.append(
            {
                "gameweek": gameweek,
                "model_version": rows[0].get("model_version"),
                "prediction_snapshot": str(snapshots[-1].relative_to(data_dir)).replace("\\", "/"),
                "players_evaluated": len(errors),
                "mean_absolute_error": round(mae, 4),
                "quantitative_mean_absolute_error": round(quantitative_mae, 4),
                "qualitative_mae_improvement": round(quantitative_mae - mae, 4),
                "root_mean_squared_error": round(rmse, 4),
                "mean_bias": round(sum(errors) / len(errors), 4),
                "average_predicted_points": round(sum(predictions) / len(predictions), 4),
                "average_actual_points": round(sum(actual_values) / len(actual_values), 4),
                "managed_team": managed_team,
            }
        )
    fields = [
        "gameweek",
        "model_version",
        "prediction_snapshot",
        "players_evaluated",
        "mean_absolute_error",
        "quantitative_mean_absolute_error",
        "qualitative_mae_improvement",
        "root_mean_squared_error",
        "mean_bias",
        "average_predicted_points",
        "average_actual_points",
    ]
    write_csv(data_dir / "chatgpt" / "prediction_accuracy.csv", results, fields)
    summary = {
        "generated_at": utc_now(),
        "evaluated_gameweeks": len(results),
        "skipped_unfinalised_gameweeks": skipped_unfinalised,
        "finality_requirement": "finished=true and data_checked=true",
        "finality_source": finality_source,
        "latest": results[-1] if results else None,
        "managed_team_latest": next(
            (
                row.get("managed_team")
                for row in reversed(results)
                if row.get("managed_team")
            ),
            None,
        ),
        "history": results,
    }
    write_json(data_dir / "chatgpt" / "prediction_evaluation.json", summary)
    return summary


def update_dataset_manifest(chatgpt_dir: Path) -> None:
    path = chatgpt_dir / "manifest.json"
    if not path.is_file():
        return
    manifest = json.loads(path.read_text(encoding="utf-8"))
    datasets = manifest.setdefault("datasets", [])
    existing = {item.get("path") for item in datasets}
    for name in MODEL_DATASETS:
        dataset_path = f"data/chatgpt/{name}"
        if (chatgpt_dir / name).is_file() and dataset_path not in existing:
            datasets.append({"path": dataset_path})
            existing.add(dataset_path)
    write_json(path, manifest)


def build_model(data_dir: Path) -> dict[str, Any]:
    chatgpt_dir = data_dir / "chatgpt"
    manifest_path = chatgpt_dir / "manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.is_file()
        else {}
    )
    season = manifest.get("season")
    scoring_rules = load_scoring_rules(
        data_dir / "context" / "scoring_rules.json", season
    )
    players = read_csv(chatgpt_dir / "players.csv")
    teams = read_csv(chatgpt_dir / "teams.csv")
    fixtures = read_csv(chatgpt_dir / "fixtures.csv")
    current_gameweek = json.loads(
        (chatgpt_dir / "current_gameweek.json").read_text(encoding="utf-8")
    )
    target_gameweek = integer(
        (current_gameweek.get("next") or {}).get("id")
    ) or None
    fixture_history = read_csv(chatgpt_dir / "player_fixtures.csv")
    past_seasons = read_csv(data_dir / "history" / "current_player_past_seasons.csv")
    observations = read_observations(data_dir / "scouting" / "observations.jsonl")
    source_registry = load_source_registry(data_dir / "context" / "sources.json")
    context_signals = read_context_signals(
        data_dir / "context" / "signals.jsonl", source_registry
    )
    ensemble_config = load_ensemble_config(
        data_dir / "model" / "ensemble_model_candidate.json"
    )
    component_candidate_path = data_dir / "model" / "component_model_candidate.json"
    component_candidate_status = "shadow_candidate_pending_held_out_evidence"
    if component_candidate_path.is_file():
        try:
            component_candidate = json.loads(
                component_candidate_path.read_text(encoding="utf-8")
            )
            component_candidate_status = str(
                component_candidate.get("status")
                or component_candidate_status
            )
        except (json.JSONDecodeError, OSError):
            component_candidate_status = "shadow_candidate_assessment_unreadable"
    if not players or not teams or not fixtures:
        raise ValueError("Core FPL datasets are missing; run the collection workflow first")

    player_features = build_player_features(players, fixture_history)
    team_features = build_team_features(teams, fixture_history, fixtures)
    priors = load_priors(data_dir / "history" / "position_priors.csv")
    projections, horizons = build_projections(
        players,
        player_features,
        team_features,
        fixtures,
        priors,
        past_seasons,
        observations,
        ensemble_config=ensemble_config,
        scoring_rules=scoring_rules,
        target_gameweek=target_gameweek,
    )

    write_csv(
        chatgpt_dir / "player_rolling_features.csv",
        player_features,
        ordered_fields(player_features, ["player_id", "player_code", "web_name", "team_id", "team_name", "position", "price"]),
    )
    write_csv(
        chatgpt_dir / "team_rolling_features.csv",
        team_features,
        ordered_fields(team_features, ["team_id", "team_code", "team_name"]),
    )
    projection_fields = ordered_fields(
        projections,
        PROJECTION_FIELDS,
    )
    write_csv(chatgpt_dir / "player_projections.csv", projections, projection_fields)
    horizon_fields = ordered_fields(
        horizons,
        ["model_version", "control_model_version", "challenger_model_version", "ensemble_status", "player_id", "player_code", "web_name", "team_id", "team_name", "position", "price"],
    )
    write_csv(chatgpt_dir / "player_projection_horizons.csv", horizons, horizon_fields)
    observation_fields = [
        "observation_id",
        "observed_at",
        "recorded_at",
        "observer",
        "season",
        "gameweek",
        "fixture_id",
        "player_id",
        "player_code",
        "player_name",
        "source_type",
        "raw_note",
        "retracts_observation_id",
        *SIGNAL_FIELDS,
        "confidence",
        "valid_from",
        "expires_at",
        "status",
    ]
    write_csv(
        chatgpt_dir / "scouting_observations.csv",
        observations,
        ordered_fields(observations, observation_fields),
    )

    generated_at = utc_now()
    my_team_path = chatgpt_dir / "my_team.json"
    my_team = (
        json.loads(my_team_path.read_text(encoding="utf-8"))
        if my_team_path.is_file()
        else {"available": False, "squad": []}
    )
    manager_history_path = chatgpt_dir / "manager_history.json"
    manager_history = (
        json.loads(manager_history_path.read_text(encoding="utf-8"))
        if manager_history_path.is_file()
        else {}
    )
    chip_rules_path = data_dir / "context" / "chip_rules.json"
    chip_rules = (
        json.loads(chip_rules_path.read_text(encoding="utf-8"))
        if chip_rules_path.is_file()
        else {}
    )
    write_signal_csv(chatgpt_dir / "external_context_signals.csv", context_signals)
    external_summary = context_summary(
        context_signals, source_registry, generated_at
    )
    write_json(chatgpt_dir / "external_context_summary.json", external_summary)
    decision_support = build_decision_support(
        horizons,
        players,
        my_team,
        current_gameweek,
        context_signals,
        source_registry,
        generated_at,
        manager_history=manager_history,
        season=season,
        chip_rules=chip_rules,
        fixture_projections=projections,
        scoring_rules_version=scoring_rules.get("version"),
        past_seasons=past_seasons,
    )
    write_decision_support(chatgpt_dir / "fpl_decisions.json", decision_support)
    write_json(
        chatgpt_dir / "initial_squad_plan.json",
        decision_support["initial_squad_plan"],
    )
    write_json(
        chatgpt_dir / "launch_validation.json",
        decision_support["initial_squad_plan"].get("launch_validation", {}),
    )
    prediction_index = write_prediction_snapshot(data_dir, current_gameweek, horizons, generated_at)
    evaluation = evaluate_predictions(data_dir)
    prospective = update_prospective_evaluation(
        data_dir,
        decision_support,
        horizons,
        players,
        my_team,
        current_gameweek,
        context_signals,
        source_registry,
        generated_at,
        fixture_projections=projections,
    )
    decision_support["prospective_evaluation"] = {
        "status": prospective["evaluation"].get("status"),
        "evaluated_gameweeks": prospective["evaluation"].get("evaluated_gameweeks"),
        "snapshot_created_this_run": prospective["index"].get("snapshot_created_this_run"),
        "minimum_gameweeks_for_evidence": prospective["evaluation"].get(
            "minimum_gameweeks_for_evidence"
        ),
    }
    operations = update_gameweek_operations(
        data_dir,
        decision_support,
        horizons,
        players,
        my_team,
        current_gameweek,
        projections,
        external_summary,
        prospective,
        generated_at,
    )
    decision_support["gameweek_operations"] = {
        "version": operations.get("operations_version"),
        "status": operations.get("status"),
        "target_gameweek": operations.get("target_gameweek"),
        "material_change": operations.get("material_change"),
        "change_summary": operations.get("change_summary"),
        "deadline_freeze": operations.get("deadline_freeze"),
        "warning_count": len(operations.get("warnings", [])),
        "report_json": "data/chatgpt/gameweek_report.json",
        "report_markdown": "data/chatgpt/gameweek_report.md",
        "advisory_only": True,
    }
    write_decision_support(chatgpt_dir / "fpl_decisions.json", decision_support)
    qualitative_projection_rows = sum(
        integer(row.get("qualitative_observation_count")) > 0 for row in projections
    )
    retracted_observation_ids = {
        str(observation.get("retracts_observation_id"))
        for observation in observations
        if observation.get("status") == "retracted"
        and observation.get("retracts_observation_id")
    }
    qualitative_summary = {
        "generated_at": generated_at,
        "observation_rows": len(observations),
        "active_observation_rows": sum(
            observation.get("status", "active") == "active"
            and str(observation.get("observation_id")) not in retracted_observation_ids
            for observation in observations
        ),
        "fixture_projections_adjusted": qualitative_projection_rows,
        "maximum_minutes_adjustment": 12,
        "attack_multiplier_bounds": [0.8, 1.2],
        "signal_half_life_days": 14,
        "principle": "Raw human observations are preserved and evaluated separately from the quantitative forecast.",
    }
    write_json(chatgpt_dir / "qualitative_signal_summary.json", qualitative_summary)
    summary = {
        "generated_at": generated_at,
        "model_version": ensemble_config["model_version"],
        "control_model_version": MODEL_VERSION,
        "challenger_model_version": COMPONENT_MODEL_VERSION,
        "ensemble_status": ensemble_config["status"],
        "ensemble_point_weight": ensemble_config["point_weight"],
        "ensemble_probability_weights": ensemble_config["probability_weights"],
        "challenger_status": component_candidate_status,
        "season": season,
        "scoring_rules_status": scoring_rules.get("status"),
        "scoring_rules_version": scoring_rules.get("version"),
        "bonus_transition": scoring_rules.get("bonus_transition"),
        "simulations_per_player_fixture": DEFAULT_SIMULATIONS,
        "method": "Development-selected ensemble with player-specific early-season priors, separately audited control, component, qualitative and freshness-weighted external-context decision layers.",
        "player_feature_rows": len(player_features),
        "team_feature_rows": len(team_features),
        "fixture_projection_rows": len(projections),
        "player_horizon_rows": len(horizons),
        "scouting_observation_rows": len(observations),
        "external_context_signal_rows": len(context_signals),
        "active_external_context_signal_rows": external_summary["active_signal_rows"],
        "decision_support_status": decision_support["status"],
        "initial_squad_status": decision_support["initial_squad_plan"]["status"],
        "launch_validation_status": (
            decision_support["initial_squad_plan"]
            .get("launch_validation", {})
            .get("status")
        ),
        "launch_validation_high_severity_issues": (
            decision_support["initial_squad_plan"]
            .get("launch_validation", {})
            .get("high_severity_issue_count", 0)
        ),
        "qualitatively_adjusted_fixture_rows": qualitative_projection_rows,
        "top_next_gameweek": top_projection_rows(horizons, "expected_points_next_1"),
        "top_next_three_gameweeks": top_projection_rows(horizons, "expected_points_next_3"),
        "component_top_next_gameweek": top_projection_rows(
            horizons, "component_expected_points_next_1"
        ),
        "component_top_next_three_gameweeks": top_projection_rows(
            horizons, "component_expected_points_next_3"
        ),
        "prediction_snapshot_created": prediction_index.get("snapshot_created_this_run"),
        "evaluated_gameweeks": evaluation.get("evaluated_gameweeks"),
        "prospective_evaluated_gameweeks": prospective["evaluation"].get(
            "evaluated_gameweeks"
        ),
        "prospective_snapshot_created": prospective["index"].get(
            "snapshot_created_this_run"
        ),
        "gameweek_operations_status": operations.get("status"),
        "gameweek_report_material_change": operations.get("material_change"),
        "gameweek_report_warning_count": len(operations.get("warnings", [])),
        "limitations": [
            "The ensemble weights were fitted on 2022/23-2023/24 and passed the documented 2024/25 held-out promotion gate.",
            "The control and component models remain available beside every ensemble recommendation for audit.",
            "External context is source-weighted and applied only to decision support until prospective evidence justifies changing the validated ensemble.",
            "Expected minutes are inferred from recent starts, minutes, availability and prior-season usage unless a timestamped decision-layer signal is present.",
            "Previous-season player evidence is shrunk towards positional priors and fades over the first six current-season fixtures.",
            "Bonus and rare disciplinary events use simplified distributions rather than a full event-level match model.",
            "Qualitative observations are prospective signals and must be timestamped before they can be evaluated honestly.",
        ],
    }
    write_json(chatgpt_dir / "projection_summary.json", summary)
    update_dataset_manifest(chatgpt_dir)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build rolling features and player-level FPL return distributions"
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    print(json.dumps(build_model(args.data_dir), indent=2))


if __name__ == "__main__":
    main()
