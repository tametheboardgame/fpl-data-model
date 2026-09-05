from __future__ import annotations

import csv
import gzip
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

from src.backtest_fpl_model import apply_hybrid, grouped_metrics, integer, number
from src.build_fpl_model import FALLBACK_PRIORS


POINT_WEIGHT = 0.2
PROBABILITY_WEIGHTS = {"6": 0.5, "10": 0.4, "15": 1.0}
HELD_OUT = "2024-25"
PRIOR_SEASON = "2023-24"


def read_gzip_csv(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def prior_usage(history_path: Path) -> dict[str, dict[str, float]]:
    rows = read_gzip_csv(history_path)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row.get("season") != PRIOR_SEASON:
            continue
        name = str(row.get("player_name") or "").strip().casefold()
        if name:
            grouped[name].append(row)
    output: dict[str, dict[str, float]] = {}
    for name, player_rows in grouped.items():
        minutes = sum(number(row.get("minutes")) for row in player_rows)
        starts = sum(
            number(row.get("starts")) > 0 or number(row.get("minutes")) >= 60
            for row in player_rows
        )
        output[name] = {
            "minutes": minutes,
            "start_rate": max(0.0, min(1.0, starts / 38)),
        }
    return output


def directional_divergence(player_rate: float, position_rate: float) -> float:
    if player_rate >= position_rate:
        denominator = max(1e-9, 1.0 - position_rate)
        return max(0.0, min(1.0, (player_rate - position_rate) / denominator))
    denominator = max(1e-9, position_rate)
    return max(0.0, min(1.0, (position_rate - player_rate) / denominator))


def signal_weight(row: dict[str, str], usage: dict[str, dict[str, float]]) -> float:
    prior_rows = integer(row.get("prior_fixture_rows"))
    if prior_rows < 3 or prior_rows >= 6:
        return 0.0
    info = usage.get(str(row.get("player_name") or "").strip().casefold())
    if not info:
        return 0.0
    position = str(row.get("position") or "MID")
    position_rate = number(FALLBACK_PRIORS.get(position, FALLBACK_PRIORS["MID"]).get("start_rate"))
    evidence = max(0.0, min(1.0, number(info.get("minutes")) / (38 * 60)))
    divergence = directional_divergence(number(info.get("start_rate")), position_rate)
    time_weight = math.sqrt(max(0.0, min(1.0, 1.0 - prior_rows / 6.0)))
    return evidence * divergence * time_weight


def weighted_mae(rows: list[dict[str, str]], prediction_field: str, actual_field: str, usage: dict[str, dict[str, float]]) -> dict[str, float]:
    weighted_error = 0.0
    total_weight = 0.0
    contributing_rows = 0
    for row in rows:
        weight = signal_weight(row, usage)
        if weight <= 0:
            continue
        weighted_error += weight * abs(number(row.get(prediction_field)) - number(row.get(actual_field)))
        total_weight += weight
        contributing_rows += 1
    return {
        "mae": weighted_error / total_weight if total_weight else 0.0,
        "weight": total_weight,
        "rows": contributing_rows,
    }


def held_out(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("season") == HELD_OUT]


def main() -> None:
    baseline_rows = read_gzip_csv(Path(sys.argv[1]))
    candidate_rows = read_gzip_csv(Path(sys.argv[2]))
    usage = prior_usage(Path(sys.argv[3]))

    apply_hybrid(baseline_rows, POINT_WEIGHT, PROBABILITY_WEIGHTS)
    apply_hybrid(candidate_rows, POINT_WEIGHT, PROBABILITY_WEIGHTS)
    baseline = held_out(baseline_rows)
    candidate = held_out(candidate_rows)

    baseline_full = grouped_metrics(baseline, "hybrid_sim")
    candidate_full = grouped_metrics(candidate, "hybrid_sim")
    baseline_signal_points = weighted_mae(baseline, "hybrid_sim_prediction", "actual_points", usage)
    candidate_signal_points = weighted_mae(candidate, "hybrid_sim_prediction", "actual_points", usage)
    baseline_signal_minutes = weighted_mae(baseline, "component_predicted_minutes", "actual_minutes", usage)
    candidate_signal_minutes = weighted_mae(candidate, "component_predicted_minutes", "actual_minutes", usage)

    criteria = {
        "full_mae_within_0_2pct_of_production": float(candidate_full["mae"]) <= float(baseline_full["mae"]) * 1.002,
        "full_rmse_within_0_2pct_of_production": float(candidate_full["rmse"]) <= float(baseline_full["rmse"]) * 1.002,
        "full_rank_within_0_002_of_production": float(candidate_full["mean_gameweek_spearman"]) >= float(baseline_full["mean_gameweek_spearman"]) - 0.002,
        "full_top10_within_one_hit_per_35gw_of_production": float(candidate_full["top_10_hit_rate"]) >= float(baseline_full["top_10_hit_rate"]) - 0.0029,
        "informative_role_weighted_points_mae_improves": candidate_signal_points["mae"] < baseline_signal_points["mae"],
        "informative_role_weighted_minutes_mae_improves": candidate_signal_minutes["mae"] < baseline_signal_minutes["mae"],
    }
    print(json.dumps({
        "production_weights": {"point_weight": POINT_WEIGHT, "probability_weights": PROBABILITY_WEIGHTS},
        "baseline_full": baseline_full,
        "candidate_full": candidate_full,
        "baseline_informative_role_points": baseline_signal_points,
        "candidate_informative_role_points": candidate_signal_points,
        "baseline_informative_role_minutes": baseline_signal_minutes,
        "candidate_informative_role_minutes": candidate_signal_minutes,
        "criteria": criteria,
        "informative_role_revalidation_passed": all(criteria.values()),
    }, indent=2))


if __name__ == "__main__":
    main()
