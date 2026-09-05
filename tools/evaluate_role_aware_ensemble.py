from __future__ import annotations

import argparse
import csv
import gzip
import json
from pathlib import Path
from typing import Any

from src.backtest_fpl_model import grouped_metrics
from src.build_fpl_model import number


BASE_POINT_WEIGHT = 0.2
BASE_PROBABILITY_WEIGHTS = {"6": 0.5, "10": 0.4, "15": 1.0}
ALPHA_GRID = [0.0, 0.5, 1.0]
RANK_TOLERANCE = 0.002
TOP_10_TOLERANCE = 0.002
FULL_ROLE_EVIDENCE_MINUTES = 38 * 60
MATERIAL_MINUTES_GAP = 20.0


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def role_protection(row: dict[str, Any]) -> float:
    """Strength of evidence that the role-aware control should resist compression.

    This deliberately protects only the failure mode observed in production:
    an early-season component estimate materially below a control estimate that
    is still supported by substantial previous-season playing-time evidence.
    It does not boost a player above the control forecast and fades to zero once
    the live control has six current-season fixtures.
    """

    prior_weight = clamp(number(row.get("control_usage_prior_weight")))
    evidence = clamp(
        number(row.get("previous_season_minutes")) / FULL_ROLE_EVIDENCE_MINUTES
    )
    minutes_gap = max(
        0.0,
        number(row.get("predicted_minutes"))
        - number(row.get("component_predicted_minutes")),
    )
    disagreement = clamp(minutes_gap / MATERIAL_MINUTES_GAP)
    return prior_weight * evidence * disagreement


def apply_role_aware_hybrid(rows: list[dict[str, Any]], alpha: float) -> None:
    alpha = clamp(alpha)
    for row in rows:
        protection = role_protection(row)
        multiplier = 1.0 - alpha * protection
        point_weight = BASE_POINT_WEIGHT * multiplier
        row["role_protection"] = round(protection, 6)
        row["effective_component_point_weight"] = round(point_weight, 6)
        row["hybrid_sim_prediction"] = round(
            (1 - point_weight) * number(row.get("player_sim_prediction"))
            + point_weight * number(row.get("component_sim_prediction")),
            4,
        )
        for threshold in (6, 10, 15):
            probability_weight = BASE_PROBABILITY_WEIGHTS[str(threshold)] * multiplier
            row[f"hybrid_probability_{threshold}_plus"] = round(
                (1 - probability_weight)
                * number(row.get(f"probability_{threshold}_plus"))
                + probability_weight
                * number(row.get(f"component_probability_{threshold}_plus")),
                4,
            )


def evaluate(rows: list[dict[str, Any]], alpha: float) -> dict[str, Any]:
    candidate = [dict(row) for row in rows]
    apply_role_aware_hybrid(candidate, alpha)
    protected = [row for row in candidate if number(row.get("role_protection")) > 0]
    strong = [row for row in candidate if number(row.get("role_protection")) >= 0.25]
    return {
        "alpha": alpha,
        "metrics": grouped_metrics(candidate, "hybrid_sim"),
        "protected_rows": len(protected),
        "mean_effective_component_weight_protected": round(
            sum(number(row.get("effective_component_point_weight")) for row in protected)
            / len(protected),
            6,
        )
        if protected
        else BASE_POINT_WEIGHT,
        "strong_role_rows": len(strong),
        "strong_role_metrics": grouped_metrics(strong, "hybrid_sim") if strong else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--predictions",
        type=Path,
        default=Path("data/backtests/backtest_player_predictions.csv.gz"),
    )
    parser.add_argument(
        "--development-seasons",
        nargs="+",
        default=["2022-23", "2023-24"],
    )
    parser.add_argument("--validation-season", default="2024-25")
    args = parser.parse_args()

    with gzip.open(args.predictions, "rt", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    development = [row for row in rows if row.get("season") in args.development_seasons]
    validation = [row for row in rows if row.get("season") == args.validation_season]

    trials = [evaluate(development, alpha) for alpha in ALPHA_GRID]
    static = next(row for row in trials if row["alpha"] == 0.0)
    static_metrics = static["metrics"]
    safe = [
        row
        for row in trials
        if row["metrics"]["mean_gameweek_spearman"]
        >= static_metrics["mean_gameweek_spearman"] - RANK_TOLERANCE
        and row["metrics"]["top_10_hit_rate"]
        >= static_metrics["top_10_hit_rate"] - TOP_10_TOLERANCE
    ]
    selected = min(
        safe or trials,
        key=lambda row: (
            row["metrics"]["mae"],
            -row["metrics"]["mean_gameweek_spearman"],
            row["alpha"],
        ),
    )
    validation_static = evaluate(validation, 0.0)
    validation_selected = evaluate(validation, selected["alpha"])
    report = {
        "method": "Development-selected attenuation of the existing 0.2 component blend when a well-evidenced early-season control role is materially above component minutes.",
        "development_seasons": args.development_seasons,
        "validation_season": args.validation_season,
        "base_point_weight": BASE_POINT_WEIGHT,
        "base_probability_weights": BASE_PROBABILITY_WEIGHTS,
        "full_role_evidence_minutes": FULL_ROLE_EVIDENCE_MINUTES,
        "material_minutes_gap": MATERIAL_MINUTES_GAP,
        "alpha_grid": ALPHA_GRID,
        "rank_tolerance": RANK_TOLERANCE,
        "top_10_tolerance": TOP_10_TOLERANCE,
        "development_trials": trials,
        "selected_alpha": selected["alpha"],
        "validation_static": validation_static,
        "validation_selected": validation_selected,
        "validation_changes": {
            "mae": round(
                validation_selected["metrics"]["mae"]
                - validation_static["metrics"]["mae"],
                6,
            ),
            "rmse": round(
                validation_selected["metrics"]["rmse"]
                - validation_static["metrics"]["rmse"],
                6,
            ),
            "rank": round(
                validation_selected["metrics"]["mean_gameweek_spearman"]
                - validation_static["metrics"]["mean_gameweek_spearman"],
                6,
            ),
            "top_10": round(
                validation_selected["metrics"]["top_10_hit_rate"]
                - validation_static["metrics"]["top_10_hit_rate"],
                6,
            ),
            "captaincy_regret": round(
                validation_selected["metrics"]["mean_captaincy_regret"]
                - validation_static["metrics"]["mean_captaincy_regret"],
                6,
            ),
        },
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
