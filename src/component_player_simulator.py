from __future__ import annotations

import math
import random
import statistics
from typing import Any

from src.player_return_simulator import (
    CLEAN_SHEET_POINTS,
    DEFENSIVE_CONTRIBUTION_THRESHOLD,
    GOAL_POINTS,
    SCORING_RULES_VERSION,
    clamp,
    percentile,
    poisson,
    stable_seed,
)


COMPONENT_MODEL_VERSION = "player-sim-3.2-candidate"
STARTER_MINUTES_PRIOR = {"GK": 89.0, "DEF": 82.0, "MID": 78.0, "FWD": 75.0}
SUBSTITUTE_MINUTES_PRIOR = {"GK": 8.0, "DEF": 18.0, "MID": 20.0, "FWD": 19.0}
ATTACK_DISPERSION_SHAPE = {"GK": 8.0, "DEF": 5.0, "MID": 3.0, "FWD": 1.8}
ATTACKING_PRIOR_MINUTES = {"GK": 900.0, "DEF": 720.0, "MID": 540.0, "FWD": 450.0}
COMPONENT_FIELDS = (
    "appearance_points",
    "goal_points",
    "assist_points",
    "clean_sheet_points",
    "goals_conceded_points",
    "save_points",
    "penalty_save_points",
    "defensive_contribution_points",
    "bonus_points",
    "discipline_points",
)


def number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def beta_smoothed_rate(
    observed_rate: float,
    observations: float,
    prior_rate: float,
    *,
    prior_strength: float = 2.0,
) -> float:
    observations = max(0.0, observations)
    return clamp(
        (observed_rate * observations + prior_rate * prior_strength)
        / (observations + prior_strength),
        0,
        1,
    )


def shrunk_mean(
    observed_mean: float,
    observations: float,
    prior_mean: float,
    *,
    prior_strength: float = 2.0,
) -> float:
    observations = max(0.0, observations)
    if observations == 0:
        return prior_mean
    return (
        observed_mean * observations + prior_mean * prior_strength
    ) / (observations + prior_strength)


def blended_attacking_rate(
    feature: dict[str, Any],
    prior: dict[str, Any],
    field: str,
    position: str,
) -> float:
    minutes_6 = number(feature.get("minutes_6"))
    minutes_10 = number(feature.get("minutes_10"))
    rate_6 = number(feature.get(f"{field}_6"))
    rate_10 = number(feature.get(f"{field}_10"))
    if minutes_6 and minutes_10:
        observed = 0.35 * rate_6 + 0.65 * rate_10
    else:
        observed = rate_10 or rate_6
    prior_rate = number(prior.get(field))
    prior_minutes = ATTACKING_PRIOR_MINUTES[position]
    weight = minutes_10 / (minutes_10 + prior_minutes) if minutes_10 else 0
    return max(0.0, observed * weight + prior_rate * (1 - weight))


