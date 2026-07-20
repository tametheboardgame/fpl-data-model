from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from src.build_fpl_model import FALLBACK_PRIORS, MODEL_VERSION, number, recent_metrics, truthy
from src.player_return_simulator import percentile, simulate_player_fixture
from src.update_fpl_data import utc_now, write_csv, write_json


DEVELOPMENT_SEASONS = ["2022-23", "2023-24"]
HELD_OUT_SEASON = "2024-25"
DEFAULT_SEASONS = [*DEVELOPMENT_SEASONS, HELD_OUT_SEASON]
BACKTEST_SIMULATIONS = 300
MINIMUM_PRIOR_FIXTURES = 3
PREDICTION_FIELDS = [
    "season",
    "gameweek",
    "player_key",
    "player_name",
    "position",
    "team",
    "fixture_count",
    "was_home",
    "eligible_reason",
    "prior_fixture_rows",
    "actual_minutes",
    "actual_points",
    "position_average_prediction",
    "season_average_prediction",
    "last_3_prediction",
    "last_6_prediction",
    "minutes_only_prediction",
    "player_sim_prediction",
    "calibrated_player_sim_prediction",
    "probability_6_plus",
    "probability_10_plus",
    "probability_15_plus",
    "calibrated_probability_6_plus",
    "calibrated_probability_10_plus",
    "calibrated_probability_15_plus",
    "points_p10",
    "points_p50",
    "points_p90",
    "predicted_minutes",
    "actual_6_plus",
    "actual_10_plus",
    "actual_15_plus",
]
MODEL_FIELDS = {
    "position_average": "position_average_prediction",
    "season_average": "season_average_prediction",
    "last_3": "last_3_prediction",
    "last_6": "last_6_prediction",
    "minutes_only": "minutes_only_prediction",
    "player_sim": "player_sim_prediction",
    "calibrated_player_sim": "calibrated_player_sim_prediction",
}


def integer(value: Any) -> int:
    return int(number(value))


def read_historical(path: Path, seasons: list[str]) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return [row for row in csv.DictReader(handle) if row.get("season") in seasons]


def player_key(row: dict[str, Any]) -> str:
    element = str(row.get("element") or "").strip()
    return element if element else str(row.get("player_name") or "").strip().lower()


def position_code(row: dict[str, Any]) -> str:
    value = str(row.get("position") or "").upper()
    return value if value in FALLBACK_PRIORS else "MID"


def mean(rows: Iterable[dict[str, Any]], field: str, default: float = 0) -> float:
    materialised = list(rows)
    return (
        sum(number(row.get(field)) for row in materialised) / len(materialised)
        if materialised
        else default
    )


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def fixture_opponents(rows: list[dict[str, Any]]) -> dict[tuple[int, str], str]:
    by_fixture: dict[int, set[str]] = defaultdict(set)
    for row in rows:
        fixture = integer(row.get("fixture"))
        team = str(row.get("team") or "")
        if fixture and team:
            by_fixture[fixture].add(team)
    result: dict[tuple[int, str], str] = {}
    for fixture, teams in by_fixture.items():
        if len(teams) != 2:
            continue
        for team in teams:
            result[(fixture, team)] = next(item for item in teams if item != team)
    return result


def completed_team_matches(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    opponents = fixture_opponents(rows)
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(integer(row.get("fixture")), str(row.get("team") or ""))].append(row)
    matches = []
    for (fixture, team), team_rows in grouped.items():
        if not fixture or not team:
            continue
        active = [row for row in team_rows if number(row.get("minutes")) > 0]
        xg_against_values = [number(row.get("expected_goals_conceded")) for row in active]
        matches.append(
            {
                "fixture": fixture,
                "team": team,
                "opponent": opponents.get((fixture, team), ""),
                "xg_for": sum(number(row.get("expected_goals")) for row in active),
                "xg_against": max(xg_against_values, default=0),
                "goals_for": sum(number(row.get("goals_scored")) for row in active),
            }
        )
    return matches


