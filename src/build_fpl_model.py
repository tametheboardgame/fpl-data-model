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
from src.scouting_observations import SIGNAL_FIELDS, qualitative_adjustment, read_observations
from src.update_fpl_data import utc_now, write_csv, write_json


MODEL_VERSION = "player-sim-2.0"
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

    def total(field: str) -> float:
        return sum(number(row.get(field)) for row in selected)

    per90 = 90 / minutes if minutes else 0
    return {
        f"fixtures_{window}": fixture_count,
        f"appearance_rate_{window}": round(appearances / fixture_count, 4) if fixture_count else 0,
        f"start_rate_{window}": round(starts / fixture_count, 4) if fixture_count else 0,
        f"average_minutes_{window}": round(minutes / fixture_count, 2) if fixture_count else 0,
        f"average_minutes_when_appearing_{window}": round(minutes / appearances, 2) if appearances else 0,
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


def projection_inputs(
    player: dict[str, Any],
    feature: dict[str, Any],
    prior: dict[str, Any],
    past: dict[str, Any] | None,
) -> dict[str, float]:
    availability = availability_probability(player)
    fixtures_6 = integer(feature.get("fixtures_6"))
    if fixtures_6:
        average_minutes = 0.7 * number(feature.get("average_minutes_6")) + 0.3 * number(feature.get("average_minutes_3"))
        start_rate = 0.7 * number(feature.get("start_rate_6")) + 0.3 * number(feature.get("start_rate_3"))
        appearance_rate = 0.7 * number(feature.get("appearance_rate_6")) + 0.3 * number(feature.get("appearance_rate_3"))
    elif past:
        average_minutes = min(90, number(past.get("minutes")) / 38)
        start_rate = min(1, number(past.get("starts")) / 38)
        appearance_rate = min(1, max(start_rate, number(past.get("minutes")) / (38 * 60)))
    else:
        average_minutes = number(prior.get("average_minutes_per_fixture"))
        start_rate = number(prior.get("start_rate"))
        appearance_rate = number(prior.get("appearance_rate"))

    minutes_10 = number(feature.get("minutes_10"))
    return {
        "availability_probability": availability,
        "start_probability": max(0, min(1, availability * start_rate)),
        "appearance_probability": max(0, min(1, availability * max(start_rate, appearance_rate))),
        "expected_minutes": max(0, min(90, availability * average_minutes)),
        "minutes_deviation": max(6, number(feature.get("minutes_standard_deviation_6"))),
        "points_per_90": blended_rate(number(feature.get("points_per_90_10")), minutes_10, number(prior.get("points_per_90"))),
        "xg_per_90": blended_rate(number(feature.get("xg_per_90_10")), minutes_10, number(prior.get("xg_per_90"))),
        "xa_per_90": blended_rate(number(feature.get("xa_per_90_10")), minutes_10, number(prior.get("xa_per_90"))),
        "saves_per_90": blended_rate(number(feature.get("saves_per_90_10")), minutes_10, number(prior.get("saves_per_90"))),
        "bonus_per_90": blended_rate(number(feature.get("bonus_per_90_10")), minutes_10, number(prior.get("bonus_per_90"))),
        "defensive_contribution_per_90": blended_rate(number(feature.get("defensive_contribution_per_90_10")), minutes_10, number(prior.get("defensive_contribution_per_90"))),
        "yellow_cards_per_90": blended_rate(number(feature.get("yellow_cards_per_90_10")), minutes_10, number(prior.get("yellow_cards_per_90"))),
        "red_cards_per_90": blended_rate(number(feature.get("red_cards_per_90_10")), minutes_10, number(prior.get("red_cards_per_90"))),
        "own_goals_per_90": blended_rate(number(feature.get("own_goals_per_90_10")), minutes_10, number(prior.get("own_goals_per_90"))),
        "penalties_missed_per_90": blended_rate(number(feature.get("penalties_missed_per_90_10")), minutes_10, number(prior.get("penalties_missed_per_90"))),
        "penalties_saved_per_90": blended_rate(number(feature.get("penalties_saved_per_90_10")), minutes_10, number(prior.get("penalties_saved_per_90"))),
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
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    feature_by_player = {integer(row.get("player_id")): row for row in player_features}
    feature_by_team = {integer(row.get("team_id")): row for row in team_features}
    past_by_code = latest_past_seasons(past_seasons)
    observations = observations or []
    future = [
        row
        for row in fixtures
        if not truthy(row.get("finished")) and integer(row.get("gameweek"))
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
            seed = (integer(fixture.get("fixture_id")), player_id)
            quantitative = simulate_player_fixture(
                base_simulation_inputs,
                simulations=simulations,
                seed_parts=(*seed, "shared"),
            )
            adjusted = simulate_player_fixture(
                adjusted_simulation_inputs,
                simulations=simulations,
                seed_parts=(*seed, "shared"),
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
                "model_version": MODEL_VERSION,
                "scoring_rules_version": SCORING_RULES_VERSION,
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
                "quantitative_expected_points": round(quantitative["expected_points"], 4),
                "qualitative_expected_points_delta": round(
                    adjusted["expected_points"] - quantitative["expected_points"], 4
                ),
                "expected_points": round(adjusted["expected_points"], 4),
                "points_p10": adjusted["points_p10"],
                "points_p50": adjusted["points_p50"],
                "points_p90": adjusted["points_p90"],
                "probability_6_plus": round(adjusted["probability_6_plus"], 4),
                "probability_10_plus": round(adjusted["probability_10_plus"], 4),
                "probability_15_plus": round(adjusted["probability_15_plus"], 4),
                "probability_3_or_fewer": round(adjusted["probability_3_or_fewer"], 4),
                "qualitative_observation_count": qualitative["observation_count"],
                "qualitative_observation_ids": "|".join(qualitative["observation_ids"]),
                "qualitative_confidence": qualitative["combined_confidence"],
                "qualitative_attack_multiplier": qualitative["attack_multiplier"],
            }
            for field, value in qualitative["signals"].items():
                projection[f"qualitative_{field}"] = value
            projections.append(projection)
            samples_by_player[player_id].append(
                {
                    "gameweek": projection["gameweek"],
                    "quantitative": quantitative["points_samples"],
                    "adjusted": adjusted["points_samples"],
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
            "model_version": MODEL_VERSION,
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
                ]
                write_csv(path, rows, fields)
                created = str(path.relative_to(data_dir)).replace("\\", "/")

    files = sorted(
        str(path.relative_to(data_dir)).replace("\\", "/")
        for path in (data_dir / "predictions").glob("gw*/*.csv")
    )
    index = {
        "generated_at": generated_at,
        "model_version": MODEL_VERSION,
        "snapshot_created_this_run": created,
        "prediction_snapshots": files,
    }
    write_json(data_dir / "chatgpt" / "prediction_index.json", index)
    return index


def evaluate_predictions(data_dir: Path) -> dict[str, Any]:
    actual_rows = read_csv(data_dir / "chatgpt" / "player_gameweeks.csv")
    actual: dict[tuple[int, int], float] = {}
    for row in actual_rows:
        actual[(integer(row.get("gameweek")), integer(row.get("player_id")))] = number(row.get("total_points"))

    results: list[dict[str, Any]] = []
    prediction_root = data_dir / "predictions"
    for gameweek_dir in sorted(prediction_root.glob("gw*")):
        snapshots = sorted(gameweek_dir.glob("*.csv"))
        if not snapshots:
            continue
        rows = read_csv(snapshots[-1])
        gameweek = integer(rows[0].get("target_gameweek")) if rows else 0
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
        "latest": results[-1] if results else None,
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
    players = read_csv(chatgpt_dir / "players.csv")
    teams = read_csv(chatgpt_dir / "teams.csv")
    fixtures = read_csv(chatgpt_dir / "fixtures.csv")
    fixture_history = read_csv(chatgpt_dir / "player_fixtures.csv")
    past_seasons = read_csv(data_dir / "history" / "current_player_past_seasons.csv")
    observations = read_observations(data_dir / "scouting" / "observations.jsonl")
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
        ["model_version", "gameweek", "fixture_id", "kickoff_time", "player_id", "player_code", "web_name", "team_id", "team_name", "position", "price", "opponent_team_id", "opponent", "is_home", "difficulty", "expected_minutes", "expected_points"],
    )
    write_csv(chatgpt_dir / "player_projections.csv", projections, projection_fields)
    horizon_fields = ordered_fields(
        horizons,
        ["model_version", "player_id", "player_code", "web_name", "team_id", "team_name", "position", "price"],
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
    current_gameweek = json.loads((chatgpt_dir / "current_gameweek.json").read_text(encoding="utf-8"))
    prediction_index = write_prediction_snapshot(data_dir, current_gameweek, horizons, generated_at)
    evaluation = evaluate_predictions(data_dir)
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
        "model_version": MODEL_VERSION,
        "scoring_rules_version": SCORING_RULES_VERSION,
        "simulations_per_player_fixture": DEFAULT_SIMULATIONS,
        "method": "Deterministic player-level simulation of FPL returns using minutes, attacking involvement, clean sheets, saves, defensive contributions, disciplinary events and bonus, with a separately auditable qualitative overlay.",
        "player_feature_rows": len(player_features),
        "team_feature_rows": len(team_features),
        "fixture_projection_rows": len(projections),
        "player_horizon_rows": len(horizons),
        "scouting_observation_rows": len(observations),
        "qualitatively_adjusted_fixture_rows": qualitative_projection_rows,
        "top_next_gameweek": top_projection_rows(horizons, "expected_points_next_1"),
        "top_next_three_gameweeks": top_projection_rows(horizons, "expected_points_next_3"),
        "prediction_snapshot_created": prediction_index.get("snapshot_created_this_run"),
        "evaluated_gameweeks": evaluation.get("evaluated_gameweeks"),
        "limitations": [
            "The simulator is a transparent baseline distribution and does not yet include betting odds or confirmed team news.",
            "Expected minutes are inferred from recent starts, minutes, availability and prior-season usage.",
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