def build_component_inputs(
    base_inputs: dict[str, Any],
    feature: dict[str, Any],
    prior: dict[str, Any],
) -> dict[str, Any]:
    """Convert rolling evidence into explicit availability, minutes and event components."""
    position = str(base_inputs.get("position") or "MID")
    if position not in STARTER_MINUTES_PRIOR:
        position = "MID"
    availability = clamp(
        number(base_inputs.get("availability_probability"))
        if "availability_probability" in base_inputs
        else 1.0,
        0,
        1,
    )
    fixtures_6 = number(feature.get("fixtures_6"))
    start_rate_6 = number(feature.get("start_rate_6"))
    appearance_rate_6 = number(feature.get("appearance_rate_6"))
    player_start_rate_prior = (
        number(base_inputs.get("player_start_rate_prior"))
        if "player_start_rate_prior" in base_inputs
        else number(prior.get("start_rate"))
    )
    player_appearance_rate_prior = (
        number(base_inputs.get("player_appearance_rate_prior"))
        if "player_appearance_rate_prior" in base_inputs
        else number(prior.get("appearance_rate"))
    )
    usage_prior_strength = max(0.0, 2.0 * (1.0 - fixtures_6 / 6.0))
    if not fixtures_6:
        # At season launch the rolling window is empty. The control layer has
        # already derived player-specific probabilities from the previous
        # season, so retain those rather than collapsing every player to the
        # same positional start and appearance priors.
        start_rate_6 = (
            number(base_inputs.get("start_probability")) / availability
            if availability
            else 0
        )
        appearance_rate_6 = (
            number(base_inputs.get("appearance_probability")) / availability
            if availability
            else 0
        )
    if fixtures_6:
        smoothed_start = beta_smoothed_rate(
            start_rate_6,
            fixtures_6,
            player_start_rate_prior,
            prior_strength=usage_prior_strength,
        )
        smoothed_appearance = beta_smoothed_rate(
            max(start_rate_6, appearance_rate_6),
            fixtures_6,
            max(player_start_rate_prior, player_appearance_rate_prior),
            prior_strength=usage_prior_strength,
        )
    else:
        smoothed_start = start_rate_6
        smoothed_appearance = max(start_rate_6, appearance_rate_6)
    start_probability = availability * smoothed_start
    appearance_probability = availability * max(smoothed_start, smoothed_appearance)

    starts = start_rate_6 * fixtures_6
    appearances = appearance_rate_6 * fixtures_6
    substitute_appearances = max(0.0, appearances - starts)
    starter_minutes_mean = shrunk_mean(
        number(feature.get("starter_average_minutes_6")),
        starts,
        STARTER_MINUTES_PRIOR[position],
    )
    substitute_minutes_mean = shrunk_mean(
        number(feature.get("substitute_average_minutes_6")),
        substitute_appearances,
        SUBSTITUTE_MINUTES_PRIOR[position],
    )
    if not fixtures_6 and start_probability:
        target_minutes = clamp(number(base_inputs.get("expected_minutes")), 0, 90)
        substitute_probability = max(
            0.0,
            appearance_probability - start_probability,
        )
        starter_minutes_mean = clamp(
            (
                target_minutes
                - substitute_probability * substitute_minutes_mean
            )
            / start_probability,
            45,
            90,
        )
    expected_minutes = (
        start_probability * starter_minutes_mean
        + max(0.0, appearance_probability - start_probability)
        * substitute_minutes_mean
    )

    output = {
        **base_inputs,
        "position": position,
        "usage_prior_strength": usage_prior_strength,
        "appearance_probability": clamp(appearance_probability, 0, 1),
        "start_probability": clamp(start_probability, 0, appearance_probability),
        "starter_minutes_mean": clamp(starter_minutes_mean, 45, 90),
        "substitute_minutes_mean": clamp(substitute_minutes_mean, 1, 45),
        "expected_minutes": clamp(expected_minutes, 0, 90),
        "xg_per_90": blended_attacking_rate(feature, prior, "xg_per_90", position),
        "xa_per_90": blended_attacking_rate(feature, prior, "xa_per_90", position),
        "attack_dispersion_shape": ATTACK_DISPERSION_SHAPE[position],
    }
    return output