def team_context(
    team: str,
    opponent: str,
    was_home: bool,
    histories: dict[str, list[dict[str, Any]]],
) -> tuple[float, float]:
    team_rows = histories.get(team, [])[-6:]
    opponent_rows = histories.get(opponent, [])[-6:]
    league_rows = [row for rows in histories.values() for row in rows[-6:]]
    league_xg = mean(league_rows, "xg_for", 1.35) or 1.35
    team_attack = mean(team_rows, "xg_for", league_xg) or league_xg
    opponent_defence = mean(opponent_rows, "xg_against", league_xg) or league_xg
    attack_factor = math.sqrt(
        clamp(team_attack / league_xg, 0.4, 2.5)
        * clamp(opponent_defence / league_xg, 0.4, 2.5)
    )
    attack_factor *= 1.06 if was_home else 0.94
    attack_factor = clamp(attack_factor, 0.55, 1.65)

    team_defence = mean(team_rows, "xg_against", league_xg) or league_xg
    opponent_attack = mean(opponent_rows, "xg_for", league_xg) or league_xg
    expected_against = (team_defence + opponent_attack) / 2
    expected_against *= 0.94 if was_home else 1.06
    clean_sheet_probability = clamp(math.exp(-max(0.15, expected_against)), 0.04, 0.72)
    return attack_factor, clean_sheet_probability


def blended_rate(player_value: float, minutes: float, prior_value: float) -> float:
    weight = clamp(minutes / (minutes + 720), 0, 1)
    return player_value * weight + prior_value * (1 - weight)


def fixture_prediction(
    row: dict[str, Any],
    history: list[dict[str, Any]],
    team_histories: dict[str, list[dict[str, Any]]],
    opponent: str,
    *,
    simulations: int,
) -> dict[str, Any]:
    position = position_code(row)
    prior = FALLBACK_PRIORS[position]
    metrics_3 = recent_metrics(history, 3)
    metrics_6 = recent_metrics(history, 6)
    metrics_10 = recent_metrics(history, 10)
    average_minutes = 0.7 * number(metrics_6.get("average_minutes_6")) + 0.3 * number(
        metrics_3.get("average_minutes_3")
    )
    start_probability = clamp(
        0.7 * number(metrics_6.get("start_rate_6"))
        + 0.3 * number(metrics_3.get("start_rate_3")),
        0,
        1,
    )
    appearance_probability = clamp(
        max(
            start_probability,
            0.7 * number(metrics_6.get("appearance_rate_6"))
            + 0.3 * number(metrics_3.get("appearance_rate_3")),
        ),
        0,
        1,
    )
    minutes_10 = number(metrics_10.get("minutes_10"))
    was_home = truthy(row.get("was_home"))
    attack_factor, clean_sheet_probability = team_context(
        str(row.get("team") or ""), opponent, was_home, team_histories
    )

    def rate(field: str) -> float:
        return blended_rate(
            number(metrics_10.get(f"{field}_10")), minutes_10, number(prior.get(field))
        )

    inputs = {
        "position": position,
        "appearance_probability": appearance_probability,
        "start_probability": start_probability,
        "expected_minutes": clamp(average_minutes, 0, 90),
        "minutes_deviation": max(6, number(metrics_6.get("minutes_standard_deviation_6"))),
        "xg_per_90": rate("xg_per_90") * attack_factor,
        "xa_per_90": rate("xa_per_90") * attack_factor,
        "clean_sheet_probability": clean_sheet_probability,
        "saves_per_90": rate("saves_per_90"),
        "bonus_per_90": rate("bonus_per_90"),
        "defensive_contribution_per_90": rate("defensive_contribution_per_90"),
        "yellow_cards_per_90": rate("yellow_cards_per_90"),
        "red_cards_per_90": rate("red_cards_per_90"),
        "own_goals_per_90": rate("own_goals_per_90"),
        "penalties_missed_per_90": rate("penalties_missed_per_90"),
        "penalties_saved_per_90": rate("penalties_saved_per_90"),
    }
    # Defensive-contribution points did not exist in the seasons under test.
    inputs["defensive_contribution_per_90"] = 0
    return simulate_player_fixture(
        inputs,
        simulations=simulations,
        seed_parts=(row.get("season"), row.get("gameweek"), row.get("fixture"), player_key(row)),
    )


