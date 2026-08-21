from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.external_context import number


OPERATIONS_VERSION = "fpl-gameweek-operations-1.3"
FREEZE_WINDOW_HOURS = 8
NORMAL_DATA_MAX_AGE_HOURS = 8
DEADLINE_DATA_MAX_AGE_HOURS = 3
FINAL_DATA_MAX_AGE_HOURS = 2
FIRM_ADVICE_WINDOW_HOURS = 24
FINAL_ADVICE_WINDOW_HOURS = 4


def integer(value: Any) -> int:
    return int(number(value))


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _player(player_id: int, players: dict[int, dict[str, Any]], points: dict[int, float]) -> dict[str, Any]:
    row = players.get(player_id, {})
    chance = row.get("chance_of_playing_next_round")
    return {
        "player_id": player_id,
        "web_name": row.get("web_name") or f"Player {player_id}",
        "team_id": integer(row.get("team_id")),
        "team_name": row.get("team_name"),
        "position": row.get("position"),
        "price": number(row.get("price")),
        "expected_points": round(points.get(player_id, 0), 3),
        "availability_status": str(row.get("status") or "a"),
        "chance_of_playing": integer(chance) if chance not in {None, ""} else None,
        "news": str(row.get("news") or "").strip(),
        "news_added": row.get("news_added"),
    }


def _route_move(decision: dict[str, Any], gameweek: int) -> dict[str, Any]:
    route = (decision.get("multi_gameweek_plan") or {}).get("recommended_route") or {}
    return next(
        (
            move
            for move in route.get("gameweek_plan", [])
            if integer(move.get("gameweek")) == gameweek
        ),
        {},
    )


