from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from src.fpl_launch_validation import validate_launch_plan
from src.fpl_multiweek import (
    POSITION_LIMITS,
    legal_squad,
    optimise_gameweek_lineup,
    optimise_multi_gameweek_route,
    projection_matrix,
)


INITIAL_SQUAD_VERSION = "fpl-initial-squad-1.1"
TARGET_SEASON = "2026/27"
BUDGET = 100.0
STRATEGIES = {
    "balanced": {
        "label": "Balanced",
        "description": "Maximise expected points while retaining useful bench depth.",
    },
    "aggressive": {
        "label": "Aggressive",
        "description": "Give extra weight to upside and lower ownership.",
    },
    "ownership_protected": {
        "label": "Ownership-protected",
        "description": "Give extra weight to highly owned players to limit early rank volatility.",
    },
}


def number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def integer(value: Any) -> int:
    return int(number(value))


def _waiting(status: str, checks: dict[str, Any], missing: list[str]) -> dict[str, Any]:
    return {
        "initial_squad_version": INITIAL_SQUAD_VERSION,
        "status": status,
        "target_season": TARGET_SEASON,
        "budget": BUDGET,
        "readiness": {
            "ready": False,
            "checks": checks,
            "missing": missing,
        },
        "recommended_strategy": None,
        "recommended_squad": [],
        "strategy_comparison": [],
        "planned_transfer_route": None,
        "principle": "No player names are emitted until official launch data passes every readiness check.",
    }


def launch_readiness(
    players: list[dict[str, Any]],
    fixture_projections: list[dict[str, Any]],
    current_gameweek: dict[str, Any],
    season: str | None,
    scoring_rules_version: str | None,
    min_player_pool: int = 300,
) -> tuple[dict[str, Any], list[str]]:
    next_event = current_gameweek.get("next") or {}
    next_gameweek = integer(next_event.get("id")) or None
    deadline = next_event.get("deadline_time")
    player_ids = [integer(row.get("player_id")) for row in players]
    team_ids = {integer(row.get("team_id")) for row in players if integer(row.get("team_id"))}
    positions = Counter(str(row.get("position")) for row in players)
    valid_players = [
        row
        for row in players
        if integer(row.get("player_id"))
        and integer(row.get("team_id"))
        and str(row.get("position")) in POSITION_LIMITS
        and number(row.get("price")) > 0
        and str(row.get("web_name") or "").strip()
    ]
    future_gameweeks = sorted(
        {
            integer(row.get("gameweek"))
            for row in fixture_projections
            if integer(row.get("gameweek")) >= 1
        }
    )
    checks = {
        "official_season": {"passed": season == TARGET_SEASON, "observed": season},
        "gameweek_1_is_next": {"passed": next_gameweek == 1, "observed": next_gameweek},
        "gameweek_1_deadline": {"passed": bool(deadline), "observed": deadline},
        "twenty_clubs": {"passed": len(team_ids) == 20, "observed": len(team_ids)},
        "complete_player_pool": {
            "passed": len(players) >= min_player_pool and len(valid_players) == len(players),
            "observed": len(players),
            "minimum": min_player_pool,
        },
        "unique_player_ids": {
            "passed": len(player_ids) == len(set(player_ids)) and all(player_ids),
            "observed": len(set(player_ids)),
        },
        "position_coverage": {
            "passed": all(positions.get(position, 0) >= limit for position, limit in POSITION_LIMITS.items()),
            "observed": {position: positions.get(position, 0) for position in POSITION_LIMITS},
        },
        "future_fixture_horizon": {
            "passed": len(future_gameweeks) >= 3 and future_gameweeks[0:1] == [1],
            "observed": future_gameweeks[:6],
            "minimum_gameweeks": 3,
        },
        "season_scoring_rules": {
            "passed": bool(scoring_rules_version) and "2026-27" in str(scoring_rules_version),
            "observed": scoring_rules_version,
        },
    }
    missing = [name for name, check in checks.items() if not check["passed"]]
    return checks, missing