def walk_forward_season(
    season_rows: list[dict[str, Any]], *, simulations: int = BACKTEST_SIMULATIONS
) -> list[dict[str, Any]]:
    by_gameweek: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in season_rows:
        by_gameweek[integer(row.get("gameweek"))].append(row)
    player_histories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    team_histories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    position_totals: dict[str, list[float]] = defaultdict(list)
    predictions: list[dict[str, Any]] = []

    for gameweek in sorted(by_gameweek):
        rows = by_gameweek[gameweek]
        opponents = fixture_opponents(rows)
        player_fixture_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            player_fixture_rows[player_key(row)].append(row)

        for key, target_rows in player_fixture_rows.items():
            history = player_histories.get(key, [])
            if len(history) < MINIMUM_PRIOR_FIXTURES:
                continue
            recent = history[-3:]
            if not any(number(row.get("minutes")) > 0 for row in recent):
                continue
            sample = target_rows[0]
            position = position_code(sample)
            simulation_rows = []
            for target in target_rows:
                opponent = opponents.get(
                    (integer(target.get("fixture")), str(target.get("team") or "")), ""
                )
                simulation_rows.append(
                    fixture_prediction(
                        target,
                        history,
                        team_histories,
                        opponent,
                        simulations=simulations,
                    )
                )
            combined_samples = [
                sum(result["points_samples"][index] for result in simulation_rows)
                for index in range(simulations)
            ]
            actual_points = sum(number(row.get("total_points")) for row in target_rows)
            actual_minutes = sum(number(row.get("minutes")) for row in target_rows)
            predicted_minutes = sum(
                number(result.get("expected_minutes_simulated")) for result in simulation_rows
            )
            history_points = [number(row.get("total_points")) for row in history]
            position_average = (
                sum(position_totals[position]) / len(position_totals[position])
                if position_totals[position]
                else 2.5
            )
            prediction = {
                "season": sample.get("season"),
                "gameweek": gameweek,
                "player_key": key,
                "player_name": sample.get("player_name"),
                "position": position,
                "team": sample.get("team"),
                "fixture_count": len(target_rows),
                "was_home": all(truthy(row.get("was_home")) for row in target_rows),
                "eligible_reason": "appeared_in_last_3_and_at_least_3_prior_fixture_rows",
                "prior_fixture_rows": len(history),
                "actual_minutes": round(actual_minutes, 2),
                "actual_points": round(actual_points, 2),
                "position_average_prediction": round(position_average * len(target_rows), 4),
                "season_average_prediction": round(
                    statistics.fmean(history_points) * len(target_rows), 4
                ),
                "last_3_prediction": round(
                    statistics.fmean(history_points[-3:]) * len(target_rows), 4
                ),
                "last_6_prediction": round(
                    statistics.fmean(history_points[-6:]) * len(target_rows), 4
                ),
                "minutes_only_prediction": round(
                    predicted_minutes / 90 * number(FALLBACK_PRIORS[position]["points_per_90"]),
                    4,
                ),
                "player_sim_prediction": round(statistics.fmean(combined_samples), 4),
                "probability_6_plus": round(
                    sum(value >= 6 for value in combined_samples) / simulations, 4
                ),
                "probability_10_plus": round(
                    sum(value >= 10 for value in combined_samples) / simulations, 4
                ),
                "probability_15_plus": round(
                    sum(value >= 15 for value in combined_samples) / simulations, 4
                ),
                "points_p10": percentile(combined_samples, 0.10),
                "points_p50": percentile(combined_samples, 0.50),
                "points_p90": percentile(combined_samples, 0.90),
                "predicted_minutes": round(predicted_minutes, 2),
                "actual_6_plus": int(actual_points >= 6),
                "actual_10_plus": int(actual_points >= 10),
                "actual_15_plus": int(actual_points >= 15),
            }
            predictions.append(prediction)

        for row in rows:
            key = player_key(row)
            player_histories[key].append(row)
            position_totals[position_code(row)].append(number(row.get("total_points")))
        for match in completed_team_matches(rows):
            team_histories[str(match["team"])].append(match)

    return predictions


def linear_calibration(rows: list[dict[str, Any]]) -> dict[str, float]:
    x = [number(row.get("player_sim_prediction")) for row in rows]
    y = [number(row.get("actual_points")) for row in rows]
    x_mean = statistics.fmean(x)
    y_mean = statistics.fmean(y)
    variance = sum((value - x_mean) ** 2 for value in x)
    slope = (
        sum((left - x_mean) * (right - y_mean) for left, right in zip(x, y)) / variance
        if variance
        else 1
    )
    slope = clamp(slope, 0.25, 1.5)
    intercept = clamp(y_mean - slope * x_mean, -2, 2)
    return {"intercept": round(intercept, 6), "slope": round(slope, 6)}


