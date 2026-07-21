from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.external_context import number, resolved_context
from src.fpl_decisions import decision_projection, optimise_lineup
from src.update_fpl_data import write_csv, write_json


PROSPECTIVE_VERSION = "fpl-prospective-1.0"
MINIMUM_GAMEWEEKS_FOR_EVIDENCE = 10


def integer(value: Any) -> int:
    return int(number(value))


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _is_odds_source(source_id: Any, source_registry: dict[str, Any]) -> bool:
    source_id = str(source_id or "")
    if "odds" in source_id.lower() or "bookmaker" in source_id.lower():
        return True
    source = next(
        (
            item
            for item in source_registry.get("sources", [])
            if str(item.get("source_id")) == source_id
        ),
        {},
    )
    label = f"{source.get('name', '')} {source.get('source_id', '')}".lower()
    return "odds" in label or "bookmaker" in label


def _arm(
    arm_id: str,
    squad_rows: list[dict[str, Any]],
    points: dict[int, float],
    basis: str,
) -> dict[str, Any]:
    rows = [
        {**row, "decision_expected_points": points.get(integer(row.get("player_id")), 0)}
        for row in squad_rows
    ]
    starters, bench = optimise_lineup(rows)
    starters.sort(
        key=lambda row: points.get(integer(row.get("player_id")), 0), reverse=True
    )
    captain = starters[0] if starters else None
    predicted = sum(points.get(integer(row.get("player_id")), 0) for row in starters)
    if captain:
        predicted += points.get(integer(captain.get("player_id")), 0)
    return {
        "arm_id": arm_id,
        "basis": basis,
        "squad_player_ids": sorted(integer(row.get("player_id")) for row in squad_rows),
        "starter_player_ids": [integer(row.get("player_id")) for row in starters],
        "bench_player_ids": [integer(row.get("player_id")) for row in bench],
        "captain_player_id": integer(captain.get("player_id")) if captain else None,
        "captain_multiplier": 2,
        "predicted_points": round(predicted, 3),
        "chip": None,
        "hit_cost": 0,
        "transfers": [],
    }


