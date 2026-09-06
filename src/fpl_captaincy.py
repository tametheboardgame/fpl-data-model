from __future__ import annotations

from typing import Any


CAPTAIN_UTILITY_VERSION = "strategic-captain-1.0"
P90_GAP_WEIGHT = 0.16
PROBABILITY_10_PLUS_WEIGHT = 1.20
PROBABILITY_15_PLUS_WEIGHT = 2.00
MAX_PLAYER_CEILING_BONUS = 1.75
CAPTAIN_CEILING_WEIGHT = 0.70
CAPTAIN_RANK_WEIGHT = 0.45
MAX_CAPTAIN_STRATEGIC_BONUS = 1.80
DEFENSIVE_CAPTAIN_PENALTY = 0.30
DEFENSIVE_CAPTAIN_EXCEPTION_MARGIN = 1.50
OWNERSHIP_PRESSURE_FLOOR = 35.0
OWNERSHIP_PRESSURE_FULL = 75.0


def number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def ownership_pressure(ownership_percent: float) -> float:
    return clamp(
        (number(ownership_percent) - OWNERSHIP_PRESSURE_FLOOR)
        / max(1.0, OWNERSHIP_PRESSURE_FULL - OWNERSHIP_PRESSURE_FLOOR),
        0.0,
        1.0,
    )


def captain_ceiling_bonus(
    mean_expected_points: float,
    points_p90: float,
    probability_10_plus: float,
    probability_15_plus: float,
) -> float:
    mean = max(0.0, number(mean_expected_points))
    p90_gap = max(0.0, number(points_p90) - mean)
    bonus = (
        P90_GAP_WEIGHT * p90_gap
        + PROBABILITY_10_PLUS_WEIGHT
        * clamp(number(probability_10_plus), 0.0, 1.0)
        + PROBABILITY_15_PLUS_WEIGHT
        * clamp(number(probability_15_plus), 0.0, 1.0)
    )
    return min(MAX_PLAYER_CEILING_BONUS, bonus)


def captain_utility(
    *,
    player_id: int,
    mean_expected_points: float,
    points_p90: float,
    probability_10_plus: float,
    probability_15_plus: float,
    ownership_percent: float,
    position: str,
    reference_mean_expected_points: float | None = None,
    expected_minutes: float | None = None,
    availability_confidence: float | None = None,
    selection_risk_penalty: float | None = None,
) -> dict[str, Any]:
    """Return one auditable strategic captain score.

    ``mean_expected_points`` is the already risk-adjusted operational mean used for
    selection. Minutes and availability are represented once through that mean and
    exposed here for audit rather than being penalised a second time. Strategic
    ceiling/rank terms choose who is doubled but are never expected points.
    """

    mean = max(0.0, number(mean_expected_points))
    reference_mean = (
        max(0.0, number(reference_mean_expected_points))
        if reference_mean_expected_points is not None
        else mean
    )
    p90 = max(0.0, number(points_p90))
    p10 = clamp(number(probability_10_plus), 0.0, 1.0)
    p15 = clamp(number(probability_15_plus), 0.0, 1.0)
    ownership = clamp(number(ownership_percent), 0.0, 100.0)
    ceiling = captain_ceiling_bonus(mean, p90, p10, p15)
    rank_pressure = ownership_pressure(ownership)
    ceiling_contribution = CAPTAIN_CEILING_WEIGHT * ceiling
    rank_contribution = CAPTAIN_RANK_WEIGHT * rank_pressure
    strategic_bonus = min(
        MAX_CAPTAIN_STRATEGIC_BONUS,
        ceiling_contribution + rank_contribution,
    )
    defensive = str(position) in {"Goalkeeper", "Defender"}
    position_penalty = DEFENSIVE_CAPTAIN_PENALTY if defensive else 0.0
    defensive_margin = DEFENSIVE_CAPTAIN_EXCEPTION_MARGIN if defensive else 0.0
    raw_utility = mean + strategic_bonus - position_penalty
    selection_score = raw_utility - defensive_margin
    reliability_ratio = (
        clamp(mean / reference_mean, 0.0, 1.5) if reference_mean > 0 else 1.0
    )

    return {
        "version": CAPTAIN_UTILITY_VERSION,
        "player_id": int(player_id),
        "captain_score": round(selection_score, 4),
        "raw_utility": round(raw_utility, 4),
        "mean_expected_points": round(mean, 4),
        "reference_mean_expected_points": round(reference_mean, 4),
        "selection_reliability_ratio": round(reliability_ratio, 4),
        "selection_risk_penalty": (
            round(max(0.0, number(selection_risk_penalty)), 4)
            if selection_risk_penalty is not None
            else None
        ),
        "expected_minutes": (
            round(max(0.0, number(expected_minutes)), 2)
            if expected_minutes is not None
            else None
        ),
        "availability_confidence": (
            round(clamp(number(availability_confidence), 0.0, 1.0), 4)
            if availability_confidence is not None
            else None
        ),
        "points_p90": round(p90, 4),
        "p90_gap": round(max(0.0, p90 - mean), 4),
        "probability_10_plus": round(p10, 4),
        "probability_15_plus": round(p15, 4),
        "ownership_percent": round(ownership, 4),
        "rank_pressure": round(rank_pressure, 4),
        "ceiling_bonus": round(ceiling, 4),
        "ceiling_contribution": round(ceiling_contribution, 4),
        "rank_pressure_contribution": round(rank_contribution, 4),
        "bounded_strategic_bonus": round(strategic_bonus, 4),
        "position": str(position),
        "position_uncertainty_penalty": round(position_penalty, 4),
        "defensive_exception_margin": round(defensive_margin, 4),
        "strategic_bonus_is_expected_points": False,
    }


def select_strategic_captain(
    starter_ids: list[int] | tuple[int, ...] | set[int],
    player_by_id: dict[int, dict[str, Any]],
    expected_points: dict[int, float],
    points_p90: dict[int, float],
    probability_10_plus: dict[int, float],
    probability_15_plus: dict[int, float],
) -> int | None:
    """Select a deterministic captain using the shared strategic utility."""

    starters = sorted(set(int(player_id) for player_id in starter_ids))
    if not starters:
        return None

    audits: dict[int, dict[str, Any]] = {}
    for player_id in starters:
        player = player_by_id.get(player_id, {})
        mean = number(expected_points.get(player_id, 0.0))
        audits[player_id] = captain_utility(
            player_id=player_id,
            mean_expected_points=mean,
            points_p90=number(points_p90.get(player_id, mean)),
            probability_10_plus=number(probability_10_plus.get(player_id, 0.0)),
            probability_15_plus=number(probability_15_plus.get(player_id, 0.0)),
            ownership_percent=number(player.get("selected_by_percent")),
            position=str(player.get("position")),
        )

    return max(
        starters,
        key=lambda player_id: (
            number(audits[player_id].get("captain_score")),
            number(audits[player_id].get("raw_utility")),
            number(expected_points.get(player_id, 0.0)),
            number(probability_15_plus.get(player_id, 0.0)),
            number(probability_10_plus.get(player_id, 0.0)),
            number(points_p90.get(player_id, 0.0)),
            -player_id,
        ),
    )