def probability_scales(rows: list[dict[str, Any]]) -> dict[str, float]:
    scales = {}
    for threshold in (6, 10, 15):
        predicted = statistics.fmean(
            number(row.get(f"probability_{threshold}_plus")) for row in rows
        )
        observed = statistics.fmean(number(row.get(f"actual_{threshold}_plus")) for row in rows)
        scales[str(threshold)] = round(clamp(observed / predicted if predicted else 1, 0.25, 4), 6)
    return scales


def apply_calibration(
    rows: list[dict[str, Any]], linear: dict[str, float], scales: dict[str, float]
) -> None:
    for row in rows:
        row["calibrated_player_sim_prediction"] = round(
            linear["intercept"] + linear["slope"] * number(row.get("player_sim_prediction")), 4
        )
        for threshold in (6, 10, 15):
            row[f"calibrated_probability_{threshold}_plus"] = round(
                clamp(
                    number(row.get(f"probability_{threshold}_plus")) * scales[str(threshold)],
                    0,
                    1,
                ),
                4,
            )


def ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    output = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[index][1]:
            end += 1
        rank = (index + end) / 2 + 1
        for position in range(index, end + 1):
            output[ordered[position][0]] = rank
        index = end + 1
    return output


def correlation(left: list[float], right: list[float]) -> float:
    if len(left) < 2:
        return 0
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    denominator = math.sqrt(
        sum((a - left_mean) ** 2 for a in left)
        * sum((b - right_mean) ** 2 for b in right)
    )
    return numerator / denominator if denominator else 0


def grouped_metrics(rows: list[dict[str, Any]], model: str) -> dict[str, Any]:
    field = MODEL_FIELDS[model]
    errors = [number(row.get(field)) - number(row.get("actual_points")) for row in rows]
    by_gameweek: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_gameweek[(str(row.get("season")), integer(row.get("gameweek")))].append(row)
    spearman = []
    top_10 = []
    top_25 = []
    captain_regret = []
    for group in by_gameweek.values():
        predicted = [number(row.get(field)) for row in group]
        actual = [number(row.get("actual_points")) for row in group]
        spearman.append(correlation(ranks(predicted), ranks(actual)))
        for size, destination in ((10, top_10), (25, top_25)):
            effective = min(size, len(group))
            predicted_top = {
                id(row) for row in sorted(group, key=lambda item: number(item.get(field)), reverse=True)[:effective]
            }
            actual_top = {
                id(row) for row in sorted(group, key=lambda item: number(item.get("actual_points")), reverse=True)[:effective]
            }
            destination.append(len(predicted_top & actual_top) / effective if effective else 0)
        captain = max(group, key=lambda item: number(item.get(field)))
        captain_regret.append(
            max(number(row.get("actual_points")) for row in group)
            - number(captain.get("actual_points"))
        )
    result = {
        "model": model,
        "rows": len(rows),
        "gameweeks": len(by_gameweek),
        "mae": round(statistics.fmean(abs(error) for error in errors), 4),
        "rmse": round(math.sqrt(statistics.fmean(error * error for error in errors)), 4),
        "bias": round(statistics.fmean(errors), 4),
        "mean_gameweek_spearman": round(statistics.fmean(spearman), 4),
        "top_10_hit_rate": round(statistics.fmean(top_10), 4),
        "top_25_hit_rate": round(statistics.fmean(top_25), 4),
        "mean_captaincy_regret": round(statistics.fmean(captain_regret), 4),
    }
    if model in {"player_sim", "calibrated_player_sim"}:
        prefix = "calibrated_" if model == "calibrated_player_sim" else ""
        for threshold in (6, 10, 15):
            probability_field = f"{prefix}probability_{threshold}_plus"
            result[f"brier_{threshold}_plus"] = round(
                statistics.fmean(
                    (number(row.get(probability_field)) - number(row.get(f"actual_{threshold}_plus"))) ** 2
                    for row in rows
                ),
                5,
            )
    return result


def gameweek_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("season")), integer(row.get("gameweek")))].append(row)
    output = []
    for (season, gameweek), group in sorted(grouped.items()):
        metrics = grouped_metrics(group, "player_sim")
        output.append({"season": season, "gameweek": gameweek, **metrics})
    return output


