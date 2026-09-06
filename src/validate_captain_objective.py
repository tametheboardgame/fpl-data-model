from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.backtest_fpl_model import (
    integer,
    number,
    player_key,
    read_historical,
    walk_forward_season,
)
from src.fpl_captaincy import (
    CAPTAIN_CEILING_WEIGHT,
    CAPTAIN_RANK_WEIGHT,
    CAPTAIN_UTILITY_VERSION,
    DEFENSIVE_CAPTAIN_EXCEPTION_MARGIN,
    DEFENSIVE_CAPTAIN_PENALTY,
    MAX_CAPTAIN_STRATEGIC_BONUS,
    MAX_PLAYER_CEILING_BONUS,
    OWNERSHIP_PRESSURE_FLOOR,
    OWNERSHIP_PRESSURE_FULL,
    P90_GAP_WEIGHT,
    PROBABILITY_10_PLUS_WEIGHT,
    PROBABILITY_15_PLUS_WEIGHT,
    captain_utility,
    select_strategic_captain,
)
from src.fpl_chip_optimizer import optimise_budget_squad
from src.update_fpl_data import utc_now, write_csv, write_json


VALIDATION_VERSION = "captain-objective-validation-1.0"
PRIMARY_SEASONS = ["2018-19", "2019-20", "2020-21", "2021-22"]
DESCRIPTIVE_SEASONS = ["2022-23", "2023-24"]
EXCLUDED_EXPOSED_SEASONS = ["2024-25", "2025-26"]
DEFAULT_SIMULATIONS = 300
REFERENCE_BUDGET = 100.0
REFERENCE_BEAM_WIDTH = 300

POSITION_NAMES = {
    "GK": "Goalkeeper",
    "DEF": "Defender",
    "MID": "Midfielder",
    "FWD": "Forward",
}
POSITION_REQUIREMENTS = {
    "Goalkeeper": 2,
    "Defender": 5,
    "Midfielder": 5,
    "Forward": 3,
}

MIN_PRIMARY_GAMEWEEKS = 100
MIN_OWNERSHIP_COVERAGE = 0.80
MEAN_POINTS_NONINFERIORITY = -0.10
REGRET_NONINFERIORITY = 0.10
BEST_HIT_NONINFERIORITY = -0.005
TEN_PLUS_NONINFERIORITY = -0.005
FIFTEEN_PLUS_NONINFERIORITY = -0.0025
UPSIDE_MEAN_POINTS = 0.02
UPSIDE_REGRET = -0.02
UPSIDE_BEST_HIT = 0.005
UPSIDE_TEN_PLUS = 0.005
UPSIDE_FIFTEEN_PLUS = 0.0025
MAX_DEFENSIVE_RATE_INCREASE = 0.02
MIN_DEFENSIVE_SWITCH_SAMPLE = 5
MAX_DEFENSIVE_SWITCH_FALSE_POSITIVE_RATE = 0.50
SEASON_MEAN_POINTS_NONINFERIORITY = -0.35
SEASON_REGRET_NONINFERIORITY = 0.35
MIN_STABLE_PRIMARY_SEASONS = 3
MAX_SINGLE_SEASON_MEAN_REGRESSION = -0.50


PREDECLARED_GATES = {
    "minimum_primary_gameweeks": MIN_PRIMARY_GAMEWEEKS,
    "minimum_lagged_ownership_coverage": MIN_OWNERSHIP_COVERAGE,
    "mean_captain_points_difference_minimum": MEAN_POINTS_NONINFERIORITY,
    "mean_regret_difference_maximum": REGRET_NONINFERIORITY,
    "best_captain_hit_rate_difference_minimum": BEST_HIT_NONINFERIORITY,
    "captain_10_plus_rate_difference_minimum": TEN_PLUS_NONINFERIORITY,
    "captain_15_plus_rate_difference_minimum": FIFTEEN_PLUS_NONINFERIORITY,
    "upside_minimums": {
        "mean_captain_points": UPSIDE_MEAN_POINTS,
        "mean_regret": UPSIDE_REGRET,
        "best_captain_hit_rate": UPSIDE_BEST_HIT,
        "captain_10_plus_rate": UPSIDE_TEN_PLUS,
        "captain_15_plus_rate": UPSIDE_FIFTEEN_PLUS,
    },
    "maximum_defensive_captain_rate_increase": MAX_DEFENSIVE_RATE_INCREASE,
    "defensive_switch_false_positive_gate": {
        "minimum_cases": MIN_DEFENSIVE_SWITCH_SAMPLE,
        "maximum_rate": MAX_DEFENSIVE_SWITCH_FALSE_POSITIVE_RATE,
    },
    "season_stability": {
        "mean_points_difference_minimum": SEASON_MEAN_POINTS_NONINFERIORITY,
        "regret_difference_maximum": SEASON_REGRET_NONINFERIORITY,
        "minimum_stable_seasons": MIN_STABLE_PRIMARY_SEASONS,
        "single_season_mean_points_floor": MAX_SINGLE_SEASON_MEAN_REGRESSION,
    },
}


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def normalise_price(value: Any) -> float:
    price = number(value)
    if price > 20:
        price /= 10
    return round(max(0.0, price), 2)