def _player_metrics(
    players: list[dict[str, Any]],
    horizons: list[dict[str, Any]],
    fixture_projections: list[dict[str, Any]],
    gameweeks: list[int],
    first_gameweek_multiplier: dict[int, float],
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[int, float]]]:
    matrix = projection_matrix(fixture_projections, gameweeks, first_gameweek_multiplier)
    horizon_by_id = {integer(row.get("player_id")): row for row in horizons}
    metrics: dict[int, dict[str, Any]] = {}
    for player in players:
        player_id = integer(player.get("player_id"))
        horizon = horizon_by_id.get(player_id, {})
        discounted_points = sum(
            (0.96**offset) * matrix.get(gameweek, {}).get(player_id, 0)
            for offset, gameweek in enumerate(gameweeks)
        )
        ownership = number(player.get("selected_by_percent"))
        upside = (
            number(horizon.get("probability_10_plus_next_3"))
            + 1.5 * number(horizon.get("probability_15_plus_next_3"))
        )
        metrics[player_id] = {
            **player,
            **{key: value for key, value in horizon.items() if key not in player},
            "player_id": player_id,
            "discounted_points": discounted_points,
            "ownership": ownership,
            "upside": upside,
        }
    return metrics, matrix


def _strategy_player_score(row: dict[str, Any], strategy: str) -> float:
    points = number(row.get("discounted_points"))
    price = max(0.1, number(row.get("price")))
    ownership = number(row.get("ownership"))
    upside = number(row.get("upside"))
    if strategy == "aggressive":
        return points + 3.0 * upside - 0.012 * ownership + 0.04 * points / price
    if strategy == "ownership_protected":
        return points + 0.025 * ownership + 0.025 * points / price
    return points + 0.08 * points / price


def _candidate_pool(
    metrics: dict[int, dict[str, Any]], strategy: str, per_position: int = 24
) -> dict[str, list[int]]:
    by_position: dict[str, list[int]] = defaultdict(list)
    for player_id, row in metrics.items():
        status = str(row.get("status") or "a").lower()
        chance = row.get("chance_of_playing_next_round")
        if status == "u" or (chance not in {None, ""} and number(chance) <= 25):
            continue
        if number(row.get("discounted_points")) <= 0 or number(row.get("price")) <= 0:
            continue
        position = str(row.get("position"))
        if position in POSITION_LIMITS:
            by_position[position].append(player_id)
    result: dict[str, list[int]] = {}
    for position, ids in by_position.items():
        by_score = sorted(ids, key=lambda item: _strategy_player_score(metrics[item], strategy), reverse=True)
        by_value = sorted(
            ids,
            key=lambda item: number(metrics[item].get("discounted_points"))
            / max(0.1, number(metrics[item].get("price"))),
            reverse=True,
        )
        by_ownership = sorted(ids, key=lambda item: number(metrics[item].get("ownership")), reverse=True)
        result[position] = list(dict.fromkeys(by_score[:per_position] + by_value[:12] + by_ownership[:8]))
    return result