def simulate_component_player_fixture(
    inputs: dict[str, Any],
    *,
    simulations: int,
    seed_parts: tuple[Any, ...] = (),
    scoring_rules_version: str | None = None,
) -> dict[str, Any]:
    """Simulate auditable FPL scoring components with position-aware tail behaviour."""
    rules_version = scoring_rules_version or SCORING_RULES_VERSION
    rng = random.Random(
        stable_seed(COMPONENT_MODEL_VERSION, rules_version, *seed_parts)
    )
    position = str(inputs.get("position") or "MID")
    if position not in GOAL_POINTS:
        position = "MID"
    appearance_probability = clamp(number(inputs.get("appearance_probability")), 0, 1)
    start_probability = clamp(
        number(inputs.get("start_probability")), 0, appearance_probability
    )
    conditional_start_probability = (
        start_probability / appearance_probability if appearance_probability else 0
    )
    starter_minutes_mean = clamp(
        number(inputs.get("starter_minutes_mean"))
        or number(inputs.get("expected_minutes"))
        or STARTER_MINUTES_PRIOR[position],
        45,
        90,
    )
    substitute_minutes_mean = clamp(
        number(inputs.get("substitute_minutes_mean"))
        or SUBSTITUTE_MINUTES_PRIOR[position],
        1,
        45,
    )
    minutes_deviation = clamp(number(inputs.get("minutes_deviation")) or 12, 4, 30)
    clean_sheet_probability = clamp(
        number(inputs.get("clean_sheet_probability")), 0.01, 0.99
    )
    expected_goals_against = -math.log(clean_sheet_probability)
    dispersion_shape = max(
        0.5,
        number(inputs.get("attack_dispersion_shape"))
        or ATTACK_DISPERSION_SHAPE[position],
    )

    points_samples: list[float] = []
    minutes_samples: list[float] = []
    goals_samples: list[float] = []
    assists_samples: list[float] = []
    saves_samples: list[float] = []
    starts_samples: list[int] = []
    sixty_plus_samples: list[int] = []
    component_totals = {field: 0.0 for field in COMPONENT_FIELDS}
    goal_returns = 0
    assist_returns = 0
    clean_sheet_returns = 0

    for _ in range(max(1, simulations)):
        components = {field: 0.0 for field in COMPONENT_FIELDS}
        if rng.random() >= appearance_probability:
            points_samples.append(0)
            minutes_samples.append(0)
            goals_samples.append(0)
            assists_samples.append(0)
            saves_samples.append(0)
            starts_samples.append(0)
            sixty_plus_samples.append(0)
            continue

        starts = rng.random() < conditional_start_probability
        if starts:
            minutes = round(
                clamp(rng.gauss(starter_minutes_mean, minutes_deviation / 2), 1, 90)
            )
        else:
            minutes = round(
                clamp(rng.gauss(substitute_minutes_mean, 7), 1, 45)
            )
        minutes_factor = minutes / 90
        starts_samples.append(int(starts))
        sixty_plus_samples.append(int(minutes >= 60))
        minutes_samples.append(minutes)

        attack_state = rng.gammavariate(dispersion_shape, 1 / dispersion_shape)
        goals = poisson(
            rng, number(inputs.get("xg_per_90")) * minutes_factor * attack_state
        )
        assists = poisson(
            rng, number(inputs.get("xa_per_90")) * minutes_factor * attack_state
        )
        goals_samples.append(goals)
        assists_samples.append(assists)
        goal_returns += int(goals > 0)
        assist_returns += int(assists > 0)

        components["appearance_points"] = 2 if minutes >= 60 else 1
        components["goal_points"] = goals * GOAL_POINTS[position]
        components["assist_points"] = assists * 3

        goals_against = poisson(rng, expected_goals_against * minutes_factor)
        clean_sheet = minutes >= 60 and goals_against == 0
        if clean_sheet:
            components["clean_sheet_points"] = CLEAN_SHEET_POINTS[position]
            clean_sheet_returns += 1
        if position in {"GK", "DEF"}:
            components["goals_conceded_points"] = -(goals_against // 2)

        saves = 0
        if position == "GK":
            saves = poisson(
                rng, number(inputs.get("saves_per_90")) * minutes_factor
            )
            components["save_points"] = saves // 3
            components["penalty_save_points"] = 5 * poisson(
                rng,
                number(inputs.get("penalties_saved_per_90")) * minutes_factor,
            )
        saves_samples.append(saves)

        threshold = DEFENSIVE_CONTRIBUTION_THRESHOLD[position]
        if threshold:
            contributions = poisson(
                rng,
                number(inputs.get("defensive_contribution_per_90")) * minutes_factor,
            )
            if contributions >= threshold:
                components["defensive_contribution_points"] = 2

        performance_multiplier = clamp(
            0.70
            + 0.55 * goals
            + 0.30 * assists
            + (0.15 if clean_sheet and position in {"GK", "DEF"} else 0)
            + (0.08 * components["save_points"] if position == "GK" else 0),
            0.45,
            2.50,
        )
        components["bonus_points"] = min(
            3,
            poisson(
                rng,
                number(inputs.get("bonus_per_90"))
                * minutes_factor
                * performance_multiplier,
            ),
        )
        components["discipline_points"] = -poisson(
            rng, number(inputs.get("yellow_cards_per_90")) * minutes_factor
        )
        components["discipline_points"] -= 3 * poisson(
            rng, number(inputs.get("red_cards_per_90")) * minutes_factor
        )
        components["discipline_points"] -= 2 * poisson(
            rng, number(inputs.get("own_goals_per_90")) * minutes_factor
        )
        components["discipline_points"] -= 2 * poisson(
            rng, number(inputs.get("penalties_missed_per_90")) * minutes_factor
        )

        points = sum(components.values())
        points_samples.append(points)
        for field, value in components.items():
            component_totals[field] += value

    count = len(points_samples)
    expected_components = {
        field: component_totals[field] / count for field in COMPONENT_FIELDS
    }
    return {
        "model_version": COMPONENT_MODEL_VERSION,
        "scoring_rules_version": rules_version,
        "simulation_count": count,
        "expected_points": statistics.fmean(points_samples),
        "expected_points_components": expected_components,
        "expected_minutes_simulated": statistics.fmean(minutes_samples),
        "expected_goals_simulated": statistics.fmean(goals_samples),
        "expected_assists_simulated": statistics.fmean(assists_samples),
        "expected_saves_simulated": statistics.fmean(saves_samples),
        "probability_start": statistics.fmean(starts_samples),
        "probability_60_plus": statistics.fmean(sixty_plus_samples),
        "goal_return_probability": goal_returns / count,
        "assist_return_probability": assist_returns / count,
        "attacking_return_probability": sum(
            goal > 0 or assist > 0
            for goal, assist in zip(goals_samples, assists_samples)
        )
        / count,
        "clean_sheet_return_probability": clean_sheet_returns / count,
        "points_p10": percentile(points_samples, 0.10),
        "points_p50": percentile(points_samples, 0.50),
        "points_p90": percentile(points_samples, 0.90),
        "minutes_p10": percentile(minutes_samples, 0.10),
        "minutes_p50": percentile(minutes_samples, 0.50),
        "minutes_p90": percentile(minutes_samples, 0.90),
        "probability_6_plus": sum(value >= 6 for value in points_samples) / count,
        "probability_10_plus": sum(value >= 10 for value in points_samples) / count,
        "probability_15_plus": sum(value >= 15 for value in points_samples) / count,
        "probability_3_or_fewer": sum(value <= 3 for value in points_samples) / count,
        "points_samples": points_samples,
    }
