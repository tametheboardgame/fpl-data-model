from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.external_context import number, resolved_context


DECISION_VERSION = "fpl-decisions-1.0"


def integer(value: Any) -> int:
    return int(number(value))


def ownership(player: dict[str, Any]) -> float:
    return number(player.get("selected_by_percent"))


def horizon_value(row: dict[str, Any], horizon: int, field: str = "expected_points") -> float:
    return number(row.get(f"{field}_next_{horizon}"))


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
        "clean_sheet_probability": 0.25,
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


def optimise_lineup(squad_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not squad_rows:
        return [], []
    by_position: dict[str, list[dict[str, Any]]] = {}
    for row in squad_rows:
        by_position.setdefault(str(row.get("position")), []).append(row)
    for rows in by_position.values():
        rows.sort(key=lambda item: number(item.get("decision_expected_points")), reverse=True)

    starters: list[dict[str, Any]] = []
    minimums = {"Goalkeeper": 1, "Defender": 3, "Midfielder": 2, "Forward": 1}
    for position, minimum in minimums.items():
        starters.extend(by_position.get(position, [])[:minimum])
    selected_ids = {integer(row.get("player_id")) for row in starters}
    remaining = sorted(
        (row for row in squad_rows if integer(row.get("player_id")) not in selected_ids),
        key=lambda item: number(item.get("decision_expected_points")),
        reverse=True,
    )
    for row in remaining:
        if len(starters) >= 11:
            break
        position = str(row.get("position"))
        if position == "Goalkeeper":
            continue
        if position == "Defender" and sum(x.get("position") == position for x in starters) >= 5:
            continue
        if position == "Midfielder" and sum(x.get("position") == position for x in starters) >= 5:
            continue
        if position == "Forward" and sum(x.get("position") == position for x in starters) >= 3:
            continue
        starters.append(row)
    selected_ids = {integer(row.get("player_id")) for row in starters}
    bench = sorted(
        (row for row in squad_rows if integer(row.get("player_id")) not in selected_ids),
        key=lambda item: (
            str(item.get("position")) != "Goalkeeper",
            number(item.get("decision_expected_points")),
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
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    next_event = current_gameweek.get("next") or {}
    target_gameweek = integer(next_event.get("id")) or None
    by_player = {integer(row.get("player_id")): row for row in players}
    by_horizon = {integer(row.get("player_id")): row for row in horizons}
    fixture = {"gameweek": target_gameweek or 0}

    evaluated: list[dict[str, Any]] = []
    for row in horizons:
        player_id = integer(row.get("player_id"))
        player = by_player.get(player_id, row)
        context = resolved_context(
            context_signals,
            source_registry,
            player,
            fixture,
            generated_at,
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
                **decision_projection(row, context),
            }
        )

    squad = my_team.get("squad") if my_team.get("available") else []
    squad_ids = {integer(item.get("player_id")) for item in squad or []}
    squad_rows = [row for row in evaluated if integer(row.get("player_id")) in squad_ids]
    starters, bench = optimise_lineup(squad_rows)
    captain_pool = sorted(
        starters,
        key=lambda row: (
            number(row.get("decision_expected_points")),
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
                    "money_remaining": round(budget - number(incoming.get("price")), 1),
                    "context_signal_ids": incoming.get("context_signal_ids", []),
                }
            )
    transfer_candidates.sort(
        key=lambda row: number(row.get("three_gameweek_gain")), reverse=True
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

    bench_points = sum(number(row.get("decision_expected_points")) for row in bench)
    captain = captain_pool[0] if captain_pool else None
    status = "ready" if target_gameweek and any(
        number(row.get("decision_expected_points")) > 0 for row in evaluated
    ) else "waiting_for_future_fixtures"
    return {
        "generated_at": generated_at,
        "decision_version": DECISION_VERSION,
        "model_version": horizons[0].get("model_version") if horizons else None,
        "status": status,
        "target_gameweek": target_gameweek,
        "team_id": my_team.get("team_id"),
        "squad_available": bool(squad),
        "bank": round(bank, 1),
        "recommended_lineup": starters,
        "bench_order": bench,
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
        "differentials": differentials,
        "chip_indicators": {
            "bench_boost_expected_bench_points": round(bench_points, 3),
            "triple_captain_expected_extra_points": round(
                number(captain.get("decision_expected_points")) if captain else 0, 3
            ),
            "wildcard_candidate_transfer_count": sum(
                number(row.get("three_gameweek_gain")) >= 1.5
                for row in transfer_candidates[:20]
            ),
            "advisory_only": True,
            "reason": (
                "Chip recommendations require confirmed blank/double gameweeks and "
                "the manager's remaining-chip state."
            ),
        },
        "audit": {
            "players_evaluated": len(evaluated),
            "context_adjusted_players": sum(
                number(row.get("context_signal_count")) > 0 for row in evaluated
            ),
            "unmodified_model_forecast_retained": True,
        },
    }


def write_decision_support(path: Path, decision: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(decision, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