def _system_strategy_arm(
    decision: dict[str, Any],
    starting_squad_ids: list[int],
    full_points: dict[int, float],
    player_by_id: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    gameweek = integer(decision.get("target_gameweek"))
    route = (decision.get("multi_gameweek_plan") or {}).get("recommended_route") or {}
    move = next(
        (
            item
            for item in route.get("gameweek_plan", [])
            if integer(item.get("gameweek")) == gameweek
        ),
        {},
    )
    transfers = move.get("transfers", []) or []
    squad = set(starting_squad_ids)
    for transfer in transfers:
        squad.discard(integer(transfer.get("sell_player_id")))
        squad.add(integer(transfer.get("buy_player_id")))
    starters = [integer(value) for value in move.get("starter_player_ids", [])]
    captain = integer(move.get("captain_player_id")) or None
    if not starters:
        starters = [
            integer(row.get("player_id"))
            for row in decision.get("recommended_lineup", [])
        ]
    if captain is None:
        captain = integer(
            ((decision.get("captaincy") or {}).get("captain") or {}).get("player_id")
        ) or None

    chip_recommendation = (decision.get("chip_optimisation") or {}).get("recommendation") or {}
    chip = (
        str(chip_recommendation.get("chip"))
        if chip_recommendation.get("action") == "play"
        and integer(chip_recommendation.get("gameweek")) == gameweek
        else None
    )
    if chip == "freehit":
        squad = set(integer(value) for value in chip_recommendation.get("temporary_squad_player_ids", []))
        starters = [integer(value) for value in chip_recommendation.get("starter_player_ids", [])]
        captain = integer(chip_recommendation.get("captain_player_id")) or captain
    elif chip == "wildcard":
        replacement = [
            integer(value)
            for value in chip_recommendation.get("replacement_squad_player_ids", [])
        ]
        if replacement:
            squad = set(replacement)
            wildcard_arm = _arm(
                "wildcard_selection",
                [player_by_id[player_id] for player_id in squad if player_id in player_by_id],
                full_points,
                "Wildcard replacement squad",
            )
            starters = wildcard_arm["starter_player_ids"]
            captain = wildcard_arm["captain_player_id"]
    captain_multiplier = 3 if chip == "3xc" else 2
    bench = sorted(squad.difference(starters))
    predicted = sum(full_points.get(player_id, 0) for player_id in starters)
    predicted += (captain_multiplier - 1) * full_points.get(captain or 0, 0)
    if chip == "bboost":
        predicted += sum(full_points.get(player_id, 0) for player_id in bench)
    return {
        "arm_id": "system_strategy",
        "basis": "Full decision system, including the first route move and current chip recommendation.",
        "squad_player_ids": sorted(squad),
        "starter_player_ids": starters,
        "bench_player_ids": bench,
        "captain_player_id": captain,
        "captain_multiplier": captain_multiplier,
        "predicted_points": round(predicted - integer(move.get("hit_cost")), 3),
        "chip": chip,
        "hit_cost": integer(move.get("hit_cost")),
        "transfers": [
            {
                "sell_player_id": integer(item.get("sell_player_id")),
                "buy_player_id": integer(item.get("buy_player_id")),
            }
            for item in transfers
        ],
    }


def build_snapshot(
    decision: dict[str, Any],
    horizons: list[dict[str, Any]],
    players: list[dict[str, Any]],
    my_team: dict[str, Any],
    current_gameweek: dict[str, Any],
    context_signals: list[dict[str, Any]],
    source_registry: dict[str, Any],
    generated_at: str,
) -> dict[str, Any] | None:
    if decision.get("status") != "ready" or not my_team.get("available"):
        return None
    next_event = current_gameweek.get("next") or {}
    gameweek = integer(next_event.get("id"))
    deadline_text = next_event.get("deadline_time")
    if not gameweek or not deadline_text:
        return None
    created_at = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    deadline = datetime.fromisoformat(str(deadline_text).replace("Z", "+00:00"))
    hours_to_deadline = (deadline - created_at).total_seconds() / 3600
    if not 0 <= hours_to_deadline <= 8:
        return None

    by_horizon = {integer(row.get("player_id")): row for row in horizons}
    by_player = {integer(row.get("player_id")): row for row in players}
    decision_rows = decision.get("recommended_lineup", []) + decision.get("bench_order", [])
    by_decision = {integer(row.get("player_id")): row for row in decision_rows}
    squad_rows = [
        {
            **by_player.get(integer(item.get("player_id")), {}),
            **by_horizon.get(integer(item.get("player_id")), {}),
            **by_decision.get(integer(item.get("player_id")), {}),
            "player_id": integer(item.get("player_id")),
            "position": item.get("position")
            or by_player.get(integer(item.get("player_id")), {}).get("position"),
        }
        for item in my_team.get("squad", [])
    ]
    if len(squad_rows) != 15:
        return None

    no_odds_signals = [
        signal
        for signal in context_signals
        if not _is_odds_source(signal.get("source_id"), source_registry)
    ]
    full_points: dict[int, float] = {}
    no_odds_points: dict[int, float] = {}
    no_external_points: dict[int, float] = {}
    quantitative_points: dict[int, float] = {}
    ownership_points: dict[int, float] = {}
    fixture = {"gameweek": gameweek}
    for player_id, horizon in by_horizon.items():
        player = by_player.get(player_id, horizon)
        full_context = resolved_context(
            context_signals, source_registry, player, fixture, created_at
        )
        no_odds_context = resolved_context(
            no_odds_signals, source_registry, player, fixture, created_at
        )
        full_points[player_id] = number(
            decision_projection(horizon, full_context).get("decision_expected_points")
        )
        no_odds_points[player_id] = number(
            decision_projection(horizon, no_odds_context).get("decision_expected_points")
        )
        no_external_points[player_id] = number(horizon.get("expected_points_next_1"))
        quantitative_points[player_id] = number(
            horizon.get("quantitative_expected_points_next_1")
        )
        ownership_points[player_id] = number(player.get("selected_by_percent"))

    arms = [
        _system_strategy_arm(
            decision,
            [integer(row.get("player_id")) for row in squad_rows],
            full_points,
            by_player,
        ),
        _arm(
            "full_context_selection",
            squad_rows,
            full_points,
            "Full model plus qualitative and all active external context, on the same starting squad.",
        ),
        _arm(
            "no_odds_selection",
            squad_rows,
            no_odds_points,
            "Identical selection with bookmaker and Odds API signals removed.",
        ),
        _arm(
            "no_external_selection",
            squad_rows,
            no_external_points,
            "Validated model plus qualitative observations, with external context removed.",
        ),
        _arm(
            "quantitative_only_selection",
            squad_rows,
            quantitative_points,
            "Untouched quantitative ensemble, with qualitative and external context removed.",
        ),
        _arm(
            "ownership_baseline",
            squad_rows,
            ownership_points,
            "Legal XI and captain chosen only by FPL ownership percentage.",
        ),
    ]
    return {
        "prospective_version": PROSPECTIVE_VERSION,
        "created_at": created_at.astimezone(timezone.utc).replace(microsecond=0).isoformat(),
        "target_gameweek": gameweek,
        "deadline_time": deadline.astimezone(timezone.utc).isoformat(),
        "hours_to_deadline": round(hours_to_deadline, 3),
        "decision_version": decision.get("decision_version"),
        "model_version": decision.get("model_version"),
        "team_id": decision.get("team_id"),
        "active_context_signal_ids": sorted(
            {
                str(signal_id)
                for row in decision_rows
                for signal_id in row.get("context_signal_ids", [])
            }
        ),
        "arms": arms,
        "principle": "Every arm is frozen before the deadline and scored only after official finality.",
    }


def write_snapshot(data_dir: Path, snapshot: dict[str, Any] | None) -> str | None:
    if not snapshot:
        return None
    created = datetime.fromisoformat(str(snapshot["created_at"]))
    gameweek = integer(snapshot.get("target_gameweek"))
    timestamp = created.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = data_dir / "prospective" / f"gw{gameweek:02d}" / f"{timestamp}.json"
    if path.exists():
        return None
    write_json(path, snapshot)
    return str(path.relative_to(data_dir)).replace("\\", "/")


def _score_arm(arm: dict[str, Any], actual: dict[int, float]) -> dict[str, Any]:
    starters = [integer(value) for value in arm.get("starter_player_ids", [])]
    bench = [integer(value) for value in arm.get("bench_player_ids", [])]
    captain = integer(arm.get("captain_player_id")) or None
    captain_multiplier = max(1, integer(arm.get("captain_multiplier")) or 2)
    lineup_points = sum(actual.get(player_id, 0) for player_id in starters)
    captain_points = actual.get(captain, 0) if captain else 0
    bench_points = (
        sum(actual.get(player_id, 0) for player_id in bench)
        if arm.get("chip") == "bboost"
        else 0
    )
    hit_cost = integer(arm.get("hit_cost"))
    gross = lineup_points + (captain_multiplier - 1) * captain_points + bench_points
    transfer_delta = sum(
        actual.get(integer(item.get("buy_player_id")), 0)
        - actual.get(integer(item.get("sell_player_id")), 0)
        for item in arm.get("transfers", [])
    )
    return {
        "actual_points": round(gross - hit_cost, 3),
        "lineup_points": round(lineup_points, 3),
        "captain_points": round(captain_points, 3),
        "bench_boost_points": round(bench_points, 3),
        "hit_cost": hit_cost,
        "transfer_gameweek_delta_before_hit": round(transfer_delta, 3),
        "transfer_gameweek_delta_after_hit": round(transfer_delta - hit_cost, 3),
    }


def evaluate(data_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    chatgpt = data_dir / "chatgpt"
    actual_by_gameweek: dict[int, dict[int, float]] = defaultdict(dict)
    for row in read_csv(chatgpt / "player_gameweeks.csv"):
        actual_by_gameweek[integer(row.get("gameweek"))][integer(row.get("player_id"))] = number(
            row.get("total_points")
        )
    finality = {
        integer(row.get("id")): truthy(row.get("finished")) and truthy(row.get("data_checked"))
        for row in read_json(chatgpt / "gameweeks.json", [])
        if integer(row.get("id"))
    }
    manager_points = {
        integer(row.get("event")): number(row.get("points"))
        for row in read_json(chatgpt / "manager_history.json", {}).get("current", [])
    }

    rows: list[dict[str, Any]] = []
    skipped_unfinalised = 0
    for gameweek_dir in sorted((data_dir / "prospective").glob("gw*")):
        snapshots = sorted(gameweek_dir.glob("*.json"))
        if not snapshots:
            continue
        snapshot = read_json(snapshots[-1], {})
        gameweek = integer(snapshot.get("target_gameweek"))
        created = datetime.fromisoformat(str(snapshot.get("created_at")).replace("Z", "+00:00"))
        deadline = datetime.fromisoformat(str(snapshot.get("deadline_time")).replace("Z", "+00:00"))
        if created >= deadline:
            continue
        if not finality.get(gameweek, False):
            skipped_unfinalised += 1
            continue
        actual = actual_by_gameweek.get(gameweek, {})
        if not actual:
            continue
        relative = str(snapshots[-1].relative_to(data_dir)).replace("\\", "/")
        for arm in snapshot.get("arms", []):
            scored = _score_arm(arm, actual)
            rows.append(
                {
                    "gameweek": gameweek,
                    "snapshot": relative,
                    "arm_id": arm.get("arm_id"),
                    "predicted_points": number(arm.get("predicted_points")),
                    **scored,
                    "official_manager_points": manager_points.get(gameweek),
                    "captain_player_id": arm.get("captain_player_id"),
                    "chip": arm.get("chip"),
                    "leakage_safe": True,
                }
            )

    by_arm: dict[str, list[float]] = defaultdict(list)
    by_gameweek_arm: dict[tuple[int, str], float] = {}
    for row in rows:
        arm_id = str(row.get("arm_id"))
        points = number(row.get("actual_points"))
        by_arm[arm_id].append(points)
        by_gameweek_arm[(integer(row.get("gameweek")), arm_id)] = points
    arm_summary = [
        {
            "arm_id": arm_id,
            "evaluated_gameweeks": len(values),
            "total_actual_points": round(sum(values), 3),
            "average_actual_points": round(sum(values) / len(values), 3),
        }
        for arm_id, values in sorted(by_arm.items())
        if values
    ]

    comparisons = []
    for comparison_id, treatment, control in (
        ("all_context_value", "full_context_selection", "no_external_selection"),
        ("odds_value", "full_context_selection", "no_odds_selection"),
        ("qualitative_value", "no_external_selection", "quantitative_only_selection"),
        ("model_vs_ownership", "full_context_selection", "ownership_baseline"),
        ("strategy_vs_ownership", "system_strategy", "ownership_baseline"),
    ):
        deltas = [
            by_gameweek_arm[(gameweek, treatment)] - by_gameweek_arm[(gameweek, control)]
            for gameweek in sorted({gw for gw, arm in by_gameweek_arm if arm == treatment})
            if (gameweek, control) in by_gameweek_arm
        ]
        average = sum(deltas) / len(deltas) if deltas else 0
        if len(deltas) < MINIMUM_GAMEWEEKS_FOR_EVIDENCE:
            status = "insufficient_evidence"
        elif average > 0.5 and sum(delta > 0 for delta in deltas) / len(deltas) >= 0.55:
            status = "positive_evidence"
        elif average < -0.5 and sum(delta < 0 for delta in deltas) / len(deltas) >= 0.60:
            status = "review_influence"
        else:
            status = "inconclusive"
        comparisons.append(
            {
                "comparison_id": comparison_id,
                "treatment": treatment,
                "control": control,
                "paired_gameweeks": len(deltas),
                "average_points_delta": round(average, 3),
                "treatment_win_rate": round(
                    sum(delta > 0 for delta in deltas) / len(deltas), 4
                )
                if deltas
                else None,
                "status": status,
            }
        )
    evaluated_gameweeks = len({integer(row.get("gameweek")) for row in rows})
    summary = {
        "prospective_version": PROSPECTIVE_VERSION,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "ready" if evaluated_gameweeks else "waiting_for_finalised_gameweeks",
        "evaluated_gameweeks": evaluated_gameweeks,
        "skipped_unfinalised_gameweeks": skipped_unfinalised,
        "minimum_gameweeks_for_evidence": MINIMUM_GAMEWEEKS_FOR_EVIDENCE,
        "arms": arm_summary,
        "comparisons": comparisons,
        "latest_gameweek": max((integer(row.get("gameweek")) for row in rows), default=None),
        "finality_requirement": "finished=true and data_checked=true",
        "governance": "Evidence is reported prospectively; source weights are not changed automatically.",
    }
    return rows, summary


def update_prospective_evaluation(
    data_dir: Path,
    decision: dict[str, Any],
    horizons: list[dict[str, Any]],
    players: list[dict[str, Any]],
    my_team: dict[str, Any],
    current_gameweek: dict[str, Any],
    context_signals: list[dict[str, Any]],
    source_registry: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    snapshot = build_snapshot(
        decision,
        horizons,
        players,
        my_team,
        current_gameweek,
        context_signals,
        source_registry,
        generated_at,
    )
    created = write_snapshot(data_dir, snapshot)
    snapshot_files = sorted(
        str(path.relative_to(data_dir)).replace("\\", "/")
        for path in (data_dir / "prospective").glob("gw*/*.json")
    )
    index = {
        "generated_at": generated_at,
        "prospective_version": PROSPECTIVE_VERSION,
        "snapshot_created_this_run": created,
        "snapshots": snapshot_files,
    }
    write_json(data_dir / "chatgpt" / "prospective_index.json", index)
    rows, summary = evaluate(data_dir)
    fields = [
        "gameweek",
        "snapshot",
        "arm_id",
        "predicted_points",
        "actual_points",
        "lineup_points",
        "captain_points",
        "bench_boost_points",
        "hit_cost",
        "transfer_gameweek_delta_before_hit",
        "transfer_gameweek_delta_after_hit",
        "official_manager_points",
        "captain_player_id",
        "chip",
        "leakage_safe",
    ]
    write_csv(data_dir / "chatgpt" / "prospective_evaluation.csv", rows, fields)
    write_json(data_dir / "chatgpt" / "prospective_evaluation.json", summary)
    return {"index": index, "evaluation": summary}
