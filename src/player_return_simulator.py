from __future__ import annotations

import hashlib
import math
import random
from typing import Any


SCORING_RULES_VERSION = "fpl-2025-26"
DEFAULT_SIMULATIONS = 600
GOAL_POINTS = {"GK": 6, "DEF": 6, "MID": 5, "FWD": 4}
CLEAN_SHEET_POINTS = {"GK": 4, "DEF": 4, "MID": 1, "FWD": 0}
DEFENSIVE_CONTRIBUTION_THRESHOLD = {"GK": 0, "DEF": 10, "MID": 12, "FWD": 12}


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def stable_seed(*parts: Any) -> int:
    text = "|".join(str(part) for part in parts)
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def poisson(rng: random.Random, expected: float) -> int:
    expected = max(0.0, expected)
    if expected == 0:
        return 0
    uniform = rng.random()
    probability = math.exp(-expected)
    cumulative = probability
    value = 0
    while uniform > cumulative:
        value += 1
        probability *= expected / value
        cumulative += probability
    return value


def percentile(values: list[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * clamp(probability, 0, 1))
    return ordered[index]


def simulate_player_fixture(
    inputs: dict[str, Any],
    *,
    simulations: int = DEFAULT_SIMULATIONS,
    seed_parts: tuple[Any, ...] = (),
) -> dict[str, Any]:
    rng = random.Random(stable_seed(SCORING_RULES_VERSION, *seed_parts))
    position = str(inputs.get("position") or "MID")
    appearance_probability = clamp(float(inputs.get("appearance_probability") or 0), 0, 1)
    start_probability = clamp(
        float(inputs.get("start_probability") or 0), 0, appearance_probability
    )
    expected_minutes = clamp(float(inputs.get("expected_minutes") or 0), 0, 90)
    minutes_deviation = clamp(float(inputs.get("minutes_deviation") or 12), 4, 30)
    substitute_mean = 18.0
    substitute_probability = max(0.0, appearance_probability - start_probability)
    starter_mean = (
        (expected_minutes - substitute_probability * substitute_mean) / start_probability
        if start_probability
        else 75.0
    )
    starter_mean = clamp(starter_mean, 50, 90)
    conditional_start_probability = (
        start_probability / appearance_probability if appearance_probability else 0
    )
    clean_sheet_probability = clamp(
        float(inputs.get("clean_sheet_probability") or 0), 0, 1
    )
    expected_goals_against = -math.log(max(0.01, clean_sheet_probability))

    points_samples: list[float] = []
    minutes_samples: list[float] = []
    for _ in range(max(1, simulations)):
        if rng.random() >= appearance_probability:
            points_samples.append(0)
            minutes_samples.append(0)
            continue

        starts = rng.random() < conditional_start_probability
        if starts:
            minutes = round(clamp(rng.gauss(starter_mean, minutes_deviation / 2), 1, 90))
        else:
            minutes = round(clamp(rng.gauss(substitute_mean, 8), 1, 45))
        minutes_samples.append(minutes)
        minutes_factor = minutes / 90

        goals = poisson(rng, float(inputs.get("xg_per_90") or 0) * minutes_factor)
        assists = poisson(rng, float(inputs.get("xa_per_90") or 0) * minutes_factor)
        points = 2 if minutes >= 60 else 1
        points += goals * GOAL_POINTS[position]
        points += assists * 3

        if minutes >= 60:
            if rng.random() < clean_sheet_probability:
                points += CLEAN_SHEET_POINTS[position]
                goals_against = 0
            else:
                goals_against = max(1, poisson(rng, expected_goals_against))
            if position in {"GK", "DEF"}:
                points -= goals_against // 2

        if position == "GK":
            saves = poisson(rng, float(inputs.get("saves_per_90") or 0) * minutes_factor)
            points += saves // 3
            points += 5 * poisson(
                rng, float(inputs.get("penalties_saved_per_90") or 0) * minutes_factor
            )

        threshold = DEFENSIVE_CONTRIBUTION_THRESHOLD[position]
        if threshold:
            contributions = poisson(
                rng,
                float(inputs.get("defensive_contribution_per_90") or 0) * minutes_factor,
            )
            if contributions >= threshold:
                points += 2

        points += min(
            3, poisson(rng, float(inputs.get("bonus_per_90") or 0) * minutes_factor)
        )
        points -= poisson(rng, float(inputs.get("yellow_cards_per_90") or 0) * minutes_factor)
        points -= 3 * poisson(
            rng, float(inputs.get("red_cards_per_90") or 0) * minutes_factor
        )
        points -= 2 * poisson(
            rng, float(inputs.get("own_goals_per_90") or 0) * minutes_factor
        )
        points -= 2 * poisson(
            rng, float(inputs.get("penalties_missed_per_90") or 0) * minutes_factor
        )
        points_samples.append(points)

    count = len(points_samples)
    return {
        "scoring_rules_version": SCORING_RULES_VERSION,
        "simulation_count": count,
        "expected_points": sum(points_samples) / count,
        "points_p10": percentile(points_samples, 0.10),
        "points_p50": percentile(points_samples, 0.50),
        "points_p90": percentile(points_samples, 0.90),
        "expected_minutes_simulated": sum(minutes_samples) / count,
        "minutes_p10": percentile(minutes_samples, 0.10),
        "minutes_p50": percentile(minutes_samples, 0.50),
        "minutes_p90": percentile(minutes_samples, 0.90),
        "probability_6_plus": sum(value >= 6 for value in points_samples) / count,
        "probability_10_plus": sum(value >= 10 for value in points_samples) / count,
        "probability_15_plus": sum(value >= 15 for value in points_samples) / count,
        "probability_3_or_fewer": sum(value <= 3 for value in points_samples) / count,
        "points_samples": points_samples,
    }
