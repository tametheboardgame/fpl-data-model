from __future__ import annotations

import csv
import gzip
import json
import sys
from pathlib import Path

from src.backtest_fpl_model import apply_hybrid, grouped_metrics, integer


PRODUCTION_POINT_WEIGHT = 0.2
PRODUCTION_PROBABILITY_WEIGHTS = {"6": 0.5, "10": 0.4, "15": 1.0}
HELD_OUT_SEASON = "2024-25"


def read_predictions(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def scope(rows: list[dict[str, str]], *, early: bool) -> list[dict[str, str]]:
    selected = [row for row in rows if row.get("season") == HELD_OUT_SEASON]
    if early:
        selected = [
            row
            for row in selected
            if 3 <= integer(row.get("prior_fixture_rows")) < 6
        ]
    return selected


def fixed_hybrid_metrics(rows: list[dict[str, str]], *, early: bool) -> dict[str, object]:
    apply_hybrid(rows, PRODUCTION_POINT_WEIGHT, PRODUCTION_PROBABILITY_WEIGHTS)
    selected = scope(rows, early=early)
    return grouped_metrics(selected, "hybrid_sim")


def control_metrics(rows: list[dict[str, str]], *, early: bool) -> dict[str, object]:
    return grouped_metrics(scope(rows, early=early), "player_sim")


def rel_change(candidate: float, baseline: float) -> float:
    return (candidate - baseline) / baseline if baseline else 0.0


def main() -> None:
    baseline_path = Path(sys.argv[1])
    candidate_path = Path(sys.argv[2])
    baseline_rows = read_predictions(baseline_path)
    candidate_rows = read_predictions(candidate_path)

    baseline_full = fixed_hybrid_metrics(baseline_rows, early=False)
    candidate_full = fixed_hybrid_metrics(candidate_rows, early=False)
    baseline_early = fixed_hybrid_metrics(baseline_rows, early=True)
    candidate_early = fixed_hybrid_metrics(candidate_rows, early=True)
    candidate_early_control = control_metrics(candidate_rows, early=True)

    criteria = {
        "full_mae_within_0_2pct_of_production": float(candidate_full["mae"])
        <= float(baseline_full["mae"]) * 1.002,
        "full_rmse_within_0_2pct_of_production": float(candidate_full["rmse"])
        <= float(baseline_full["rmse"]) * 1.002,
        "full_rank_within_0_002_of_production": float(candidate_full["mean_gameweek_spearman"])
        >= float(baseline_full["mean_gameweek_spearman"]) - 0.002,
        "full_top10_within_one_hit_per_35gw_of_production": float(candidate_full["top_10_hit_rate"])
        >= float(baseline_full["top_10_hit_rate"]) - 0.0029,
        "early_mae_improves_vs_production": float(candidate_early["mae"])
        < float(baseline_early["mae"]),
        "early_mae_beats_control": float(candidate_early["mae"])
        < float(candidate_early_control["mae"]),
        "early_rank_not_materially_worse_than_production": float(candidate_early["mean_gameweek_spearman"])
        >= float(baseline_early["mean_gameweek_spearman"]) - 0.01,
    }

    report = {
        "production_weights": {
            "point_weight": PRODUCTION_POINT_WEIGHT,
            "probability_weights": PRODUCTION_PROBABILITY_WEIGHTS,
        },
        "baseline_full": baseline_full,
        "candidate_full": candidate_full,
        "candidate_full_relative_mae_change": round(
            rel_change(float(candidate_full["mae"]), float(baseline_full["mae"])), 6
        ),
        "baseline_early": baseline_early,
        "candidate_early": candidate_early,
        "candidate_early_control": candidate_early_control,
        "candidate_early_relative_mae_change_vs_production": round(
            rel_change(float(candidate_early["mae"]), float(baseline_early["mae"])), 6
        ),
        "criteria": criteria,
        "scoped_revalidation_passed": all(criteria.values()),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