def build_lagged_ownership(
    historical_rows: list[dict[str, Any]],
) -> tuple[
    dict[tuple[str, int, str], float],
    dict[tuple[str, int], float],
]:
    """Return leakage-safe previous-GW ownership and inferred manager counts.

    Historical `selected` is deduplicated to one count per player per Gameweek so
    double-Gameweek fixture rows do not double-count ownership. The manager base is
    inferred from the fact that every valid FPL squad contains 15 players.
    """

    selected_by_gameweek: dict[tuple[str, int], dict[str, float]] = defaultdict(dict)
    for row in historical_rows:
        season = str(row.get("season") or "")
        gameweek = integer(row.get("gameweek"))
        key = player_key(row)
        if not season or gameweek <= 0 or not key:
            continue
        selected = max(0.0, number(row.get("selected")))
        previous = selected_by_gameweek[(season, gameweek)].get(key)
        if previous is None or selected > previous:
            selected_by_gameweek[(season, gameweek)][key] = selected

    ownership_by_gameweek: dict[tuple[str, int], dict[str, float]] = {}
    inferred_managers: dict[tuple[str, int], float] = {}
    for season_gameweek, player_counts in selected_by_gameweek.items():
        total_selections = sum(player_counts.values())
        manager_count = total_selections / 15 if total_selections > 0 else 0.0
        inferred_managers[season_gameweek] = manager_count
        if manager_count <= 0:
            ownership_by_gameweek[season_gameweek] = {}
            continue
        ownership_by_gameweek[season_gameweek] = {
            key: clamp(selected / manager_count * 100, 0.0, 100.0)
            for key, selected in player_counts.items()
        }

    lagged: dict[tuple[str, int, str], float] = {}
    for (season, gameweek), player_ownership in ownership_by_gameweek.items():
        target_gameweek = gameweek + 1
        for key, ownership in player_ownership.items():
            lagged[(season, target_gameweek, key)] = ownership
    return lagged, inferred_managers


def build_target_metadata(
    historical_rows: list[dict[str, Any]],
) -> dict[tuple[str, int, str], dict[str, Any]]:
    output: dict[tuple[str, int, str], dict[str, Any]] = {}
    for row in historical_rows:
        season = str(row.get("season") or "")
        gameweek = integer(row.get("gameweek"))
        key = player_key(row)
        if not season or gameweek <= 0 or not key:
            continue
        index = (season, gameweek, key)
        existing = output.get(index, {})
        price = normalise_price(row.get("value"))
        output[index] = {
            "price": price if price > 0 else number(existing.get("price")),
            "team": str(row.get("team") or existing.get("team") or ""),
            "position": str(row.get("position") or existing.get("position") or ""),
        }
    return output


def _captain_sort_key(
    player_id: int,
    audits: dict[int, dict[str, Any]],
    expected_points: dict[int, float],
    p90: dict[int, float],
    p10: dict[int, float],
    p15: dict[int, float],
) -> tuple[float, float, float, float, float, float, int]:
    return (
        number(audits[player_id].get("captain_score")),
        number(audits[player_id].get("raw_utility")),
        number(expected_points.get(player_id)),
        number(p15.get(player_id)),
        number(p10.get(player_id)),
        number(p90.get(player_id)),
        -player_id,
    )