def _selection(
    decision: dict[str, Any],
    players: dict[int, dict[str, Any]],
    horizons: list[dict[str, Any]],
    my_team: dict[str, Any],
    gameweek: int,
) -> dict[str, Any]:
    points = {
        integer(row.get("player_id")): number(row.get("expected_points_next_1"))
        for row in horizons
    }
    initial_plan = decision.get("initial_squad_plan") or {}
    points.update(
        {
            integer(row.get("player_id")): number(
                row.get("gameweek_1_expected_points")
            )
            for row in initial_plan.get("recommended_squad", [])
            if integer(row.get("player_id"))
            and row.get("gameweek_1_expected_points") not in {None, ""}
        }
    )
    points.update(
        {
            integer(row.get("player_id")): number(
                row.get("decision_expected_points")
            )
            for row in (decision.get("recommended_lineup") or [])
            + (decision.get("bench_order") or [])
            if integer(row.get("player_id"))
            and row.get("decision_expected_points") not in {None, ""}
        }
    )
    if (
        gameweek == 1
        and (not my_team.get("available") or not my_team.get("squad"))
        and initial_plan.get("recommended_squad")
    ):
        squad_ids = [
            integer(row.get("player_id"))
            for row in initial_plan.get("recommended_squad", [])
        ]
        starter_ids = [
            integer(row.get("player_id"))
            for row in initial_plan.get("recommended_starting_xi", [])
        ]
        bench_ids = [
            integer(row.get("player_id"))
            for row in initial_plan.get("recommended_bench_order", [])
        ]
        captain_id = integer((initial_plan.get("captain") or {}).get("player_id"))
        vice_id = integer(
            (initial_plan.get("vice_captain") or {}).get("player_id")
        )
        selected_variant = next(
            (
                row
                for row in initial_plan.get("strategy_comparison", [])
                if row.get("strategy")
                == initial_plan.get("recommended_strategy")
            ),
            {},
        )
        return {
            "selection_source": "initial_squad_plan",
            "starting_xi": [
                _player(player_id, players, points) for player_id in starter_ids
            ],
            "bench_order": [
                _player(player_id, players, points) for player_id in bench_ids
            ],
            "captain": _player(captain_id, players, points) if captain_id else None,
            "vice_captain": _player(vice_id, players, points) if vice_id else None,
            "transfers": [],
            "transfer_action": "select_initial_squad",
            "free_transfers_before": 0,
            "hit_cost": 0,
            "bank_after": initial_plan.get("bank"),
            "expected_points": next(
                (
                    row.get("gameweek_1_expected_points_including_captain")
                    for row in initial_plan.get("strategy_comparison", [])
                    if row.get("strategy")
                    == initial_plan.get("recommended_strategy")
                ),
                None,
            ),
            "net_expected_points": next(
                (
                    row.get("gameweek_1_expected_points_including_captain")
                    for row in initial_plan.get("strategy_comparison", [])
                    if row.get("strategy")
                    == initial_plan.get("recommended_strategy")
                ),
                None,
            ),
            "six_gameweek_net_gain_vs_hold": (
                (initial_plan.get("planned_transfer_route") or {})
                .get("recommended_route", {})
                .get("net_gain_vs_hold")
            ),
            "six_gameweek_total_hit_cost": (
                (initial_plan.get("planned_transfer_route") or {})
                .get("recommended_route", {})
                .get("total_hit_cost")
            ),
            "squad_player_ids": squad_ids,
            "lineup_correlation": selected_variant.get(
                "lineup_correlation", {}
            ),
        }
    move = _route_move(decision, gameweek)
    transfers = move.get("transfers", []) or []
    squad_ids = {
        integer(row.get("player_id"))
        for row in my_team.get("squad", [])
        if integer(row.get("player_id"))
    }
    for transfer in transfers:
        squad_ids.discard(integer(transfer.get("sell_player_id")))
        squad_ids.add(integer(transfer.get("buy_player_id")))

    starter_ids = [integer(value) for value in move.get("starter_player_ids", [])]
    if not starter_ids:
        starter_ids = [
            integer(row.get("player_id"))
            for row in decision.get("recommended_lineup", [])
        ]
    captain_id = integer(move.get("captain_player_id"))
    if not captain_id:
        captain_id = integer(
            ((decision.get("captaincy") or {}).get("captain") or {}).get("player_id")
        )
    vice_id = integer(
        ((decision.get("captaincy") or {}).get("vice_captain") or {}).get("player_id")
    )
    if vice_id not in starter_ids or vice_id == captain_id:
        vice_id = next(
            (
                player_id
                for player_id in sorted(starter_ids, key=lambda item: points.get(item, 0), reverse=True)
                if player_id != captain_id
            ),
            0,
        )

    if not squad_ids:
        squad_ids = set(starter_ids).union(
            integer(row.get("player_id")) for row in decision.get("bench_order", [])
        )
    bench_ids = list(squad_ids.difference(starter_ids))
    bench_ids.sort(
        key=lambda player_id: (
            str(players.get(player_id, {}).get("position")) != "Goalkeeper",
            points.get(player_id, 0),
        ),
        reverse=True,
    )
    transfers_public = [
        {
            "sell_player_id": integer(row.get("sell_player_id")),
            "sell": row.get("sell") or players.get(integer(row.get("sell_player_id")), {}).get("web_name"),
            "buy_player_id": integer(row.get("buy_player_id")),
            "buy": row.get("buy") or players.get(integer(row.get("buy_player_id")), {}).get("web_name"),
            "sell_price": row.get("sell_price"),
            "buy_price": row.get("buy_price"),
        }
        for row in transfers
    ]
    route = (decision.get("multi_gameweek_plan") or {}).get("recommended_route") or {}
    return {
        "selection_source": "registered_team",
        "starting_xi": [_player(player_id, players, points) for player_id in starter_ids],
        "bench_order": [_player(player_id, players, points) for player_id in bench_ids],
        "captain": _player(captain_id, players, points) if captain_id else None,
        "vice_captain": _player(vice_id, players, points) if vice_id else None,
        "transfers": transfers_public,
        "transfer_action": "make_transfers" if transfers_public else "roll_or_hold",
        "free_transfers_before": move.get("free_transfers_before", (decision.get("free_transfer_state") or {}).get("available")),
        "hit_cost": integer(move.get("hit_cost")),
        "bank_after": move.get("bank_after", decision.get("bank")),
        "expected_points": move.get("lineup_expected_points"),
        "net_expected_points": move.get("net_expected_points"),
        "six_gameweek_net_gain_vs_hold": route.get("net_gain_vs_hold"),
        "six_gameweek_total_hit_cost": route.get("total_hit_cost"),
        "lineup_correlation": decision.get("lineup_correlation", {}),
    }


