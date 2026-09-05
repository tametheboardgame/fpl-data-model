from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from src.backtest_fpl_model import (
    apply_hybrid,
    grouped_metrics,
    read_historical,
    walk_forward_season,
)
from src.component_player_simulator import COMPONENT_MODEL_VERSION
from src.build_fpl_model import MODEL_VERSION
from src.update_fpl_data import utc_now


HOLDOUT_SEASON = "2025-26"
PRIOR_SEASON = "2024-25"
SIMULATIONS = 300
FIXED_POINT_WEIGHT = 0.2
FIXED_PROBABILITY_WEIGHTS = {"6": 0.5, "10": 0.4, "15": 1.0}
RANK_TOLERANCE = 0.002
MINIMUM_MAE_IMPROVEMENT = 0.005


def metric_delta(candidate: dict[str, Any], control: dict[str, Any], field: str) -> float:
    return round(float(candidate[field]) - float(control[field]), 6)


def evaluate(data_dir: Path) -> dict[str, Any]:
    history_path = data_dir / "history" / "historical_player_gameweeks.csv.gz"
    rows = read_historical(history_path, [PRIOR_SEASON, HOLDOUT_SEASON])
    prior_rows = [row for row in rows if row.get("season") == PRIOR_SEASON]
    holdout_rows = [row for row in rows if row.get("season") == HOLDOUT_SEASON]
    if not prior_rows or not holdout_rows:
        raise RuntimeError("Both 2024/25 prior context and 2025/26 holdout rows are required")

    predictions = walk_forward_season(
        holdout_rows,
        prior_rows,
        simulations=SIMULATIONS,
    )
    if not predictions:
        raise RuntimeError("The frozen holdout produced no eligible predictions")

    # Frozen before the 2025/26 outcomes are inspected. There is deliberately no
    # fitting, grid search, calibration selection, or parameter selection here.
    apply_hybrid(predictions, FIXED_POINT_WEIGHT, FIXED_PROBABILITY_WEIGHTS)

    control = grouped_metrics(predictions, "player_sim")
    component = grouped_metrics(predictions, "component_sim")
    hybrid = grouped_metrics(predictions, "hybrid_sim")

    probability_not_worse = {
        str(threshold): hybrid[f"brier_{threshold}_plus"]
        <= control[f"brier_{threshold}_plus"]
        for threshold in (6, 10, 15)
    }
    gates = {
        "rank_correlation_within_tolerance": hybrid["mean_gameweek_spearman"]
        >= control["mean_gameweek_spearman"] - RANK_TOLERANCE,
        "mae_improves_by_at_least_half_percent": hybrid["mae"]
        <= control["mae"] * (1 - MINIMUM_MAE_IMPROVEMENT),
        "rmse_not_worse": hybrid["rmse"] <= control["rmse"],
        "top_10_hit_rate_not_worse": hybrid["top_10_hit_rate"]
        >= control["top_10_hit_rate"],
        "captaincy_regret_not_worse": hybrid["mean_captaincy_regret"]
        <= control["mean_captaincy_regret"],
        "at_least_two_probability_brier_scores_not_worse": sum(
            probability_not_worse.values()
        )
        >= 2,
    }

    early = [
        row
        for row in predictions
        if 3 <= int(float(row.get("prior_fixture_rows") or 0)) <= 5
    ]
    strong_previous_role = [
        row
        for row in early
        if float(row.get("previous_season_minutes") or 0) >= 1800
    ]

    def diagnostic(items: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not items:
            return None
        return {
            "rows": len(items),
            "control": grouped_metrics(items, "player_sim"),
            "hybrid": grouped_metrics(items, "hybrid_sim"),
        }

    manifest_path = data_dir / "history" / "historical_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}

    return {
        "generated_at": utc_now(),
        "evaluation": "one_shot_frozen_final_holdout",
        "holdout_season": HOLDOUT_SEASON,
        "prior_context_season": PRIOR_SEASON,
        "architecture_frozen_before_holdout": True,
        "source_commit": os.environ.get("GITHUB_SHA"),
        "control_model_version": MODEL_VERSION,
        "component_model_version": COMPONENT_MODEL_VERSION,
        "simulations_per_player_fixture": SIMULATIONS,
        "fixed_parameters": {
            "point_weight": FIXED_POINT_WEIGHT,
            "probability_weights": FIXED_PROBABILITY_WEIGHTS,
            "rank_tolerance": RANK_TOLERANCE,
            "minimum_relative_mae_improvement": MINIMUM_MAE_IMPROVEMENT,
        },
        "prohibited_holdout_operations": [
            "weight_selection",
            "parameter_fitting",
            "calibration_fitting",
            "post_result_threshold_changes",
        ],
        "historical_source": {
            "content_sha256": manifest.get("content_sha256"),
            "season_row_counts": manifest.get("season_row_counts"),
            "total_rows": manifest.get("total_rows"),
        },
        "eligible_prediction_rows": len(predictions),
        "control_metrics": control,
        "component_metrics": component,
        "frozen_hybrid_metrics": hybrid,
        "hybrid_minus_control": {
            field: metric_delta(hybrid, control, field)
            for field in (
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
            )
        },
        "probability_brier_not_worse": probability_not_worse,
        "predeclared_promotion_gates": gates,
        "passes_all_predeclared_gates": all(gates.values()),
        "diagnostics_not_used_for_model_selection": {
            "early_current_season_rows_3_to_5": diagnostic(early),
            "early_rows_with_at_least_1800_previous_season_minutes": diagnostic(
                strong_previous_role
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the frozen ensemble once on 2025/26")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(args.data_dir)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