def evaluate_reference_gameweek(
    season: str,
    gameweek: int,
    prediction_rows: list[dict[str, Any]],
    metadata: dict[tuple[str, int, str], dict[str, Any]],
    lagged_ownership: dict[tuple[str, int, str], float],
) -> dict[str, Any] | None:
    eligible: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for prediction in prediction_rows:
        key = str(prediction.get("player_key") or "")
        meta = metadata.get((season, gameweek, key), {})
        position = POSITION_NAMES.get(str(prediction.get("position") or "").upper())
        price = normalise_price(meta.get("price"))
        team = str(prediction.get("team") or meta.get("team") or "")
        if not key or position is None or price <= 0 or not team:
            continue
        eligible.append((key, prediction, {**meta, "position_name": position, "price": price, "team": team}))

    team_ids = {
        team: index
        for index, team in enumerate(sorted({meta["team"] for _, _, meta in eligible}), start=1)
    }
    player_by_id: dict[int, dict[str, Any]] = {}
    prediction_by_id: dict[int, dict[str, Any]] = {}
    expected_points: dict[int, float] = {}
    points_p90: dict[int, float] = {}
    probability_10_plus: dict[int, float] = {}
    probability_15_plus: dict[int, float] = {}
    ownership_available: dict[int, bool] = {}

    for player_id, (key, prediction, meta) in enumerate(sorted(eligible, key=lambda item: item[0]), start=1):
        ownership_key = (season, gameweek, key)
        ownership = number(lagged_ownership.get(ownership_key))
        player_by_id[player_id] = {
            "player_id": player_id,
            "player_key": key,
            "web_name": str(prediction.get("player_name") or key),
            "position": meta["position_name"],
            "team_id": team_ids[meta["team"]],
            "team_name": meta["team"],
            "price": meta["price"],
            "selected_by_percent": ownership,
        }
        prediction_by_id[player_id] = prediction
        expected_points[player_id] = max(0.0, number(prediction.get("player_sim_prediction")))
        points_p90[player_id] = max(0.0, number(prediction.get("points_p90")))
        probability_10_plus[player_id] = clamp(number(prediction.get("probability_10_plus")), 0.0, 1.0)
        probability_15_plus[player_id] = clamp(number(prediction.get("probability_15_plus")), 0.0, 1.0)
        ownership_available[player_id] = ownership_key in lagged_ownership

    position_counts: dict[str, int] = defaultdict(int)
    for player in player_by_id.values():
        position_counts[str(player.get("position"))] += 1
    if any(position_counts.get(position, 0) < count for position, count in POSITION_REQUIREMENTS.items()):
        return None

    reference = optimise_budget_squad(
        player_by_id,
        expected_points,
        REFERENCE_BUDGET,
        beam_width=REFERENCE_BEAM_WIDTH,
    )
    if reference is None:
        return None
    squad_ids, squad_cost, _, starters, control_captain = reference
    if not starters or control_captain is None:
        return None

    strategic_captain = select_strategic_captain(
        starters,
        player_by_id,
        expected_points,
        points_p90,
        probability_10_plus,
        probability_15_plus,
    )
    if strategic_captain is None:
        return None

    neutral_players = {
        player_id: {**player, "selected_by_percent": 0.0}
        for player_id, player in player_by_id.items()
    }
    neutral_captain = select_strategic_captain(
        starters,
        neutral_players,
        expected_points,
        points_p90,
        probability_10_plus,
        probability_15_plus,
    )

    actual_points = {
        player_id: number(prediction_by_id[player_id].get("actual_points"))
        for player_id in starters
    }
    best_actual = max(actual_points.values())
    best_ids = {player_id for player_id, value in actual_points.items() if value == best_actual}

    control_ranked = sorted(
        starters,
        key=lambda player_id: (
            expected_points.get(player_id, 0.0),
            probability_15_plus.get(player_id, 0.0),
            probability_10_plus.get(player_id, 0.0),
            points_p90.get(player_id, 0.0),
            -player_id,
        ),
        reverse=True,
    )
    audits = {
        player_id: captain_utility(
            player_id=player_id,
            mean_expected_points=expected_points.get(player_id, 0.0),
            points_p90=points_p90.get(player_id, 0.0),
            probability_10_plus=probability_10_plus.get(player_id, 0.0),
            probability_15_plus=probability_15_plus.get(player_id, 0.0),
            ownership_percent=number(player_by_id[player_id].get("selected_by_percent")),
            position=str(player_by_id[player_id].get("position")),
        )
        for player_id in starters
    }
    strategic_ranked = sorted(
        starters,
        key=lambda player_id: _captain_sort_key(
            player_id,
            audits,
            expected_points,
            points_p90,
            probability_10_plus,
            probability_15_plus,
        ),
        reverse=True,
    )

    control_actual = actual_points[control_captain]
    strategic_actual = actual_points[strategic_captain]
    neutral_actual = actual_points.get(neutral_captain, strategic_actual)
    control_player = player_by_id[control_captain]
    strategic_player = player_by_id[strategic_captain]
    attacking_starters = [
        player_id
        for player_id in starters
        if str(player_by_id[player_id].get("position")) in {"Midfielder", "Forward"}
    ]
    best_attacking_actual = max((actual_points[player_id] for player_id in attacking_starters), default=best_actual)
    control_defensive = str(control_player.get("position")) in {"Goalkeeper", "Defender"}
    strategic_defensive = str(strategic_player.get("position")) in {"Goalkeeper", "Defender"}
    defensive_switch = (
        strategic_captain != control_captain
        and strategic_defensive
        and not control_defensive
    )
    defensive_false_positive = defensive_switch and strategic_actual < best_attacking_actual
    strategic_premium_attacker = (
        str(strategic_player.get("position")) in {"Midfielder", "Forward"}
        and number(strategic_player.get("price")) >= 10.0
    )
    control_premium_attacker = (
        str(control_player.get("position")) in {"Midfielder", "Forward"}
        and number(control_player.get("price")) >= 10.0
    )
    strategic_high_ownership_high_ceiling = (
        number(strategic_player.get("selected_by_percent")) >= OWNERSHIP_PRESSURE_FLOOR
        and points_p90.get(strategic_captain, 0.0) >= 10.0
    )
    control_high_ownership_high_ceiling = (
        number(control_player.get("selected_by_percent")) >= OWNERSHIP_PRESSURE_FLOOR
        and points_p90.get(control_captain, 0.0) >= 10.0
    )

    return {
        "season": season,
        "gameweek": gameweek,
        "reference_squad_cost": round(squad_cost, 2),
        "reference_squad_size": len(squad_ids),
        "starter_count": len(starters),
        "ownership_available_starters": sum(1 for player_id in starters if ownership_available.get(player_id)),
        "control_captain": str(control_player.get("web_name")),
        "strategic_captain": str(strategic_player.get("web_name")),
        "neutral_strategic_captain": str(player_by_id.get(neutral_captain, {}).get("web_name") or ""),
        "captain_changed": int(strategic_captain != control_captain),
        "control_actual_points": control_actual,
        "strategic_actual_points": strategic_actual,
        "neutral_strategic_actual_points": neutral_actual,
        "actual_points_difference": strategic_actual - control_actual,
        "best_available_actual_points": best_actual,
        "control_regret": best_actual - control_actual,
        "strategic_regret": best_actual - strategic_actual,
        "neutral_strategic_regret": best_actual - neutral_actual,
        "control_best_hit": int(control_captain in best_ids),
        "strategic_best_hit": int(strategic_captain in best_ids),
        "neutral_strategic_best_hit": int(neutral_captain in best_ids if neutral_captain is not None else False),
        "control_10_plus": int(control_actual >= 10),
        "strategic_10_plus": int(strategic_actual >= 10),
        "control_15_plus": int(control_actual >= 15),
        "strategic_15_plus": int(strategic_actual >= 15),
        "control_top3_hit": int(bool(best_ids & set(control_ranked[:3]))),
        "strategic_top3_hit": int(bool(best_ids & set(strategic_ranked[:3]))),
        "strategic_win_when_changed": int(strategic_captain != control_captain and strategic_actual > control_actual),
        "strategic_loss_when_changed": int(strategic_captain != control_captain and strategic_actual < control_actual),
        "strategic_tie_when_changed": int(strategic_captain != control_captain and strategic_actual == control_actual),
        "control_defensive_captain": int(control_defensive),
        "strategic_defensive_captain": int(strategic_defensive),
        "defensive_switch": int(defensive_switch),
        "defensive_switch_false_positive": int(defensive_false_positive),
        "control_premium_attacker": int(control_premium_attacker),
        "strategic_premium_attacker": int(strategic_premium_attacker),
        "control_high_ownership_high_ceiling": int(control_high_ownership_high_ceiling),
        "strategic_high_ownership_high_ceiling": int(strategic_high_ownership_high_ceiling),
        "control_mean_xpts": round(expected_points[control_captain], 4),
        "strategic_mean_xpts": round(expected_points[strategic_captain], 4),
        "strategic_captain_score": audits[strategic_captain]["captain_score"],
        "strategic_captain_raw_utility": audits[strategic_captain]["raw_utility"],
        "strategic_captain_p90": round(points_p90[strategic_captain], 4),
        "strategic_captain_probability_10_plus": round(probability_10_plus[strategic_captain], 4),
        "strategic_captain_probability_15_plus": round(probability_15_plus[strategic_captain], 4),
        "strategic_captain_lagged_ownership": round(number(strategic_player.get("selected_by_percent")), 4),
    }