def _optimise_squad(
    metrics: dict[int, dict[str, Any]],
    matrix: dict[int, dict[int, float]],
    gameweeks: list[int],
    strategy: str,
    beam_width: int = 700,
) -> dict[str, Any] | None:
    pools = _candidate_pool(metrics, strategy)
    if any(len(pools.get(position, [])) < limit for position, limit in POSITION_LIMITS.items()):
        return None
    slots = [position for position, limit in POSITION_LIMITS.items() for _ in range(limit)]
    states: list[tuple[tuple[int, ...], float, float]] = [((), 0.0, 0.0)]
    for slot_index, position in enumerate(slots):
        next_states: dict[tuple[int, ...], tuple[tuple[int, ...], float, float]] = {}
        remaining_positions = Counter(slots[slot_index + 1 :])
        minimum_remaining = sum(
            sum(sorted(number(metrics[player_id].get("price")) for player_id in pools[pos])[:count])
            for pos, count in remaining_positions.items()
        )
        for ids, cost, heuristic in states:
            clubs = Counter(integer(metrics[player_id].get("team_id")) for player_id in ids)
            for player_id in pools[position]:
                if player_id in ids or clubs[integer(metrics[player_id].get("team_id"))] >= 3:
                    continue
                new_cost = cost + number(metrics[player_id].get("price"))
                if new_cost + minimum_remaining > BUDGET + 1e-9:
                    continue
                new_ids = tuple(sorted((*ids, player_id)))
                candidate = (
                    new_ids,
                    new_cost,
                    heuristic + _strategy_player_score(metrics[player_id], strategy),
                )
                current = next_states.get(new_ids)
                if current is None or candidate[2] > current[2]:
                    next_states[new_ids] = candidate
        states = sorted(next_states.values(), key=lambda item: item[2], reverse=True)[:beam_width]
        if not states:
            return None

    legal = [state for state in states if legal_squad(state[0], metrics) and state[1] <= BUDGET + 1e-9]
    if not legal:
        return None

    def final_score(state: tuple[tuple[int, ...], float, float]) -> float:
        squad_ids, _, _ = state
        total = 0.0
        for offset, gameweek in enumerate(gameweeks):
            points = dict(matrix.get(gameweek, {}))
            if strategy == "aggressive":
                points = {
                    player_id: value * (1 + 0.08 * number(metrics[player_id].get("upside")))
                    * (1 - 0.03 * number(metrics[player_id].get("ownership")) / 100)
                    for player_id, value in points.items()
                }
            elif strategy == "ownership_protected":
                points = {
                    player_id: value * (1 + 0.06 * number(metrics[player_id].get("ownership")) / 100)
                    for player_id, value in points.items()
                }
            lineup_points, starters, _ = optimise_gameweek_lineup(squad_ids, metrics, points)
            bench = set(squad_ids).difference(starters)
            bench_depth = sum(points.get(player_id, 0) for player_id in bench)
            total += (0.96**offset) * (lineup_points + 0.12 * bench_depth)
        return total

    best = max(legal, key=final_score)
    squad_ids, cost, _ = best
    base_points = matrix.get(gameweeks[0], {})
    first_points, starters, captain = optimise_gameweek_lineup(squad_ids, metrics, base_points)
    starter_order = sorted(starters, key=lambda player_id: base_points.get(player_id, 0), reverse=True)
    vice_captain = next((player_id for player_id in starter_order if player_id != captain), None)
    bench = sorted(
        set(squad_ids).difference(starters),
        key=lambda player_id: (
            str(metrics[player_id].get("position")) != "Goalkeeper",
            base_points.get(player_id, 0),
        ),
        reverse=True,
    )

    def public_player(player_id: int) -> dict[str, Any]:
        row = metrics[player_id]
        return {
            "player_id": player_id,
            "web_name": row.get("web_name"),
            "team_id": integer(row.get("team_id")),
            "team_name": row.get("team_name"),
            "position": row.get("position"),
            "price": round(number(row.get("price")), 1),
            "gameweek_1_expected_points": round(base_points.get(player_id, 0), 3),
            "discounted_horizon_points": round(number(row.get("discounted_points")), 3),
            "ownership_percent": round(number(row.get("ownership")), 2),
        }

    return {
        "strategy": strategy,
        **STRATEGIES[strategy],
        "total_cost": round(cost, 1),
        "bank": round(BUDGET - cost, 1),
        "objective_score": round(final_score(best), 3),
        "gameweek_1_expected_points_including_captain": round(first_points, 3),
        "squad": [public_player(player_id) for player_id in squad_ids],
        "starting_xi": [public_player(player_id) for player_id in starter_order],
        "bench_order": [public_player(player_id) for player_id in bench],
        "captain": public_player(captain) if captain else None,
        "vice_captain": public_player(vice_captain) if vice_captain else None,
        "validation": {
            "legal_squad": legal_squad(squad_ids, metrics),
            "position_counts": dict(Counter(str(metrics[player_id].get("position")) for player_id in squad_ids)),
            "maximum_from_one_club": max(Counter(integer(metrics[player_id].get("team_id")) for player_id in squad_ids).values()),
            "within_budget": cost <= BUDGET + 1e-9,
        },
    }


