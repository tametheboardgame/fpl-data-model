from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.backtest_fpl_model import apply_hybrid, grouped_metrics, read_historical, walk_forward_season


SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25"]
TARGET_SEASONS = ["2022-23", "2023-24", "2024-25"]
SIMULATIONS = 300
CURRENT_POINT_WEIGHT = 0.2
RANK_SAFE_POINT_WEIGHT = 0.0
FIXED_PROBABILITY_WEIGHTS = {"6": 0.5, "10": 0.4, "15": 1.0}


def haul_ranking_metrics(rows: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
    by_gameweek: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_gameweek[int(float(row.get("gameweek") or 0))].append(row)

    output: dict[str, Any] = {}
    for threshold in (6, 10, 15):
        probability_field = (
            f"{prefix}_probability_{threshold}_plus"
            if prefix
            else f"probability_{threshold}_plus"
        )
        actual_field = f"actual_{threshold}_plus"
        for k in (10, 25):
            precisions: list[float] = []
            recalls: list[float] = []
            for gameweek_rows in by_gameweek.values():
                ranked = sorted(
                    gameweek_rows,
                    key=lambda row: float(row.get(probability_field) or 0),
                    reverse=True,
                )
                selected = ranked[:k]
                if not selected:
                    continue
                hits = sum(int(float(row.get(actual_field) or 0)) for row in selected)
                actual_total = sum(
                    int(float(row.get(actual_field) or 0)) for row in gameweek_rows
                )
                precisions.append(hits / len(selected))
                if actual_total:
                    recalls.append(hits / actual_total)
            output[f"{threshold}_plus_precision_at_{k}"] = round(
                sum(precisions) / len(precisions), 5
            ) if precisions else None
            output[f"{threshold}_plus_recall_at_{k}"] = round(
                sum(recalls) / len(recalls), 5
            ) if recalls else None
    return output


def variant(rows: list[dict[str, Any]], point_weight: float) -> list[dict[str, Any]]:
    result = [dict(row) for row in rows]
    apply_hybrid(result, point_weight, FIXED_PROBABILITY_WEIGHTS)
    return result


def evaluate(data_dir: Path) -> dict[str, Any]:
    all_rows = read_historical(
        data_dir / "history" / "historical_player_gameweeks.csv.gz",
        SEASONS,
    )
    by_season: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in all_rows:
        by_season[str(row.get("season"))].append(row)

    reports: dict[str, Any] = {}
    for target in TARGET_SEASONS:
        index = SEASONS.index(target)
        prior = SEASONS[index - 1]
        predictions = walk_forward_season(
            by_season[target],
            by_season[prior],
            simulations=SIMULATIONS,
        )
        current = variant(predictions, CURRENT_POINT_WEIGHT)
        rank_safe = variant(predictions, RANK_SAFE_POINT_WEIGHT)
        control_metrics = grouped_metrics(predictions, "player_sim")
        current_metrics = grouped_metrics(current, "hybrid_sim")
        rank_safe_metrics = grouped_metrics(rank_safe, "hybrid_sim")
        reports[target] = {
            "prior_context_season": prior,
            "rows": len(predictions),
            "control": {
                "metrics": control_metrics,
                "haul_ranking": haul_ranking_metrics(predictions, ""),
            },
            "current_0_2": {
                "metrics": current_metrics,
                "haul_ranking": haul_ranking_metrics(current, "hybrid"),
            },
            "rank_safe_control_mean_component_tails": {
                "metrics": rank_safe_metrics,
                "haul_ranking": haul_ranking_metrics(rank_safe, "hybrid"),
            },
        }

    validation = reports["2024-25"]
    control = validation["control"]["metrics"]
    candidate = validation["rank_safe_control_mean_component_tails"]["metrics"]
    control_haul = validation["control"]["haul_ranking"]
    candidate_haul = validation["rank_safe_control_mean_component_tails"]["haul_ranking"]
    brier_not_worse = {
        str(threshold): candidate[f"brier_{threshold}_plus"]
        <= control[f"brier_{threshold}_plus"]
        for threshold in (6, 10, 15)
    }
    expected_point_fields = (
        "mae",
        "rmse",
        "mean_gameweek_spearman",
        "top_10_hit_rate",
        "top_25_hit_rate",
        "mean_captaincy_regret",
    )
    gates = {
        "expected_point_metrics_identical_to_control": all(
            candidate[field] == control[field] for field in expected_point_fields
        ),
        "at_least_two_probability_briers_not_worse": sum(brier_not_worse.values()) >= 2,
        "ten_plus_precision_at_10_not_worse": (
            candidate_haul["10_plus_precision_at_10"]
            >= control_haul["10_plus_precision_at_10"]
        ),
        "fifteen_plus_precision_at_10_not_worse": (
            candidate_haul["15_plus_precision_at_10"]
            >= control_haul["15_plus_precision_at_10"]
        ),
    }

    return {
        "purpose": (
            "Development-only test of a rank-safe architecture: control expected-points mean "
            "with the already-selected component probability weights retained only for tails."
        ),
        "holdout_2025_26_used": False,
        "parameters": {
            "current_point_weight": CURRENT_POINT_WEIGHT,
            "rank_safe_point_weight": RANK_SAFE_POINT_WEIGHT,
            "fixed_probability_weights": FIXED_PROBABILITY_WEIGHTS,
            "simulations": SIMULATIONS,
        },
        "season_reports": reports,
        "internal_validation_season": "2024-25",
        "internal_validation_brier_not_worse": brier_not_worse,
        "internal_validation_gates": gates,
        "passes_internal_validation_gates": all(gates.values()),
        "governance_note": (
            "2025/26 has already been exposed and is not used for selection or revalidation. "
            "Any architecture selected here requires prospective 2026/27 evidence."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
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