def _chip(decision: dict[str, Any], gameweek: int) -> dict[str, Any]:
    recommendation = (decision.get("chip_optimisation") or {}).get("recommendation")
    if not recommendation:
        return {"action": "unavailable", "chip": None, "reason": "Chip optimisation is not ready."}
    result = {
        "action": recommendation.get("action") or "hold",
        "chip": recommendation.get("chip"),
        "chip_name": recommendation.get("chip_name"),
        "gameweek": integer(recommendation.get("gameweek")) or gameweek,
        "incremental_expected_points": recommendation.get("incremental_expected_points"),
        "reason": recommendation.get("reason"),
    }
    if recommendation.get("next_planned_use"):
        planned = recommendation["next_planned_use"]
        result["next_planned_use"] = {
            "chip": planned.get("chip"),
            "chip_name": planned.get("chip_name"),
            "gameweek": planned.get("gameweek"),
            "incremental_expected_points": planned.get("incremental_expected_points"),
        }
    return result


def _fixture_signature(rows: list[dict[str, Any]], gameweeks: list[int]) -> list[list[Any]]:
    selected = set(gameweeks)
    fixtures = {
        (
            integer(row.get("gameweek")),
            str(row.get("fixture_id") or row.get("fixture") or ""),
            integer(row.get("team_id")),
            integer(row.get("opponent_team_id")),
            str(row.get("kickoff_time") or ""),
        )
        for row in rows
        if integer(row.get("gameweek")) in selected
    }
    return [list(row) for row in sorted(fixtures)]


def _risks(selection: dict[str, Any]) -> list[dict[str, Any]]:
    roles: dict[int, str] = {}
    for row in selection.get("starting_xi", []):
        roles[integer(row.get("player_id"))] = "starting_xi"
    for row in selection.get("bench_order", []):
        roles.setdefault(integer(row.get("player_id")), "bench")
    if selection.get("captain"):
        roles[integer(selection["captain"].get("player_id"))] = "captain"
    result = []
    for row in selection.get("starting_xi", []) + selection.get("bench_order", []):
        chance = row.get("chance_of_playing")
        status = str(row.get("availability_status") or "a").lower()
        news = str(row.get("news") or "").strip()
        if status == "a" and chance in {None, 100} and not news:
            continue
        role = roles.get(integer(row.get("player_id")), "squad")
        severity = "high" if role in {"captain", "starting_xi"} and (status != "a" or (chance is not None and chance < 75)) else "medium"
        result.append(
            {
                "player_id": row.get("player_id"),
                "web_name": row.get("web_name"),
                "role": role,
                "severity": severity,
                "availability_status": status,
                "chance_of_playing": chance,
                "news": news,
                "news_added": row.get("news_added"),
            }
        )
    return result


