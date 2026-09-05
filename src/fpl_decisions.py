from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.external_context import number, resolved_context
from src.fpl_chip_optimizer import optimise_chip_plan
from src.fpl_chips import derive_chip_state
from src.fpl_initial_squad import build_initial_squad_plan
from src.fpl_multiweek import (
    fixture_rows_by_player,
    lineup_correlation_analysis,
    optimise_gameweek_lineup,
    optimise_multi_gameweek_route,
)
from src.fpl_transfers import derive_free_transfer_state, transfer_hit_cost


DECISION_VERSION = "fpl-decisions-2.3"
MARKET_BLEND_WEIGHT = 0.75
MINUTES_RISK_WEIGHT = 0.30
MODEL_DISAGREEMENT_WEIGHT = 0.25
MAX_SELECTION_RISK_SHARE = 0.40
GOAL_POINTS = {
    "Goalkeeper": 6,
    "Defender": 6,
    "Midfielder": 5,
    "Forward": 4,
}
CLEAN_SHEET_POINTS = {
    "Goalkeeper": 4,
    "Defender": 4,
    "Midfielder": 1,
    "Forward": 0,
}


def integer(value: Any) -> int:
    return int(number(value))


def ownership(player: dict[str, Any]) -> float:
    return number(player.get("selected_by_percent"))