def _mean(rows: list[dict[str, Any]], field: str) -> float:
    if not rows:
        return 0.0
    return statistics.fmean(number(row.get(field)) for row in rows)


def aggregate_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "gameweeks": 0,
            "ownership_coverage_rate": 0.0,
        }
    differences = [number(row.get("actual_points_difference")) for row in rows]
    mean_difference = statistics.fmean(differences)
    standard_error = (
        statistics.stdev(differences) / math.sqrt(len(differences))
        if len(differences) > 1
        else 0.0
    )
    ci_lower = mean_difference - 1.96 * standard_error
    ci_upper = mean_difference + 1.96 * standard_error
    changed = sum(integer(row.get("captain_changed")) for row in rows)
    defensive_switches = sum(integer(row.get("defensive_switch")) for row in rows)
    defensive_false_positives = sum(
        integer(row.get("defensive_switch_false_positive")) for row in rows
    )
    ownership_denominator = sum(integer(row.get("starter_count")) for row in rows)
    ownership_numerator = sum(integer(row.get("ownership_available_starters")) for row in rows)

    control_mean_points = _mean(rows, "control_actual_points")
    strategic_mean_points = _mean(rows, "strategic_actual_points")
    neutral_mean_points = _mean(rows, "neutral_strategic_actual_points")
    control_regret = _mean(rows, "control_regret")
    strategic_regret = _mean(rows, "strategic_regret")
    neutral_regret = _mean(rows, "neutral_strategic_regret")
    control_best_hit = _mean(rows, "control_best_hit")
    strategic_best_hit = _mean(rows, "strategic_best_hit")
    control_10_plus = _mean(rows, "control_10_plus")
    strategic_10_plus = _mean(rows, "strategic_10_plus")
    control_15_plus = _mean(rows, "control_15_plus")
    strategic_15_plus = _mean(rows, "strategic_15_plus")
    control_defensive = _mean(rows, "control_defensive_captain")
    strategic_defensive = _mean(rows, "strategic_defensive_captain")

    return {
        "gameweeks": len(rows),
        "control_mean_captain_points": round(control_mean_points, 4),
        "strategic_mean_captain_points": round(strategic_mean_points, 4),
        "mean_captain_points_difference": round(strategic_mean_points - control_mean_points, 4),
        "mean_captain_points_difference_95pct_ci_lower": round(ci_lower, 4),
        "mean_captain_points_difference_95pct_ci_upper": round(ci_upper, 4),
        "neutral_strategic_mean_captain_points": round(neutral_mean_points, 4),
        "lagged_ownership_vs_neutral_mean_points_difference": round(strategic_mean_points - neutral_mean_points, 4),
        "control_mean_regret": round(control_regret, 4),
        "strategic_mean_regret": round(strategic_regret, 4),
        "mean_regret_difference": round(strategic_regret - control_regret, 4),
        "neutral_strategic_mean_regret": round(neutral_regret, 4),
        "control_best_captain_hit_rate": round(control_best_hit, 4),
        "strategic_best_captain_hit_rate": round(strategic_best_hit, 4),
        "best_captain_hit_rate_difference": round(strategic_best_hit - control_best_hit, 4),
        "control_10_plus_rate": round(control_10_plus, 4),
        "strategic_10_plus_rate": round(strategic_10_plus, 4),
        "captain_10_plus_rate_difference": round(strategic_10_plus - control_10_plus, 4),
        "control_15_plus_rate": round(control_15_plus, 4),
        "strategic_15_plus_rate": round(strategic_15_plus, 4),
        "captain_15_plus_rate_difference": round(strategic_15_plus - control_15_plus, 4),
        "control_top3_shortlist_hit_rate": round(_mean(rows, "control_top3_hit"), 4),
        "strategic_top3_shortlist_hit_rate": round(_mean(rows, "strategic_top3_hit"), 4),
        "captain_change_rate": round(changed / len(rows), 4),
        "captain_changed_gameweeks": changed,
        "strategic_wins_when_changed": sum(integer(row.get("strategic_win_when_changed")) for row in rows),
        "strategic_losses_when_changed": sum(integer(row.get("strategic_loss_when_changed")) for row in rows),
        "strategic_ties_when_changed": sum(integer(row.get("strategic_tie_when_changed")) for row in rows),
        "control_defensive_captain_rate": round(control_defensive, 4),
        "strategic_defensive_captain_rate": round(strategic_defensive, 4),
        "defensive_captain_rate_difference": round(strategic_defensive - control_defensive, 4),
        "defensive_switch_cases": defensive_switches,
        "defensive_switch_false_positives": defensive_false_positives,
        "defensive_switch_false_positive_rate": (
            round(defensive_false_positives / defensive_switches, 4)
            if defensive_switches
            else None
        ),
        "control_premium_attacker_captain_rate": round(_mean(rows, "control_premium_attacker"), 4),
        "strategic_premium_attacker_captain_rate": round(_mean(rows, "strategic_premium_attacker"), 4),
        "control_high_ownership_high_ceiling_rate": round(_mean(rows, "control_high_ownership_high_ceiling"), 4),
        "strategic_high_ownership_high_ceiling_rate": round(_mean(rows, "strategic_high_ownership_high_ceiling"), 4),
        "ownership_coverage_rate": (
            round(ownership_numerator / ownership_denominator, 4)
            if ownership_denominator
            else 0.0
        ),
    }