def _providers(context_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(context_dir.glob("*_status.json")):
        data = read_json(path, {})
        if not isinstance(data, dict):
            continue
        rows.append(
            {
                "file": path.name,
                "provider": data.get("provider") or path.stem,
                "status": data.get("status") or "unknown",
                "generated_at": data.get("generated_at"),
                "required_action": data.get("required_action"),
                "error": data.get("error"),
            }
        )
    return rows


def _warnings(
    decision: dict[str, Any],
    selection: dict[str, Any],
    current_gameweek: dict[str, Any],
    generated: datetime,
    hours_to_deadline: float | None,
    providers: list[dict[str, Any]],
    external_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    source_time = parse_time(current_gameweek.get("generated_at"))
    if hours_to_deadline is not None and 0 <= hours_to_deadline <= FINAL_ADVICE_WINDOW_HOURS:
        max_age = FINAL_DATA_MAX_AGE_HOURS
    elif hours_to_deadline is not None and 0 <= hours_to_deadline <= FREEZE_WINDOW_HOURS:
        max_age = DEADLINE_DATA_MAX_AGE_HOURS
    else:
        max_age = NORMAL_DATA_MAX_AGE_HOURS
    if not source_time:
        warnings.append({"code": "missing_source_timestamp", "severity": "high", "message": "The official FPL data timestamp is missing."})
    else:
        age = max(0.0, (generated - source_time).total_seconds() / 3600)
        if age > max_age:
            warnings.append({"code": "stale_fpl_data", "severity": "high", "message": f"Official FPL data is {age:.1f} hours old; maximum permitted age is {max_age} hours."})
    if decision.get("status") == "ready":
        starters = [integer(row.get("player_id")) for row in selection.get("starting_xi", [])]
        bench = [integer(row.get("player_id")) for row in selection.get("bench_order", [])]
        captain = integer((selection.get("captain") or {}).get("player_id"))
        vice_captain = integer(
            (selection.get("vice_captain") or {}).get("player_id")
        )
        if len(starters) != 11 or len(set(starters)) != 11:
            warnings.append({"code": "invalid_starting_xi", "severity": "high", "message": "The proposed starting XI does not contain 11 unique players."})
        if set(starters).intersection(bench):
            warnings.append({"code": "lineup_bench_overlap", "severity": "high", "message": "At least one player appears in both the starting XI and bench."})
        if captain and captain not in starters:
            warnings.append({"code": "captain_not_starting", "severity": "high", "message": "The proposed captain is not in the starting XI."})
        if vice_captain and (
            vice_captain not in starters or vice_captain == captain
        ):
            warnings.append({"code": "invalid_vice_captain", "severity": "high", "message": "The proposed vice-captain is not a distinct member of the starting XI."})
        if selection.get("selection_source") == "initial_squad_plan":
            squad_ids = [integer(value) for value in selection.get("squad_player_ids", [])]
            positions = Counter(
                str(row.get("position"))
                for row in selection.get("starting_xi", [])
            )
            if len(squad_ids) != 15 or len(set(squad_ids)) != 15 or len(bench) != 4:
                warnings.append({"code": "invalid_initial_squad", "severity": "high", "message": "The proposed initial squad does not contain 15 unique players split into an XI and four-player bench."})
            if not (
                positions.get("Goalkeeper", 0) == 1
                and 3 <= positions.get("Defender", 0) <= 5
                and 2 <= positions.get("Midfielder", 0) <= 5
                and 1 <= positions.get("Forward", 0) <= 3
            ):
                warnings.append({"code": "invalid_starting_formation", "severity": "high", "message": "The proposed initial starting XI does not use a legal FPL formation."})
    for issue in (
        ((decision.get("initial_squad_plan") or {}).get("launch_validation") or {})
        .get("issues", [])
    ):
        warnings.append(
            {
                "code": issue.get("code") or "launch_validation",
                "severity": issue.get("severity") or "high",
                "message": issue.get("message") or "Launch validation requires review.",
            }
        )
    for risk in _risks(selection):
        warnings.append({"code": "player_availability", "severity": risk["severity"], "message": f"{risk['web_name']} has an availability flag ({risk.get('chance_of_playing')}% chance): {risk.get('news') or risk.get('availability_status')}."})
    correlation = selection.get("lineup_correlation") or {}
    if integer(correlation.get("opposing_pair_count")):
        pair_names = [
            f"{row.get('defender')} / {row.get('attacker')}"
            for row in correlation.get("opposing_pairs", [])[:3]
        ]
        warnings.append(
            {
                "code": "opposing_player_correlation",
                "severity": "low",
                "message": (
                    "The starting XI contains negatively correlated opposing "
                    f"players: {', '.join(pair_names)}. This affects variance, "
                    "not mean expected points."
                ),
            }
        )
    for provider in providers:
        if provider.get("status") in {"error", "failed"}:
            warnings.append({"code": "provider_error", "severity": "medium", "message": f"{provider['provider']} is reporting an error."})
        elif provider.get("status") == "plan_blocked":
            warnings.append({"code": "provider_plan_blocked", "severity": "low", "message": f"{provider['provider']} is unavailable under the current plan; recommendations use the remaining sources."})
    if integer(external_summary.get("expired_signal_rows")):
        warnings.append({"code": "expired_context", "severity": "low", "message": f"{integer(external_summary.get('expired_signal_rows'))} external-context signals have expired and are excluded."})
    return warnings


def _operational_readiness(
    decision: dict[str, Any],
    warnings: list[dict[str, Any]],
    freeze: dict[str, Any],
    hours_to_deadline: float | None,
    providers: list[dict[str, Any]],
) -> dict[str, Any]:
    blocking = [
        str(row.get("code"))
        for row in warnings
        if row.get("severity") == "high"
    ]
    launch_validation = (
        (decision.get("initial_squad_plan") or {}).get("launch_validation") or {}
    )
    validation_passed = (
        decision.get("status") == "ready"
        and launch_validation.get("status") == "passed"
    )
    if not validation_passed:
        blocking.append("validation_not_passed")
    inside_freeze = (
        hours_to_deadline is not None
        and 0 <= hours_to_deadline <= FREEZE_WINDOW_HOURS
    )
    if inside_freeze and freeze.get("status") != "frozen":
        blocking.append("deadline_snapshot_not_frozen")
    blocking = list(dict.fromkeys(blocking))

    plan_blocked_team_news = any(
        row.get("status") == "plan_blocked" for row in providers
    )
    late_news_due = (
        hours_to_deadline is not None
        and 0 <= hours_to_deadline <= FIRM_ADVICE_WINDOW_HOURS
    )
    if blocking:
        advice_level = "blocked"
    elif hours_to_deadline is not None and 0 <= hours_to_deadline <= FINAL_ADVICE_WINDOW_HOURS:
        advice_level = "final"
    elif hours_to_deadline is not None and 0 <= hours_to_deadline <= FIRM_ADVICE_WINDOW_HOURS:
        advice_level = "firm"
    else:
        advice_level = "provisional"
    return {
        "advice_level": advice_level,
        "firm_advice_allowed": advice_level in {"firm", "final"},
        "validation_passed": validation_passed,
        "blocking_reasons": blocking,
        "late_team_news_review": {
            "status": "required_before_action" if late_news_due else "not_due",
            "required": late_news_due,
            "reason": (
                "API-Football is plan-blocked, so check official club news and trusted predicted line-ups before applying the recommendation."
                if plan_blocked_team_news
                else "Check late official team news before applying the recommendation."
            ),
        },
    }


def _material_state(report: dict[str, Any]) -> dict[str, Any]:
    selection = report.get("recommendation", {})
    return {
        "status": report.get("status"),
        "target_gameweek": report.get("target_gameweek"),
        "deadline_time": (report.get("deadline") or {}).get("deadline_time"),
        "starting_xi": [row.get("player_id") for row in selection.get("starting_xi", [])],
        "bench": [row.get("player_id") for row in selection.get("bench_order", [])],
        "captain": (selection.get("captain") or {}).get("player_id"),
        "vice_captain": (selection.get("vice_captain") or {}).get("player_id"),
        "transfers": [(row.get("sell_player_id"), row.get("buy_player_id")) for row in selection.get("transfers", [])],
        "chip": report.get("chip_recommendation"),
        "risks": report.get("availability_risks", []),
        "fixture_signature": report.get("fixture_signature", []),
        "warning_codes": sorted((row.get("code"), row.get("severity")) for row in report.get("warnings", [])),
        "advice_level": (report.get("operational_readiness") or {}).get("advice_level"),
        "firm_advice_allowed": (report.get("operational_readiness") or {}).get("firm_advice_allowed"),
        "lineup_correlation": (
            (selection.get("lineup_correlation") or {}).get(
                "negative_correlation_exposure"
            )
        ),
    }


def _changes(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[dict[str, Any]]:
    if not previous:
        return [{"type": "initial_report", "summary": "Initial operational report created."}]
    before = _material_state(previous)
    after = _material_state(current)
    changes = []
    labels = {
        "status": "Operational readiness changed",
        "target_gameweek": "Target Gameweek changed",
        "deadline_time": "Deadline changed",
        "starting_xi": "Starting XI changed",
        "bench": "Bench order changed",
        "captain": "Captain changed",
        "vice_captain": "Vice-captain changed",
        "transfers": "Transfer recommendation changed",
        "chip": "Chip recommendation changed",
        "risks": "Availability information changed",
        "fixture_signature": "Fixture information changed",
        "warning_codes": "Data-quality warning state changed",
        "advice_level": "Deadline advice stage changed",
        "firm_advice_allowed": "Firm-advice safety gate changed",
        "lineup_correlation": "Starting XI correlation exposure changed",
    }
    for key, summary in labels.items():
        if before.get(key) != after.get(key):
            changes.append({"type": key, "summary": summary, "before": before.get(key), "after": after.get(key)})
    return changes


def _freeze_status(
    gameweek: int,
    hours_to_deadline: float | None,
    prospective: dict[str, Any],
) -> dict[str, Any]:
    paths = [
        path
        for path in (prospective.get("index") or {}).get("snapshots", [])
        if f"/gw{gameweek:02d}/" in str(path)
    ]
    if not gameweek or hours_to_deadline is None:
        return {"status": "waiting_for_deadline", "immutable_snapshot": None}
    if hours_to_deadline < 0:
        return {"status": "deadline_passed", "immutable_snapshot": paths[-1] if paths else None}
    if hours_to_deadline > FREEZE_WINDOW_HOURS:
        return {"status": "waiting_for_freeze_window", "window_hours": FREEZE_WINDOW_HOURS, "immutable_snapshot": paths[-1] if paths else None}
    return {
        "status": "frozen" if paths else "snapshot_missing",
        "window_hours": FREEZE_WINDOW_HOURS,
        "immutable_snapshot": paths[-1] if paths else None,
        "snapshot_created_this_run": (prospective.get("index") or {}).get("snapshot_created_this_run"),
    }


def build_gameweek_report(
    decision: dict[str, Any],
    horizons: list[dict[str, Any]],
    players: list[dict[str, Any]],
    my_team: dict[str, Any],
    current_gameweek: dict[str, Any],
    fixture_projections: list[dict[str, Any]],
    external_summary: dict[str, Any],
    prospective: dict[str, Any],
    providers: list[dict[str, Any]],
    generated_at: str,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated = parse_time(generated_at) or datetime.now(timezone.utc)
    next_event = current_gameweek.get("next") or {}
    gameweek = integer(next_event.get("id"))
    deadline = parse_time(next_event.get("deadline_time"))
    hours_to_deadline = round((deadline - generated).total_seconds() / 3600, 3) if deadline else None
    player_by_id = {integer(row.get("player_id")): row for row in players}
    selection = _selection(decision, player_by_id, horizons, my_team, gameweek) if decision.get("status") == "ready" else {
        "starting_xi": [], "bench_order": [], "captain": None, "vice_captain": None,
        "transfers": [], "transfer_action": "unavailable", "hit_cost": 0,
    }
    initial_plan = decision.get("initial_squad_plan") or {}
    route_plan = decision.get("multi_gameweek_plan") or {}
    if (
        selection.get("selection_source") == "initial_squad_plan"
        and initial_plan.get("planned_transfer_route")
    ):
        route_plan = initial_plan.get("planned_transfer_route") or {}
    horizon_gameweeks = route_plan.get("horizon_gameweeks", []) or initial_plan.get(
        "horizon_gameweeks", []
    )
    fixture_signature = _fixture_signature(fixture_projections, horizon_gameweeks)
    freeze = _freeze_status(gameweek, hours_to_deadline, prospective)
    warnings = _warnings(decision, selection, current_gameweek, generated, hours_to_deadline, providers, external_summary)
    if freeze.get("status") == "snapshot_missing":
        warnings.append({
            "code": "deadline_snapshot_missing",
            "severity": "high",
            "message": "The final pre-deadline recommendation snapshot is missing; firm advice is blocked.",
        })
    status = "ready" if decision.get("status") == "ready" else "waiting_for_recommendations"
    if status == "ready" and any(row.get("severity") == "high" for row in warnings):
        status = "review_required"
    readiness = _operational_readiness(
        decision, warnings, freeze, hours_to_deadline, providers
    )
    report = {
        "operations_version": OPERATIONS_VERSION,
        "generated_at": generated.replace(microsecond=0).isoformat(),
        "status": status,
        "decision_status": decision.get("status"),
        "decision_version": decision.get("decision_version"),
        "target_gameweek": gameweek or None,
        "deadline": {
            "deadline_time": deadline.isoformat() if deadline else None,
            "deadline_time_uk": deadline.astimezone(ZoneInfo("Europe/London")).isoformat() if deadline else None,
            "hours_remaining": hours_to_deadline,
        },
        "recommendation": selection,
        "chip_recommendation": _chip(decision, gameweek) if decision.get("status") == "ready" else {"action": "unavailable", "chip": None, "reason": "Decision support is not ready."},
        "six_gameweek_plan": {
            "status": route_plan.get("status"),
            "horizon_gameweeks": horizon_gameweeks,
            "net_gain_vs_hold": (route_plan.get("recommended_route") or {}).get("net_gain_vs_hold"),
            "gameweek_plan": (route_plan.get("recommended_route") or {}).get("gameweek_plan", []),
        },
        "availability_risks": _risks(selection),
        "warnings": warnings,
        "providers": providers,
        "source_freshness": {
            "official_fpl_generated_at": current_gameweek.get("generated_at"),
            "external_context_generated_at": external_summary.get("generated_at"),
            "active_external_signals": external_summary.get("active_signal_rows", 0),
            "expired_external_signals": external_summary.get("expired_signal_rows", 0),
        },
        "fixture_signature": fixture_signature,
        "deadline_freeze": freeze,
        "operational_readiness": readiness,
        "advisory_only": True,
        "automatic_fpl_actions": False,
    }
    changes = _changes(previous, report)
    report["material_changes"] = changes
    report["material_change"] = bool(changes)
    report["change_summary"] = "No material change since the previous report." if not changes else " ".join(change["summary"] for change in changes)
    state_json = json.dumps(_material_state(report), sort_keys=True, separators=(",", ":"))
    report["decision_fingerprint"] = hashlib.sha256(state_json.encode("utf-8")).hexdigest()
    return report


def render_markdown(report: dict[str, Any]) -> str:
    recommendation = report.get("recommendation") or {}
    deadline = report.get("deadline") or {}
    lines = [
        f"# FPL Gameweek {report.get('target_gameweek') or '-'} Deadline Report",
        "",
        f"Status: {report.get('status')}",
        f"Generated: {report.get('generated_at')}",
        f"UK deadline: {deadline.get('deadline_time_uk') or 'Not available'}",
        f"Hours remaining: {deadline.get('hours_remaining') if deadline.get('hours_remaining') is not None else 'Not available'}",
        f"Advice level: {(report.get('operational_readiness') or {}).get('advice_level') or 'unavailable'}",
        f"Firm advice allowed: {(report.get('operational_readiness') or {}).get('firm_advice_allowed', False)}",
        "",
        "## Recommended action",
        "",
    ]
    if report.get("status") == "waiting_for_recommendations":
        lines.append("No squad action is recommended because future fixtures and projections are not yet ready.")
    else:
        transfers = recommendation.get("transfers", [])
        if recommendation.get("transfer_action") == "select_initial_squad":
            lines.append("Action: Review and select the proposed initial squad")
        else:
            lines.append("Transfers: " + (", ".join(f"{row.get('sell')} to {row.get('buy')}" for row in transfers) if transfers else "Roll or hold the transfer"))
        lines.append(
            f"Recommendation source: {recommendation.get('selection_source') or 'registered_team'}"
        )
        lines.append(f"Hit cost: {recommendation.get('hit_cost', 0)} points")
        chip = report.get("chip_recommendation") or {}
        lines.append(f"Chip: {chip.get('chip_name') if chip.get('action') == 'play' else 'Hold'}")
        lines.extend(["", "## Starting XI", ""])
        lines.extend(f"- {row.get('web_name')} ({row.get('team_name')}, {row.get('expected_points')} xPts)" for row in recommendation.get("starting_xi", []))
        captain = recommendation.get("captain") or {}
        vice = recommendation.get("vice_captain") or {}
        lines.extend(["", f"Captain: {captain.get('web_name') or 'Not available'}", f"Vice-captain: {vice.get('web_name') or 'Not available'}", "", "## Bench order", ""])
        lines.extend(f"{index}. {row.get('web_name')} ({row.get('expected_points')} xPts)" for index, row in enumerate(recommendation.get("bench_order", []), start=1))
    lines.extend(["", "## Changes since previous report", ""])
    lines.extend(f"- {row.get('summary')}" for row in report.get("material_changes", []))
    if not report.get("material_changes"):
        lines.append("- No material changes")
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- [{str(row.get('severity')).upper()}] {row.get('message')}" for row in report.get("warnings", []))
    if not report.get("warnings"):
        lines.append("- No warnings")
    late_news = (report.get("operational_readiness") or {}).get("late_team_news_review") or {}
    lines.extend([
        "",
        "## Manual late-news check",
        "",
        f"Status: {late_news.get('status') or 'not_due'}",
        late_news.get("reason") or "Check official team news before applying changes.",
    ])
    lines.extend(["", "## Deadline snapshot", "", f"Freeze status: {(report.get('deadline_freeze') or {}).get('status')}", f"Immutable snapshot: {(report.get('deadline_freeze') or {}).get('immutable_snapshot') or 'Not yet available'}", "", "This report is advisory only. No transfers, chips or team changes are made automatically.", ""])
    return "\n".join(lines)


def update_gameweek_operations(
    data_dir: Path,
    decision: dict[str, Any],
    horizons: list[dict[str, Any]],
    players: list[dict[str, Any]],
    my_team: dict[str, Any],
    current_gameweek: dict[str, Any],
    fixture_projections: list[dict[str, Any]],
    external_summary: dict[str, Any],
    prospective: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    chatgpt = data_dir / "chatgpt"
    latest_path = chatgpt / "gameweek_report.json"
    previous = read_json(latest_path, None)
    report = build_gameweek_report(
        decision, horizons, players, my_team, current_gameweek, fixture_projections,
        external_summary, prospective, _providers(data_dir / "context"), generated_at,
        previous=previous,
    )
    archive_json = None
    archive_markdown = None
    if report.get("material_change") and report.get("target_gameweek"):
        generated = parse_time(generated_at) or datetime.now(timezone.utc)
        folder = data_dir / "operations" / f"gw{integer(report['target_gameweek']):02d}"
        stamp = generated.strftime("%Y%m%dT%H%M%SZ")
        json_path = folder / f"{stamp}.json"
        markdown_path = folder / f"{stamp}.md"
        write_json(json_path, report)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_markdown(report), encoding="utf-8")
        archive_json = str(json_path.relative_to(data_dir)).replace("\\", "/")
        archive_markdown = str(markdown_path.relative_to(data_dir)).replace("\\", "/")
    report["archive_created_this_run"] = archive_json
    report["archive_markdown_created_this_run"] = archive_markdown
    write_json(latest_path, report)
    (chatgpt / "gameweek_report.md").write_text(render_markdown(report), encoding="utf-8")
    return report