def horizon_value(row: dict[str, Any], horizon: int, field: str = "expected_points") -> float:
    return number(row.get(f"{field}_next_{horizon}"))


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _expected_goals_conceded_deductions(expected_goals_against: float) -> float:
    expected_goals_against = clamp(expected_goals_against, 0, 8)
    return sum(
        (goals // 2)
        * math.exp(-expected_goals_against)
        * expected_goals_against**goals
        / math.factorial(goals)
        for goals in range(20)
    )


def fixture_rows_with_model_team_xg(
    fixture_projections: list[dict[str, Any]], gameweek: int
) -> list[dict[str, Any]]:
    selected = [
        dict(row)
        for row in fixture_projections
        if integer(row.get("gameweek")) == gameweek
    ]
    estimates: dict[tuple[int, int], list[float]] = {}
    for row in selected:
        fixture_id = integer(row.get("fixture_id"))
        opponent_team_id = integer(row.get("opponent_team_id"))
        clean_sheet_probability = number(row.get("clean_sheet_probability"))
        if fixture_id and opponent_team_id and 0 < clean_sheet_probability < 1:
            estimates.setdefault((fixture_id, opponent_team_id), []).append(
                -math.log(clean_sheet_probability)
            )
    for row in selected:
        values = estimates.get(
            (integer(row.get("fixture_id")), integer(row.get("team_id"))), []
        )
        if values:
            row["model_team_expected_goals"] = statistics.median(values)
    return selected


def fixture_decision_projection(
    projection: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    base_points = number(projection.get("expected_points"))
    base_minutes = number(projection.get("expected_minutes"))
    position = str(projection.get("position"))
    values = context.get("values", {})
    strengths = context.get("strengths", {})
    multiplier = 1.0
    upside_score = 0.0
    reasons: list[str] = []
    adjustment_components: dict[str, float] = {}

    if "availability_probability" in values:
        target = number(values["availability_probability"])
        strength = number(strengths.get("availability_probability"))
        multiplier *= 1 - strength * (1 - target)
        reasons.append(f"availability signal {target:.0%}")
    if "expected_minutes" in values and base_minutes > 0:
        target = number(values["expected_minutes"])
        strength = number(strengths.get("expected_minutes"))
        minutes_ratio = clamp(target / base_minutes, 0.0, 1.25)
        multiplier *= 1 + strength * (minutes_ratio - 1)
        reasons.append(f"external minutes estimate {target:.0f}")
    if "start_probability" in values:
        target = number(values["start_probability"])
        strength = number(strengths.get("start_probability"))
        start_multiplier = 0.65 + 0.7 * target
        multiplier *= 1 + strength * (start_multiplier - 1)
        reasons.append(f"starting probability {target:.0%}")
    if "attack_multiplier" in values:
        target = number(values["attack_multiplier"])
        strength = number(strengths.get("attack_multiplier"))
        multiplier *= 1 + strength * (target - 1)
        reasons.append(f"attacking-role multiplier {target:.2f}")

    model_team_xg = number(projection.get("model_team_expected_goals"))
    target_team_xg = number(values.get("team_expected_goals"))
    team_xg_strength = number(strengths.get("team_expected_goals"))
    if not target_team_xg and "team_score_probability" in values:
        score_probability = clamp(
            number(values.get("team_score_probability")), 0, 0.99
        )
        target_team_xg = -math.log(max(0.01, 1 - score_probability))
        team_xg_strength = number(strengths.get("team_score_probability"))
    if model_team_xg > 0 and target_team_xg > 0 and team_xg_strength > 0:
        raw_attack_ratio = clamp(target_team_xg / model_team_xg, 0.65, 1.60)
        attack_ratio = 1 + (
            raw_attack_ratio - 1
        ) * team_xg_strength * MARKET_BLEND_WEIGHT
        attack_points = (
            number(projection.get("expected_goals")) * GOAL_POINTS.get(position, 0)
            + number(projection.get("expected_assists")) * 3
        )
        adjustment_components["team_attack_market"] = attack_points * (
            attack_ratio - 1
        )
        reasons.append(
            f"team expected goals {target_team_xg:.2f} versus model {model_team_xg:.2f}"
        )

    model_clean_sheet = number(projection.get("clean_sheet_probability"))
    target_clean_sheet = number(values.get("clean_sheet_probability"))
    clean_sheet_strength = number(strengths.get("clean_sheet_probability"))
    decision_clean_sheet = model_clean_sheet
    if (
        0 < model_clean_sheet < 1
        and 0 < target_clean_sheet < 1
        and clean_sheet_strength > 0
    ):
        decision_clean_sheet = model_clean_sheet + (
            target_clean_sheet - model_clean_sheet
        ) * clean_sheet_strength * MARKET_BLEND_WEIGHT
        clean_sheet_points = CLEAN_SHEET_POINTS.get(position, 0)
        if clean_sheet_points:
            component_clean_sheet_points = number(
                projection.get("component_clean_sheet_points")
            )
            points_per_probability = (
                component_clean_sheet_points / model_clean_sheet
                if component_clean_sheet_points > 0
                else clean_sheet_points * min(1.0, base_minutes / 60)
            )
            points_per_probability = min(
                clean_sheet_points * 1.05, points_per_probability
            )
            adjustment_components["clean_sheet_market"] = (
                decision_clean_sheet - model_clean_sheet
            ) * points_per_probability
        if position in {"Goalkeeper", "Defender"}:
            appearance_probability = number(
                projection.get("appearance_probability")
            ) or min(1.0, base_minutes / 60)
            model_lambda = -math.log(model_clean_sheet)
            decision_lambda = -math.log(decision_clean_sheet)
            adjustment_components["goals_conceded_market"] = -appearance_probability * (
                _expected_goals_conceded_deductions(decision_lambda)
                - _expected_goals_conceded_deductions(model_lambda)
            )
        reasons.append(
            f"clean sheet probability {target_clean_sheet:.0%} versus model {model_clean_sheet:.0%}"
        )

    upside_weights = {
        "anytime_goal_probability": 0.50,
        "team_score_probability": 0.30,
        "clean_sheet_probability": 0.25,
        "match_win_probability": 0.05,
        "penalty_taker_probability": 0.15,
        "set_piece_share": 0.10,
    }
    for signal_type, importance in upside_weights.items():
        if signal_type not in values:
            continue
        target = number(values[signal_type])
        strength = number(strengths.get(signal_type))
        upside_score += importance * target * strength
        if signal_type not in {"clean_sheet_probability"}:
            reasons.append(f"{signal_type.replace('_', ' ')} {target:.0%}")

    market_adjustment = sum(adjustment_components.values())
    multiplier = clamp(multiplier, 0.0, 1.35)
    decision_points = max(0.0, (base_points + market_adjustment) * multiplier)
    return {
        "fixture_id": integer(projection.get("fixture_id")),
        "model_expected_points": round(base_points, 4),
        "decision_expected_points": round(decision_points, 4),
        "context_multiplier": round(
            decision_points / base_points if base_points else 1.0, 4
        ),
        "market_adjustment_points": round(market_adjustment, 4),
        "market_adjustment_components": {
            key: round(value, 4)
            for key, value in adjustment_components.items()
        },
        "model_team_expected_goals": round(model_team_xg, 4),
        "market_team_expected_goals": (
            round(target_team_xg, 4) if target_team_xg else None
        ),
        "model_clean_sheet_probability": round(model_clean_sheet, 4),
        "decision_clean_sheet_probability": round(decision_clean_sheet, 4),
        "external_upside_score": round(min(1.0, upside_score), 4),
        "context_signal_count": integer(context.get("signal_count")),
        "context_signal_ids": context.get("signal_ids", []),
        "context_source_ids": context.get("source_ids", []),
        "context_reasons": reasons,
    }


def aggregate_fixture_decisions(
    horizon: dict[str, Any], fixture_decisions: list[dict[str, Any]]
) -> dict[str, Any]:
    base_points = horizon_value(horizon, 1)
    fixture_base = sum(
        number(row.get("model_expected_points")) for row in fixture_decisions
    )
    residual = base_points - fixture_base
    decision_points = max(
        0.0,
        residual
        + sum(number(row.get("decision_expected_points")) for row in fixture_decisions),
    )
    signal_ids = list(
        dict.fromkeys(
            signal_id
            for row in fixture_decisions
            for signal_id in row.get("context_signal_ids", [])
        )
    )
    source_ids = sorted(
        {
            source_id
            for row in fixture_decisions
            for source_id in row.get("context_source_ids", [])
        }
    )
    return {
        "model_expected_points": round(base_points, 3),
        "context_multiplier": round(
            decision_points / base_points if base_points else 1.0, 4
        ),
        "decision_expected_points": round(decision_points, 3),
        "market_adjustment_points": round(
            sum(
                number(row.get("market_adjustment_points"))
                for row in fixture_decisions
            ),
            3,
        ),
        "external_upside_score": round(
            min(
                1.0,
                sum(
                    number(row.get("external_upside_score"))
                    for row in fixture_decisions
                ),
            ),
            4,
        ),
        "context_signal_count": len(signal_ids),
        "context_signal_ids": signal_ids,
        "context_source_ids": source_ids,
        "context_reasons": list(
            dict.fromkeys(
                reason
                for row in fixture_decisions
                for reason in row.get("context_reasons", [])
            )
        ),
        "fixture_decisions": fixture_decisions,
    }


def selection_risk_adjustment(
    player: dict[str, Any],
    horizon: dict[str, Any],
    projection: dict[str, Any],
    target_gameweek: int | None,
) -> dict[str, Any]:
    """Apply epistemic risk only to selection, never to the raw forecast.

    Outcome variance is valuable for attackers and is handled in captaincy. This
    adjustment instead targets evidence that the point estimate itself is
    unreliable: a mismatch with observed starts/minutes, an availability flag,
    or disagreement between the control and component models.
    """

    decision_points = number(projection.get("decision_expected_points"))
    expected_minutes = horizon_value(horizon, 1, "expected_minutes")
    completed_gameweeks = max(0, integer(target_gameweek) - 1)
    observed_fixture_count = integer(horizon.get("current_season_fixture_count"))
    if observed_fixture_count <= 0:
        observed_fixture_count = completed_gameweeks
    minutes_penalty = 0.0
    observed_usage = None
    if observed_fixture_count and expected_minutes > 0:
        start_rate = clamp(
            number(player.get("starts")) / observed_fixture_count, 0.0, 1.0
        )
        minute_share = clamp(
            number(player.get("minutes")) / (90 * observed_fixture_count),
            0.0,
            1.0,
        )
        observed_usage = 0.65 * start_rate + 0.35 * minute_share
        projected_usage = clamp(expected_minutes / 90, 0.0, 1.0)
        usage_gap = max(0.0, projected_usage - observed_usage)
        minutes_penalty = decision_points * MINUTES_RISK_WEIGHT * usage_gap

    chance = player.get("chance_of_playing_next_round")
    status = str(player.get("status") or "a").lower()
    availability_penalty = 0.0
    if chance not in {None, ""}:
        availability_penalty = decision_points * 0.35 * (
            1 - clamp(number(chance) / 100, 0.0, 1.0)
        )
    elif status not in {"a", ""}:
        availability_penalty = decision_points * 0.18

    control_points = horizon_value(horizon, 1, "control_expected_points")
    component_points = horizon_value(
        horizon, 1, "component_expected_points"
    )
    component_mean_active = (
        str(horizon.get("ensemble_status") or "")
        == "recommended_for_live_promotion"
        and number(horizon.get("ensemble_point_weight")) > 0
    )
    model_disagreement = (
        abs(control_points - component_points)
        if component_mean_active and control_points > 0 and component_points > 0
        else 0.0
    )
    component_expected_minutes = horizon_value(
        horizon, 1, "component_expected_minutes"
    )
    projected_usage = (
        clamp(expected_minutes / 90, 0.0, 1.0) if expected_minutes > 0 else 0.0
    )
    role_supported_disagreement = 0.0
    if (
        model_disagreement > 0
        and observed_usage is not None
        and expected_minutes > 0
        and component_expected_minutes > 0
        and observed_usage + 0.05 >= projected_usage
        and number(projection.get("market_adjustment_points")) > 0
    ):
        component_minutes_gap = max(
            0.0, expected_minutes - component_expected_minutes
        )
        minutes_explained_points = control_points * clamp(
            component_minutes_gap / expected_minutes, 0.0, 1.0
        )
        role_supported_disagreement = min(
            model_disagreement, minutes_explained_points
        )
    penalised_model_disagreement = max(
        0.0, model_disagreement - role_supported_disagreement
    )
    disagreement_penalty = min(
        0.75, MODEL_DISAGREEMENT_WEIGHT * penalised_model_disagreement
    )
    total_penalty = min(
        decision_points * MAX_SELECTION_RISK_SHARE,
        minutes_penalty + availability_penalty + disagreement_penalty,
    )
    selection_points = max(0.0, decision_points - total_penalty)
    points_p90 = horizon_value(horizon, 1, "points_p90")
    probability_10_plus = horizon_value(horizon, 1, "probability_10_plus")
    probability_15_plus = horizon_value(horizon, 1, "probability_15_plus")
    position = str(player.get("position") or horizon.get("position"))
    captain_score = (
        selection_points
        + 0.15 * max(0.0, points_p90 - decision_points)
        + 0.8 * probability_10_plus
        + 0.5 * probability_15_plus
        - (0.35 if position in {"Goalkeeper", "Defender"} else 0.0)
    )
    reasons = []
    if minutes_penalty > 0.05:
        reasons.append(
            f"observed usage {observed_usage:.0%} trails projected minutes"
        )
    if availability_penalty > 0.05:
        reasons.append("official availability uncertainty")
    if role_supported_disagreement > 0.05:
        reasons.append(
            "component disagreement partly explained by a minutes gap contradicted "
            "by observed usage and positive market context"
        )
    if disagreement_penalty > 0.05:
        reasons.append(
            f"unexplained control/component disagreement {penalised_model_disagreement:.2f} points"
        )
    return {
        "selection_expected_points": round(selection_points, 3),
        "selection_risk_penalty": round(total_penalty, 3),
        "minutes_risk_penalty": round(minutes_penalty, 3),
        "availability_risk_penalty": round(availability_penalty, 3),
        "model_disagreement_penalty": round(disagreement_penalty, 3),
        "raw_model_disagreement": round(model_disagreement, 3),
        "penalised_model_disagreement": round(penalised_model_disagreement, 3),
        "role_supported_disagreement": round(role_supported_disagreement, 3),
        "component_expected_minutes_next_1": round(component_expected_minutes, 2),
        "observed_fixture_count": observed_fixture_count,
        "observed_usage_rate": (
            round(observed_usage, 4) if observed_usage is not None else None
        ),
        "captain_score": round(captain_score, 4),
        "selection_risk_reasons": reasons,
    }


def decision_projection(
    row: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    base_points = horizon_value(row, 1)
    base_minutes = horizon_value(row, 1, "expected_minutes")
    values = context.get("values", {})
    strengths = context.get("strengths", {})
    multiplier = 1.0
    upside_score = 0.0
    reasons: list[str] = []

    if "availability_probability" in values:
        target = number(values["availability_probability"])
        strength = number(strengths.get("availability_probability"))
        multiplier *= 1 - strength * (1 - target)
        reasons.append(f"availability signal {target:.0%}")
    if "expected_minutes" in values and base_minutes > 0:
        target = number(values["expected_minutes"])
        strength = number(strengths.get("expected_minutes"))
        minutes_ratio = max(0.0, min(1.25, target / base_minutes))
        multiplier *= 1 + strength * (minutes_ratio - 1)
        reasons.append(f"external minutes estimate {target:.0f}")
    if "start_probability" in values:
        target = number(values["start_probability"])
        strength = number(strengths.get("start_probability"))
        start_multiplier = 0.65 + 0.7 * target
        multiplier *= 1 + strength * (start_multiplier - 1)
        reasons.append(f"starting probability {target:.0%}")
    if "attack_multiplier" in values:
        target = number(values["attack_multiplier"])
        strength = number(strengths.get("attack_multiplier"))
        multiplier *= 1 + strength * (target - 1)
        reasons.append(f"attacking-role multiplier {target:.2f}")

    upside_weights = {
        "anytime_goal_probability": 0.50,
        "team_score_probability": 0.30,
        "clean_sheet_probability": 0.25,
        "match_win_probability": 0.05,
        "penalty_taker_probability": 0.15,
        "set_piece_share": 0.10,
    }
    for signal_type, importance in upside_weights.items():
        if signal_type not in values:
            continue
        target = number(values[signal_type])
        strength = number(strengths.get(signal_type))
        upside_score += importance * target * strength
        reasons.append(f"{signal_type.replace('_', ' ')} {target:.0%}")
    if "team_expected_goals" in values:
        target = number(values["team_expected_goals"])
        reasons.append(f"bookmaker-derived team expected goals {target:.2f}")

    multiplier = max(0.0, min(1.35, multiplier))
    decision_points = base_points * multiplier
    return {
        "model_expected_points": round(base_points, 3),
        "context_multiplier": round(multiplier, 4),
        "decision_expected_points": round(decision_points, 3),
        "external_upside_score": round(min(1.0, upside_score), 4),
        "context_signal_count": integer(context.get("signal_count")),
        "context_signal_ids": context.get("signal_ids", []),
        "context_source_ids": context.get("source_ids", []),
        "context_reasons": reasons,
    }


def optimise_lineup(
    squad_rows: list[dict[str, Any]],
    fixtures_by_player: dict[int, list[dict[str, Any]]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not squad_rows:
        return [], []
    player_by_id = {
        integer(row.get("player_id")): row for row in squad_rows
    }
    squad_ids = tuple(player_by_id)
    points = {
        player_id: number(
            row.get("selection_expected_points")
            if row.get("selection_expected_points") not in {None, ""}
            else row.get("decision_expected_points")
        )
        for player_id, row in player_by_id.items()
    }
    _, starter_ids, _ = optimise_gameweek_lineup(
        squad_ids,
        player_by_id,
        points,
        fixtures_by_player,
        risk_profile="balanced",
    )
    selected_ids = set(starter_ids)
    starters = [player_by_id[player_id] for player_id in starter_ids]
    bench = sorted(
        (row for row in squad_rows if integer(row.get("player_id")) not in selected_ids),
        key=lambda item: (
            str(item.get("position")) != "Goalkeeper",
            number(
                item.get("selection_expected_points")
                if item.get("selection_expected_points") not in {None, ""}
                else item.get("decision_expected_points")
            ),
        ),
        reverse=True,
    )
    return starters, bench


def build_decision_support(
    horizons: list[dict[str, Any]],
    players: list[dict[str, Any]],
    my_team: dict[str, Any],
    current_gameweek: dict[str, Any],
    context_signals: list[dict[str, Any]],
    source_registry: dict[str, Any],
    generated_at: str | None = None,
    manager_history: dict[str, Any] | None = None,
    season: str | None = None,
    chip_rules: dict[str, Any] | None = None,
    fixture_projections: list[dict[str, Any]] | None = None,
    scoring_rules_version: str | None = None,
    past_seasons: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    next_event = current_gameweek.get("next") or {}
    target_gameweek = integer(next_event.get("id")) or None
    season_rules = (chip_rules or {}).get("seasons", {}).get(str(season), {})
    chip_state = derive_chip_state(
        manager_history, season, chip_rules, target_gameweek=target_gameweek
    )
    transfer_state = derive_free_transfer_state(
        manager_history, target_gameweek, season_rules
    )
    by_player = {integer(row.get("player_id")): row for row in players}
    by_horizon = {integer(row.get("player_id")): row for row in horizons}
    fixture = {"gameweek": target_gameweek or 0}
    target_fixture_rows = fixture_rows_with_model_team_xg(
        fixture_projections or [], target_gameweek or 0
    )
    target_fixtures_by_player = fixture_rows_by_player(
        target_fixture_rows, target_gameweek or 0
    )

    evaluated: list[dict[str, Any]] = []
    for row in horizons:
        player_id = integer(row.get("player_id"))
        player = by_player.get(player_id, row)
        player_fixture_rows = target_fixtures_by_player.get(player_id, [])
        fixture_decisions = []
        for player_fixture in player_fixture_rows:
            context = resolved_context(
                context_signals,
                source_registry,
                player,
                {
                    "fixture_id": integer(player_fixture.get("fixture_id")),
                    "gameweek": target_gameweek or 0,
                },
                generated_at,
            )
            fixture_decision = fixture_decision_projection(
                player_fixture, context
            )
            fixture_decisions.append(fixture_decision)
            player_fixture["decision_clean_sheet_probability"] = (
                fixture_decision.get("decision_clean_sheet_probability")
            )
        if fixture_decisions:
            projection = aggregate_fixture_decisions(row, fixture_decisions)
        else:
            context = resolved_context(
                context_signals,
                source_registry,
                player,
                fixture,
                generated_at,
            )
            projection = decision_projection(row, context)
        projection.update(
            selection_risk_adjustment(
                player, row, projection, target_gameweek
            )
        )
        evaluated.append(
            {
                "player_id": player_id,
                "web_name": row.get("web_name"),
                "team_id": integer(row.get("team_id")),
                "team_name": row.get("team_name"),
                "position": row.get("position"),
                "price": number(row.get("price")),
                "ownership_percent": ownership(player),
                "expected_points_next_3": horizon_value(row, 3),
                "points_p90_next_1": horizon_value(row, 1, "points_p90"),
                "probability_10_plus_next_1": horizon_value(
                    row, 1, "probability_10_plus"
                ),
                "probability_15_plus_next_1": horizon_value(
                    row, 1, "probability_15_plus"
                ),
                **projection,
            }
        )

    squad = my_team.get("squad") if my_team.get("available") else []
    squad_ids = {integer(item.get("player_id")) for item in squad or []}
    squad_rows = [row for row in evaluated if integer(row.get("player_id")) in squad_ids]
    starters, bench = optimise_lineup(
        squad_rows, target_fixtures_by_player
    )
    lineup_correlation = lineup_correlation_analysis(
        [integer(row.get("player_id")) for row in starters],
        {integer(row.get("player_id")): row for row in squad_rows},
        target_fixtures_by_player,
    )
    captain_pool = sorted(
        starters,
        key=lambda row: (
            number(row.get("captain_score")),
            number(row.get("selection_expected_points")),
            number(row.get("external_upside_score")),
            number(row.get("probability_10_plus_next_1")),
            number(row.get("points_p90_next_1")),
        ),
        reverse=True,
    )

    bank = number((my_team.get("entry_history") or {}).get("bank")) / 10
    squad_team_counts: dict[int, int] = {}
    for item in squad or []:
        player = by_player.get(integer(item.get("player_id")), {})
        team_id = integer(player.get("team_id"))
        squad_team_counts[team_id] = squad_team_counts.get(team_id, 0) + 1

    transfer_candidates: list[dict[str, Any]] = []
    for outgoing in squad_rows:
        outgoing_horizon = by_horizon.get(integer(outgoing.get("player_id")), {})
        selling_price = next(
            (
                number(item.get("selling_price")) / 10
                for item in squad or []
                if integer(item.get("player_id")) == integer(outgoing.get("player_id"))
                and item.get("selling_price") not in {None, ""}
            ),
            number(outgoing.get("price")),
        )
        budget = selling_price + bank
        for incoming in evaluated:
            if integer(incoming.get("player_id")) in squad_ids:
                continue
            if incoming.get("position") != outgoing.get("position"):
                continue
            if number(incoming.get("price")) > budget + 1e-9:
                continue
            incoming_team = integer(incoming.get("team_id"))
            outgoing_team = integer(outgoing.get("team_id"))
            resulting_team_count = squad_team_counts.get(incoming_team, 0)
            if incoming_team != outgoing_team:
                resulting_team_count += 1
            if resulting_team_count > 3:
                continue
            gain = number(incoming.get("expected_points_next_3")) - horizon_value(
                outgoing_horizon, 3
            )
            if gain <= 0:
                continue
            hit_cost = transfer_hit_cost(
                1,
                transfer_state.get("available"),
                integer(transfer_state.get("hit_cost")) or 4,
            )
            net_gain = gain - hit_cost if hit_cost is not None else gain
            if net_gain <= 0:
                continue
            transfer_candidates.append(
                {
                    "sell": {
                        "player_id": outgoing.get("player_id"),
                        "web_name": outgoing.get("web_name"),
                        "price": selling_price,
                        "expected_points_next_3": horizon_value(outgoing_horizon, 3),
                    },
                    "buy": {
                        "player_id": incoming.get("player_id"),
                        "web_name": incoming.get("web_name"),
                        "team_name": incoming.get("team_name"),
                        "price": incoming.get("price"),
                        "expected_points_next_3": incoming.get("expected_points_next_3"),
                    },
                    "three_gameweek_gain": round(gain, 3),
                    "transfer_hit_cost": hit_cost,
                    "net_three_gameweek_gain": round(net_gain, 3),
                    "free_transfers_before": transfer_state.get("available"),
                    "money_remaining": round(budget - number(incoming.get("price")), 1),
                    "context_signal_ids": incoming.get("context_signal_ids", []),
                }
            )
    transfer_candidates.sort(
        key=lambda row: number(row.get("net_three_gameweek_gain")), reverse=True
    )

    differentials = sorted(
        (
            row
            for row in evaluated
            if row.get("player_id") not in squad_ids
            and 0 < number(row.get("ownership_percent")) <= 10
            and number(row.get("decision_expected_points")) > 0
        ),
        key=lambda row: (
            number(row.get("decision_expected_points")),
            number(row.get("external_upside_score")),
            number(row.get("probability_10_plus_next_1")),
        ),
        reverse=True,
    )[:15]

    bench_points = sum(
        number(row.get("selection_expected_points")) for row in bench
    )
    captain = captain_pool[0] if captain_pool else None
    first_gameweek_multiplier = {
        integer(row.get("player_id")): (
            number(row.get("selection_expected_points"))
            / number(row.get("model_expected_points"))
            if number(row.get("model_expected_points")) > 0
            else 1.0
        )
        for row in evaluated
    }
    first_gameweek_captain_scores = {
        integer(row.get("player_id")): number(row.get("captain_score"))
        for row in evaluated
        if integer(row.get("player_id"))
    }
    multi_gameweek_plan = optimise_multi_gameweek_route(
        fixture_projections or [],
        [
            {
                **player,
                **{
                    key: value
                    for key, value in (by_horizon.get(integer(player.get("player_id"))) or {}).items()
                    if key in {"web_name", "team_id", "team_name", "position", "price"}
                },
            }
            for player in players
        ],
        squad or [],
        bank,
        transfer_state.get("available"),
        integer(transfer_state.get("maximum")) or 5,
        integer(transfer_state.get("hit_cost")) or 4,
        target_gameweek,
        first_gameweek_multiplier=first_gameweek_multiplier,
        first_gameweek_captain_scores=first_gameweek_captain_scores,
    )
    status = "ready" if target_gameweek and any(
        number(row.get("decision_expected_points")) > 0 for row in evaluated
    ) else "waiting_for_future_fixtures"
    if status != "ready":
        starters = []
        bench = []
        captain_pool = []
        captain = None
        transfer_candidates = []
        differentials = []
        bench_points = 0
        multi_gameweek_plan = {
            "status": "waiting_for_projections",
            "horizon_gameweeks": [],
            "routes": [],
        }
    chip_optimisation = optimise_chip_plan(
        fixture_projections or [],
        players,
        squad or [],
        bank,
        chip_state,
        multi_gameweek_plan,
        target_gameweek,
        first_gameweek_multiplier=first_gameweek_multiplier,
    )
    initial_squad_plan = build_initial_squad_plan(
        players,
        horizons,
        fixture_projections or [],
        current_gameweek,
        season,
        scoring_rules_version,
        first_gameweek_multiplier=first_gameweek_multiplier,
        past_seasons=past_seasons,
    )
    return {
        "generated_at": generated_at,
        "decision_version": DECISION_VERSION,
        "model_version": horizons[0].get("model_version") if horizons else None,
        "status": status,
        "target_gameweek": target_gameweek,
        "team_id": my_team.get("team_id"),
        "squad_available": bool(squad),
        "bank": round(bank, 1),
        "free_transfer_state": transfer_state,
        "recommended_lineup": starters,
        "bench_order": bench,
        "lineup_correlation": lineup_correlation,
        "captaincy": {
            "captain": captain,
            "vice_captain": captain_pool[1] if len(captain_pool) > 1 else None,
            "alternatives": captain_pool[:5],
            "principle": (
                "Expected FPL points is primary; 10+ probability and upper-tail points "
                "break close calls."
            ),
        },
        "transfer_shortlist": transfer_candidates[:20],
        "multi_gameweek_plan": multi_gameweek_plan,
        "chip_optimisation": chip_optimisation,
        "initial_squad_plan": initial_squad_plan,
        "differentials": differentials,
        "chip_indicators": {
            "chip_state": chip_state,
            "bench_boost_expected_bench_points": round(bench_points, 3),
            "triple_captain_expected_extra_points": round(
                number(captain.get("decision_expected_points")) if captain else 0, 3
            ),
            "wildcard_candidate_transfer_count": sum(
                number(row.get("net_three_gameweek_gain")) >= 1.5
                for row in transfer_candidates[:20]
            ),
            "advisory_only": False,
            "optimisation_status": chip_optimisation.get("status"),
            "current_gameweek_recommendation": chip_optimisation.get("recommendation"),
            "reason": (
                "Phase 18 compares each available chip with the no-chip transfer routes, "
                "accounts for half-season expiry and enforces one chip per Gameweek."
            ),
        },
        "audit": {
            "players_evaluated": len(evaluated),
            "context_adjusted_players": sum(
                number(row.get("context_signal_count")) > 0 for row in evaluated
            ),
            "market_adjusted_players": sum(
                abs(number(row.get("market_adjustment_points"))) > 1e-9
                for row in evaluated
            ),
            "selection_risk_adjusted_players": sum(
                number(row.get("selection_risk_penalty")) > 0.05
                for row in evaluated
            ),
            "unmodified_model_forecast_retained": True,
            "decision_layer_market_adjustment": True,
        },
    }


def write_decision_support(path: Path, decision: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(decision, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