def evaluate_acceptance(
    primary_metrics: dict[str, Any],
    primary_by_season: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    sample_ok = integer(primary_metrics.get("gameweeks")) >= MIN_PRIMARY_GAMEWEEKS
    ownership_ok = number(primary_metrics.get("ownership_coverage_rate")) >= MIN_OWNERSHIP_COVERAGE
    stable_seasons = [
        season
        for season, metrics in primary_by_season.items()
        if number(metrics.get("mean_captain_points_difference")) >= SEASON_MEAN_POINTS_NONINFERIORITY
        and number(metrics.get("mean_regret_difference")) <= SEASON_REGRET_NONINFERIORITY
    ]
    season_differences = [
        number(metrics.get("mean_captain_points_difference"))
        for metrics in primary_by_season.values()
        if integer(metrics.get("gameweeks")) > 0
    ]
    false_positive_cases = integer(primary_metrics.get("defensive_switch_cases"))
    false_positive_rate_raw = primary_metrics.get("defensive_switch_false_positive_rate")
    false_positive_rate = (
        number(false_positive_rate_raw) if false_positive_rate_raw is not None else 0.0
    )
    upside_signal = any(
        (
            number(primary_metrics.get("mean_captain_points_difference")) >= UPSIDE_MEAN_POINTS,
            number(primary_metrics.get("mean_regret_difference")) <= UPSIDE_REGRET,
            number(primary_metrics.get("best_captain_hit_rate_difference")) >= UPSIDE_BEST_HIT,
            number(primary_metrics.get("captain_10_plus_rate_difference")) >= UPSIDE_TEN_PLUS,
            number(primary_metrics.get("captain_15_plus_rate_difference")) >= UPSIDE_FIFTEEN_PLUS,
        )
    )

    criteria = {
        "sample_size": sample_ok,
        "lagged_ownership_coverage": ownership_ok,
        "mean_captain_points_noninferior": number(primary_metrics.get("mean_captain_points_difference"))
        >= MEAN_POINTS_NONINFERIORITY,
        "mean_regret_noninferior": number(primary_metrics.get("mean_regret_difference"))
        <= REGRET_NONINFERIORITY,
        "best_captain_hit_rate_noninferior": number(primary_metrics.get("best_captain_hit_rate_difference"))
        >= BEST_HIT_NONINFERIORITY,
        "captain_10_plus_rate_noninferior": number(primary_metrics.get("captain_10_plus_rate_difference"))
        >= TEN_PLUS_NONINFERIORITY,
        "captain_15_plus_rate_noninferior": number(primary_metrics.get("captain_15_plus_rate_difference"))
        >= FIFTEEN_PLUS_NONINFERIORITY,
        "positive_upside_signal": upside_signal,
        "defensive_captain_rate_bounded": number(primary_metrics.get("defensive_captain_rate_difference"))
        <= MAX_DEFENSIVE_RATE_INCREASE,
        "defensive_switch_false_positive_safe": (
            false_positive_cases < MIN_DEFENSIVE_SWITCH_SAMPLE
            or false_positive_rate <= MAX_DEFENSIVE_SWITCH_FALSE_POSITIVE_RATE
        ),
        "season_stability": len(stable_seasons) >= MIN_STABLE_PRIMARY_SEASONS,
        "no_severe_single_season_regression": (
            min(season_differences, default=0.0) >= MAX_SINGLE_SEASON_MEAN_REGRESSION
        ),
    }
    integrity_keys = {"sample_size", "lagged_ownership_coverage"}
    if not all(criteria[key] for key in integrity_keys):
        status = "inconclusive"
    elif all(criteria.values()):
        status = "accepted"
    else:
        status = "rejected"
    failed = [key for key, passed in criteria.items() if not passed]
    return {
        "status": status,
        "recommended_for_current_gameweek_authority": status == "accepted",
        "criteria": criteria,
        "failed_gates": failed,
        "stable_primary_seasons": stable_seasons,
        "stable_primary_season_count": len(stable_seasons),
        "principle": (
            "The frozen captain utility is accepted only if every predeclared blocking gate passes. "
            "A rejected result must not trigger coefficient tuning against this evaluation set."
        ),
    }


def run_validation(
    data_dir: Path,
    *,
    simulations: int = DEFAULT_SIMULATIONS,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    seasons = [*PRIMARY_SEASONS, *DESCRIPTIVE_SEASONS]
    historical_path = data_dir / "history" / "historical_player_gameweeks.csv.gz"
    historical_rows = read_historical(historical_path, seasons)
    lagged_ownership, inferred_managers = build_lagged_ownership(historical_rows)
    metadata = build_target_metadata(historical_rows)

    raw_by_season: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in historical_rows:
        raw_by_season[str(row.get("season") or "")].append(row)

    prediction_rows: list[dict[str, Any]] = []
    for season in seasons:
        prediction_rows.extend(
            walk_forward_season(raw_by_season.get(season, []), simulations=simulations)
        )

    predictions_by_gameweek: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in prediction_rows:
        predictions_by_gameweek[(str(row.get("season") or ""), integer(row.get("gameweek")))].append(row)

    details: list[dict[str, Any]] = []
    skipped_gameweeks: list[dict[str, Any]] = []
    for (season, gameweek), rows in sorted(predictions_by_gameweek.items()):
        result = evaluate_reference_gameweek(
            season,
            gameweek,
            rows,
            metadata,
            lagged_ownership,
        )
        if result is None:
            skipped_gameweeks.append({"season": season, "gameweek": gameweek})
            continue
        details.append(result)

    primary_rows = [row for row in details if row.get("season") in PRIMARY_SEASONS]
    descriptive_rows = [row for row in details if row.get("season") in DESCRIPTIVE_SEASONS]
    by_season = {
        season: aggregate_metrics([row for row in details if row.get("season") == season])
        for season in seasons
    }
    primary_by_season = {season: by_season[season] for season in PRIMARY_SEASONS}
    primary_metrics = aggregate_metrics(primary_rows)
    descriptive_metrics = aggregate_metrics(descriptive_rows)
    acceptance = evaluate_acceptance(primary_metrics, primary_by_season)

    manager_summary = {
        season: {
            "gameweeks_with_inferred_manager_base": sum(
                1
                for (candidate_season, _), managers in inferred_managers.items()
                if candidate_season == season and managers > 0
            ),
            "minimum_inferred_managers": round(
                min(
                    (
                        managers
                        for (candidate_season, _), managers in inferred_managers.items()
                        if candidate_season == season and managers > 0
                    ),
                    default=0.0,
                ),
                2,
            ),
            "maximum_inferred_managers": round(
                max(
                    (
                        managers
                        for (candidate_season, _), managers in inferred_managers.items()
                        if candidate_season == season and managers > 0
                    ),
                    default=0.0,
                ),
                2,
            ),
        }
        for season in seasons
    }

    report = {
        "validation_version": VALIDATION_VERSION,
        "generated_at": utc_now(),
        "captain_utility_version": CAPTAIN_UTILITY_VERSION,
        "status": acceptance["status"],
        "recommended_for_current_gameweek_authority": acceptance[
            "recommended_for_current_gameweek_authority"
        ],
        "evaluation_design": {
            "primary_gated_seasons": PRIMARY_SEASONS,
            "descriptive_only_seasons": DESCRIPTIVE_SEASONS,
            "excluded_exposed_seasons": EXCLUDED_EXPOSED_SEASONS,
            "simulations_per_player_fixture": simulations,
            "reference_budget": REFERENCE_BUDGET,
            "reference_squad_method": (
                "One deterministic legal synthetic 15-player squad per Gameweek, selected from control mean xPts only; "
                "the same mean-selected starting XI is used for control and strategic captain comparison."
            ),
            "ownership_method": (
                "Previous-Gameweek selected counts only; deduplicated per player, manager base inferred as total selections / 15, "
                "then converted to lagged ownership percent. Target-GW selected counts are never used as captain inputs."
            ),
            "coefficient_selection": "None. strategic-captain-1.0 was frozen before this evaluation.",
        },
        "captain_utility_parameters": {
            "p90_gap_weight": P90_GAP_WEIGHT,
            "probability_10_plus_weight": PROBABILITY_10_PLUS_WEIGHT,
            "probability_15_plus_weight": PROBABILITY_15_PLUS_WEIGHT,
            "maximum_player_ceiling_bonus": MAX_PLAYER_CEILING_BONUS,
            "captain_ceiling_weight": CAPTAIN_CEILING_WEIGHT,
            "captain_rank_weight": CAPTAIN_RANK_WEIGHT,
            "maximum_captain_strategic_bonus": MAX_CAPTAIN_STRATEGIC_BONUS,
            "defensive_captain_penalty": DEFENSIVE_CAPTAIN_PENALTY,
            "defensive_exception_margin": DEFENSIVE_CAPTAIN_EXCEPTION_MARGIN,
            "ownership_pressure_floor": OWNERSHIP_PRESSURE_FLOOR,
            "ownership_pressure_full": OWNERSHIP_PRESSURE_FULL,
        },
        "predeclared_gates": PREDECLARED_GATES,
        "historical_source_rows": len(historical_rows),
        "walk_forward_prediction_rows": len(prediction_rows),
        "evaluated_gameweeks": len(details),
        "skipped_reference_squad_gameweeks": skipped_gameweeks,
        "inferred_manager_base_summary": manager_summary,
        "primary_metrics": primary_metrics,
        "descriptive_metrics": descriptive_metrics,
        "by_season": by_season,
        "acceptance": acceptance,
        "limitations": [
            "Historical squads are synthetic legal reference squads, not the user's actual squads; this isolates captain choice but cannot reproduce transfer-path constraints.",
            "Lagged ownership is deliberately conservative and cannot capture target-Gameweek transfer movement that live pre-deadline ownership can observe.",
            "The 2018/19-2021/22 primary robustness seasons have sparser expected-stat fields than modern seasons, so the simulator relies more heavily on priors there.",
            "Historical defensive-contribution points are disabled because that scoring rule did not exist in the evaluated seasons.",
            "2024/25 and the closed 2025/26 holdout are excluded from FPL-22C promotion gates; no failed gate may be repaired by tuning against them.",
            "Prospective 2026/27 evidence remains required even if the retrospective gates pass.",
        ],
    }
    return report, details


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the frozen shared FPL captain objective.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--simulations", type=int, default=DEFAULT_SIMULATIONS)
    parser.add_argument(
        "--output",
        default="data/backtests/captain_objective_validation.json",
    )
    parser.add_argument(
        "--details-output",
        default="data/backtests/captain_objective_gameweeks.csv",
    )
    args = parser.parse_args()

    report, details = run_validation(
        Path(args.data_dir),
        simulations=max(50, args.simulations),
    )
    output_path = Path(args.output)
    details_path = Path(args.details_output)
    write_json(output_path, report)
    if details:
        write_csv(details_path, details, list(details[0].keys()))

    compact = {
        "status": report["status"],
        "recommended": report["recommended_for_current_gameweek_authority"],
        "primary_gameweeks": report["primary_metrics"].get("gameweeks"),
        "ownership_coverage": report["primary_metrics"].get("ownership_coverage_rate"),
        "mean_captain_points_difference": report["primary_metrics"].get(
            "mean_captain_points_difference"
        ),
        "mean_regret_difference": report["primary_metrics"].get("mean_regret_difference"),
        "best_hit_difference": report["primary_metrics"].get(
            "best_captain_hit_rate_difference"
        ),
        "ten_plus_difference": report["primary_metrics"].get(
            "captain_10_plus_rate_difference"
        ),
        "fifteen_plus_difference": report["primary_metrics"].get(
            "captain_15_plus_rate_difference"
        ),
        "defensive_rate_difference": report["primary_metrics"].get(
            "defensive_captain_rate_difference"
        ),
        "failed_gates": report["acceptance"].get("failed_gates"),
        "stable_primary_seasons": report["acceptance"].get("stable_primary_seasons"),
    }
    print("CAPTAIN_OBJECTIVE_VALIDATION_RESULT=" + json.dumps(compact, sort_keys=True))


if __name__ == "__main__":
    main()