def probability_calibration_bins(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for model, prefix in (("player_sim", ""), ("calibrated_player_sim", "calibrated_")):
        for threshold in (6, 10, 15):
            grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
            probability_field = f"{prefix}probability_{threshold}_plus"
            for row in rows:
                probability = clamp(number(row.get(probability_field)), 0, 1)
                grouped[min(9, int(probability * 10))].append(row)
            for bin_number, bin_rows in sorted(grouped.items()):
                predicted = statistics.fmean(
                    number(row.get(probability_field)) for row in bin_rows
                )
                observed = statistics.fmean(
                    number(row.get(f"actual_{threshold}_plus")) for row in bin_rows
                )
                output.append(
                    {
                        "model": model,
                        "threshold": threshold,
                        "probability_bin_lower": round(bin_number / 10, 1),
                        "probability_bin_upper": round((bin_number + 1) / 10, 1),
                        "rows": len(bin_rows),
                        "mean_predicted_probability": round(predicted, 5),
                        "observed_return_rate": round(observed, 5),
                        "absolute_calibration_gap": round(abs(predicted - observed), 5),
                    }
                )
    return output


def write_gzip_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                writer = csv.DictWriter(text, fieldnames=PREDICTION_FIELDS, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)


def run_backtest(
    data_dir: Path,
    seasons: list[str] | None = None,
    *,
    simulations: int = BACKTEST_SIMULATIONS,
) -> dict[str, Any]:
    seasons = seasons or DEFAULT_SEASONS
    historical_path = data_dir / "history" / "historical_player_gameweeks.csv.gz"
    rows = read_historical(historical_path, seasons)
    by_season: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_season[str(row.get("season"))].append(row)
    predictions = []
    for season in seasons:
        predictions.extend(
            walk_forward_season(by_season.get(season, []), simulations=simulations)
        )
    development = [row for row in predictions if row.get("season") in DEVELOPMENT_SEASONS]
    held_out = [row for row in predictions if row.get("season") == HELD_OUT_SEASON]
    linear = linear_calibration(development)
    scales = probability_scales(development)
    apply_calibration(predictions, linear, scales)

    comparison = [grouped_metrics(held_out, model) for model in MODEL_FIELDS]
    development_comparison = [grouped_metrics(development, model) for model in MODEL_FIELDS]
    raw = next(row for row in comparison if row["model"] == "player_sim")
    calibrated = next(row for row in comparison if row["model"] == "calibrated_player_sim")
    baselines = [
        row
        for row in comparison
        if row["model"] not in {"player_sim", "calibrated_player_sim"}
    ]
    best_baseline_mae = min(baselines, key=lambda row: row["mae"])
    best_baseline_rank = max(baselines, key=lambda row: row["mean_gameweek_spearman"])
    calibration_report = {
        "generated_at": utc_now(),
        "model_version": MODEL_VERSION,
        "development_seasons": DEVELOPMENT_SEASONS,
        "held_out_season": HELD_OUT_SEASON,
        "development_rows": len(development),
        "held_out_rows": len(held_out),
        "expected_points_calibration": linear,
        "probability_multipliers": scales,
        "held_out_raw_metrics": raw,
        "held_out_calibrated_metrics": calibrated,
        "expected_points_calibration_recommended": calibrated["mae"] < raw["mae"],
        "held_out_mae_change": round(calibrated["mae"] - raw["mae"], 4),
        "probability_calibration_recommended": {
            str(threshold): calibrated[f"brier_{threshold}_plus"]
            < raw[f"brier_{threshold}_plus"]
            for threshold in (6, 10, 15)
        },
        "methodology": "All calibration parameters were fitted only on the development seasons and assessed on 2024/25.",
    }
    success = {
        "beats_best_baseline_mae": raw["mae"] < best_baseline_mae["mae"],
        "best_baseline_mae_model": best_baseline_mae["model"],
        "best_baseline_mae": best_baseline_mae["mae"],
        "beats_best_baseline_rank_correlation": raw["mean_gameweek_spearman"]
        > best_baseline_rank["mean_gameweek_spearman"],
        "best_baseline_rank_model": best_baseline_rank["model"],
        "best_baseline_rank_correlation": best_baseline_rank["mean_gameweek_spearman"],
        "calibration_improves_held_out_mae": calibrated["mae"] < raw["mae"],
        "calibration_improves_all_probability_brier_scores": all(
            calibration_report["probability_calibration_recommended"].values()
        ),
    }
    summary = {
        "generated_at": utc_now(),
        "model_version": MODEL_VERSION,
        "seasons": seasons,
        "development_seasons": DEVELOPMENT_SEASONS,
        "held_out_season": HELD_OUT_SEASON,
        "historical_source_rows": len(rows),
        "eligible_prediction_rows": len(predictions),
        "backtested_gameweeks": len(
            {(row.get("season"), row.get("gameweek")) for row in predictions}
        ),
        "simulations_per_player_fixture": simulations,
        "eligibility": "At least three prior fixture rows and at least one appearance in the last three fixtures.",
        "held_out_player_sim_metrics": raw,
        "held_out_calibrated_metrics": calibrated,
        "success_criteria": success,
        "limitations": [
            "The historical archive does not contain timestamped qualitative observations, so only the quantitative model is backtested.",
            "Players are evaluated only after three prior fixture rows, excluding early-season and immediate new-signing decisions.",
            "Historical team context is reconstructed from official player-level expected statistics rather than betting markets.",
            "The simulator uses simplified bonus and disciplinary-event distributions.",
        ],
    }

    backtest_dir = data_dir / "backtests"
    model_dir = data_dir / "model"
    write_gzip_csv(backtest_dir / "backtest_player_predictions.csv.gz", predictions)
    write_csv(
        backtest_dir / "backtest_gameweeks.csv",
        gameweek_metrics(predictions),
        [
            "season",
            "gameweek",
            "model",
            "rows",
            "gameweeks",
            "mae",
            "rmse",
            "bias",
            "mean_gameweek_spearman",
            "top_10_hit_rate",
            "top_25_hit_rate",
            "mean_captaincy_regret",
            "brier_6_plus",
            "brier_10_plus",
            "brier_15_plus",
        ],
    )
    metric_rows = []
    for scope, scoped_rows in (
        ("development", development),
        ("held_out", held_out),
        ("all", predictions),
    ):
        for model in MODEL_FIELDS:
            metric_rows.append({"scope": scope, **grouped_metrics(scoped_rows, model)})
    for season in seasons:
        season_prediction_rows = [row for row in predictions if row.get("season") == season]
        metric_rows.append(
            {
                "scope": f"season_{season}",
                **grouped_metrics(season_prediction_rows, "player_sim"),
            }
        )
    for position in ("GK", "DEF", "MID", "FWD"):
        position_rows = [row for row in held_out if row.get("position") == position]
        metric_rows.append(
            {"scope": f"held_out_position_{position}", **grouped_metrics(position_rows, "player_sim")}
        )
    for venue in (True, False):
        venue_rows = [row for row in held_out if bool(row.get("was_home")) is venue]
        metric_rows.append(
            {
                "scope": "held_out_home" if venue else "held_out_away",
                **grouped_metrics(venue_rows, "player_sim"),
            }
        )
    metric_fields = ["scope", *list(metric_rows[0].keys())]
    metric_fields = list(dict.fromkeys(metric_fields + sorted({key for row in metric_rows for key in row})))
    write_csv(backtest_dir / "backtest_metrics.csv", metric_rows, metric_fields)
    comparison_fields = list(
        dict.fromkeys(
            ["model"] + sorted({key for row in comparison for key in row if key != "model"})
        )
    )
    write_csv(backtest_dir / "model_comparison.csv", comparison, comparison_fields)
    write_csv(
        backtest_dir / "development_model_comparison.csv",
        development_comparison,
        comparison_fields,
    )
    calibration_bin_rows = probability_calibration_bins(held_out)
    write_csv(
        backtest_dir / "probability_calibration_bins.csv",
        calibration_bin_rows,
        list(calibration_bin_rows[0].keys()),
    )
    write_json(backtest_dir / "backtest_summary.json", summary)
    write_json(backtest_dir / "calibration_report.json", calibration_report)
    write_json(
        model_dir / "candidate_calibration_parameters.json",
        {
            "generated_at": utc_now(),
            "status": "candidate_not_applied_to_live_model",
            "fitted_on": DEVELOPMENT_SEASONS,
            "tested_on": HELD_OUT_SEASON,
            "expected_points": linear,
            "probability_multipliers": scales,
            "recommendations": {
                "expected_points": calibration_report[
                    "expected_points_calibration_recommended"
                ],
                "probabilities": calibration_report[
                    "probability_calibration_recommended"
                ],
            },
        },
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run leakage-safe historical FPL backtests")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--seasons", nargs="*", default=DEFAULT_SEASONS)
    parser.add_argument("--simulations", type=int, default=BACKTEST_SIMULATIONS)
    args = parser.parse_args()
    print(
        json.dumps(
            run_backtest(args.data_dir, args.seasons, simulations=args.simulations), indent=2
        )
    )


if __name__ == "__main__":
    main()