def build_initial_squad_plan(
    players: list[dict[str, Any]],
    horizons: list[dict[str, Any]],
    fixture_projections: list[dict[str, Any]],
    current_gameweek: dict[str, Any],
    season: str | None,
    scoring_rules_version: str | None,
    first_gameweek_multiplier: dict[int, float] | None = None,
    min_player_pool: int = 300,
    past_seasons: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    checks, missing = launch_readiness(
        players,
        fixture_projections,
        current_gameweek,
        season,
        scoring_rules_version,
        min_player_pool,
    )
    next_gameweek = integer((current_gameweek.get("next") or {}).get("id")) or None
    if season == TARGET_SEASON and next_gameweek not in {None, 1}:
        return _waiting("not_applicable_after_gameweek_1", checks, missing)
    if missing:
        return _waiting("waiting_for_launch_data", checks, missing)

    gameweeks = sorted({integer(row.get("gameweek")) for row in fixture_projections if integer(row.get("gameweek")) >= 1})[:6]
    metrics, matrix = _player_metrics(
        players,
        horizons,
        fixture_projections,
        gameweeks,
        first_gameweek_multiplier or {},
    )
    variants = [
        _optimise_squad(metrics, matrix, gameweeks, strategy)
        for strategy in STRATEGIES
    ]
    if any(variant is None for variant in variants):
        return _waiting(
            "optimisation_unavailable",
            checks,
            ["budget_legal_candidate_squads"],
        )
    comparison = [variant for variant in variants if variant is not None]
    recommended = next(variant for variant in comparison if variant["strategy"] == "balanced")
    route = optimise_multi_gameweek_route(
        fixture_projections,
        list(metrics.values()),
        [
            {"player_id": row["player_id"], "selling_price": round(number(row.get("price")) * 10)}
            for row in recommended["squad"]
        ],
        recommended["bank"],
        free_transfers=1,
        target_gameweek=1,
        horizon=6,
        first_gameweek_multiplier=first_gameweek_multiplier,
    )
    launch_validation = validate_launch_plan(
        players,
        horizons,
        fixture_projections,
        comparison,
        recommended,
        route,
        past_seasons,
    )
    status = (
        "ready"
        if launch_validation["usable_for_selection"]
        else "review_required"
    )
    return {
        "initial_squad_version": INITIAL_SQUAD_VERSION,
        "status": status,
        "target_season": TARGET_SEASON,
        "budget": BUDGET,
        "horizon_gameweeks": gameweeks,
        "readiness": {
            "ready": status == "ready",
            "launch_data_ready": True,
            "checks": checks,
            "missing": [],
        },
        "launch_validation": launch_validation,
        "recommended_strategy": "balanced",
        "total_cost": recommended["total_cost"],
        "bank": recommended["bank"],
        "recommended_squad": recommended["squad"],
        "recommended_starting_xi": recommended["starting_xi"],
        "recommended_bench_order": recommended["bench_order"],
        "captain": recommended["captain"],
        "vice_captain": recommended["vice_captain"],
        "strategy_comparison": comparison,
        "planned_transfer_route": route,
        "selection_policy": "Balanced is the default recommendation; aggressive and ownership-protected structures are retained as explicit alternatives.",
        "assumptions": [
            "The £100.0m initial budget and standard 2-5-5-3 squad structure apply.",
            "No more than three players may be selected from one club.",
            "Prices are held constant across the six-Gameweek planning horizon.",
            "The output is regenerated as official prices, fixtures, availability and context change before the Gameweek 1 deadline.",
        ],
    }
