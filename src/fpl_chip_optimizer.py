from __future__ import annotations

from typing import Any

from src.fpl_multiweek import (
    POSITION_LIMITS,
    integer,
    legal_squad,
    number,
    optimise_gameweek_lineup,
    projection_matrix,
)


CHIP_LABELS = {
    "wildcard": "Wildcard",
    "freehit": "Free Hit",
    "bboost": "Bench Boost",
    "3xc": "Triple Captain",
}
MINIMUM_EDGE = {"wildcard": 12.0, "freehit": 10.0, "bboost": 8.0, "3xc": 7.5}


def fixture_counts(
    fixture_projections: list[dict[str, Any]],
    players: list[dict[str, Any]],
    gameweeks: list[int],
) -> dict[int, dict[int, int]]:
    player_team = {
        integer(player.get("player_id")): integer(player.get("team_id"))
        for player in players
    }
    seen: dict[tuple[int, int], set[str]] = {}
    fallback: dict[tuple[int, int, int], int] = {}
    for row in fixture_projections:
        gameweek = integer(row.get("gameweek"))
        if gameweek not in gameweeks:
            continue
        player_id = integer(row.get("player_id"))
        team_id = integer(row.get("team_id")) or player_team.get(player_id, 0)
        if not team_id:
            continue
        fixture_id = row.get("fixture_id") or row.get("fixture")
        if fixture_id not in {None, ""}:
            seen.setdefault((gameweek, team_id), set()).add(str(fixture_id))
        else:
            key = (gameweek, team_id, player_id)
            fallback[key] = fallback.get(key, 0) + 1

    counts: dict[int, dict[int, int]] = {gameweek: {} for gameweek in gameweeks}
    team_ids = {team_id for team_id in player_team.values() if team_id}
    for gameweek in gameweeks:
        for team_id in team_ids:
            explicit = seen.get((gameweek, team_id))
            if explicit is not None:
                counts[gameweek][team_id] = len(explicit)
                continue
            per_player = [
                value
                for (gw, team, _), value in fallback.items()
                if gw == gameweek and team == team_id
            ]
            counts[gameweek][team_id] = max(per_player, default=0)
    return counts


def gameweek_structure(counts: dict[int, int]) -> dict[str, Any]:
    blank_teams = sorted(team_id for team_id, count in counts.items() if count == 0)
    double_teams = sorted(team_id for team_id, count in counts.items() if count > 1)
    if blank_teams and double_teams:
        kind = "blank_and_double"
    elif blank_teams:
        kind = "blank"
    elif double_teams:
        kind = "double"
    else:
        kind = "normal"
    return {
        "type": kind,
        "blank_team_ids": blank_teams,
        "double_team_ids": double_teams,
        "blank_team_count": len(blank_teams),
        "double_team_count": len(double_teams),
    }


def route_squads(
    starting_squad: tuple[int, ...], route: dict[str, Any]
) -> dict[int, tuple[int, ...]]:
    squad = set(starting_squad)
    rows: dict[int, tuple[int, ...]] = {}
    for move in route.get("gameweek_plan", []):
        for transfer in move.get("transfers", []):
            squad.discard(integer(transfer.get("sell_player_id")))
            squad.add(integer(transfer.get("buy_player_id")))
        rows[integer(move.get("gameweek"))] = tuple(sorted(squad))
    return rows


def optimise_budget_squad(
    player_by_id: dict[int, dict[str, Any]],
    points_by_player: dict[int, float],
    budget: float,
    beam_width: int = 1200,
) -> tuple[tuple[int, ...], float, float, list[int], int | None] | None:
    candidates: dict[str, list[int]] = {}
    limits = {"Goalkeeper": 14, "Defender": 26, "Midfielder": 26, "Forward": 20}
    for position, count in POSITION_LIMITS.items():
        rows = [
            player_id
            for player_id, player in player_by_id.items()
            if str(player.get("position")) == position
        ]
        rows.sort(
            key=lambda player_id: (
                points_by_player.get(player_id, 0),
                points_by_player.get(player_id, 0)
                / max(0.1, number(player_by_id[player_id].get("price"))),
            ),
            reverse=True,
        )
        cheapest = sorted(
            rows,
            key=lambda player_id: number(player_by_id[player_id].get("price")),
        )[:count]
        candidates[position] = list(dict.fromkeys(rows[: limits[position]] + cheapest))

    slots = [
        position
        for position, count in POSITION_LIMITS.items()
        for _ in range(count)
    ]
    states: list[tuple[tuple[int, ...], float, float, dict[int, int], dict[str, int]]] = [
        ((), 0.0, 0.0, {}, {})
    ]
    for position in slots:
        expanded = []
        for selected, cost, raw_score, clubs, last_by_position in states:
            last_id = last_by_position.get(position, 0)
            for player_id in candidates[position]:
                if player_id <= last_id or player_id in selected:
                    continue
                team_id = integer(player_by_id[player_id].get("team_id"))
                if clubs.get(team_id, 0) >= 3:
                    continue
                new_cost = cost + number(player_by_id[player_id].get("price"))
                if new_cost > budget + 1e-9:
                    continue
                new_clubs = dict(clubs)
                new_clubs[team_id] = new_clubs.get(team_id, 0) + 1
                new_last = dict(last_by_position)
                new_last[position] = player_id
                expanded.append(
                    (
                        selected + (player_id,),
                        new_cost,
                        raw_score + points_by_player.get(player_id, 0),
                        new_clubs,
                        new_last,
                    )
                )
        expanded.sort(
            key=lambda state: (
                state[2]
                + max((points_by_player.get(pid, 0) for pid in state[0]), default=0),
                -state[1],
            ),
            reverse=True,
        )
        states = expanded[:beam_width]
        if not states:
            return None

    best = None
    for selected, cost, _, _, _ in states:
        squad_ids = tuple(sorted(selected))
        if not legal_squad(squad_ids, player_by_id):
            continue
        score, starters, captain = optimise_gameweek_lineup(
            squad_ids, player_by_id, points_by_player
        )
        result = (squad_ids, cost, score, starters, captain)
        if best is None or score > best[2]:
            best = result
    return best


def active_chip_period(chip_state: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (period for period in chip_state.get("periods", []) if period.get("status") == "current"),
        None,
    )


def chip_available(chip_state: dict[str, Any], chip: str) -> bool:
    period = active_chip_period(chip_state)
    if period:
        return integer((period.get("chips", {}).get(chip) or {}).get("remaining")) > 0
    return integer((chip_state.get("chips", {}).get(chip) or {}).get("remaining")) > 0


def candidate_status(
    chip: str,
    edge: float,
    structure: dict[str, Any],
    horizon_reaches_expiry: bool,
) -> tuple[str, str]:
    relevant_event = {
        "freehit": structure["type"] in {"blank", "double", "blank_and_double"},
        "bboost": bool(structure["double_team_count"]),
        "3xc": bool(structure["double_team_count"]),
        "wildcard": True,
    }[chip]
    threshold = 0.0 if horizon_reaches_expiry else MINIMUM_EDGE[chip]
    if edge <= 0:
        return "reject", "No expected-points gain over the no-chip route."
    if not relevant_event and chip != "wildcard":
        return "hold", "No confirmed Blank or Double Gameweek structure supports using this chip."
    if edge + 1e-9 < threshold:
        return "hold", f"The {edge:.1f}-point edge is below the {threshold:.1f}-point save threshold."
    return "play", "The projected gain clears the save threshold within the known horizon."


def optimise_chip_plan(
    fixture_projections: list[dict[str, Any]],
    players: list[dict[str, Any]],
    squad: list[dict[str, Any]],
    bank: float,
    chip_state: dict[str, Any],
    multi_gameweek_plan: dict[str, Any],
    target_gameweek: int | None,
    discount: float = 0.96,
) -> dict[str, Any]:
    gameweeks = [integer(gw) for gw in multi_gameweek_plan.get("horizon_gameweeks", [])]
    routes = multi_gameweek_plan.get("routes", [])
    if multi_gameweek_plan.get("status") != "ready" or not gameweeks or not routes:
        return {
            "status": "waiting_for_routes",
            "horizon_gameweeks": gameweeks,
            "recommendation": None,
            "schedule": [],
            "candidates": [],
        }
    if chip_state.get("status") != "ready":
        return {
            "status": "chip_state_unavailable",
            "horizon_gameweeks": gameweeks,
            "recommendation": None,
            "schedule": [],
            "candidates": [],
        }

    player_by_id = {integer(player.get("player_id")): player for player in players}
    starting_ids = tuple(sorted(integer(row.get("player_id")) for row in squad))
    matrix = projection_matrix(fixture_projections, gameweeks)
    counts = fixture_counts(fixture_projections, players, gameweeks)
    structures = {gw: gameweek_structure(counts.get(gw, {})) for gw in gameweeks}
    period = active_chip_period(chip_state)
    period_end = integer((period or {}).get("end_gameweek")) or 38
    horizon_reaches_expiry = max(gameweeks) >= period_end
    total_budget = sum(
        number(row.get("selling_price")) / 10
        if number(row.get("selling_price")) >= 10
        else number(row.get("selling_price"))
        or number(player_by_id.get(integer(row.get("player_id")), {}).get("price"))
        for row in squad
    ) + bank

    candidates: list[dict[str, Any]] = []
    for route_index, route in enumerate(routes):
        squads = route_squads(starting_ids, route)
        moves_by_gw = {
            integer(move.get("gameweek")): move for move in route.get("gameweek_plan", [])
        }
        baseline_by_gw = {
            gw: number((moves_by_gw.get(gw) or {}).get("net_expected_points"))
            for gw in gameweeks
        }
        for offset, gameweek in enumerate(gameweeks):
            route_squad = squads.get(gameweek, starting_ids)
            points = matrix.get(gameweek, {})
            normal_score, starters, captain = optimise_gameweek_lineup(
                route_squad, player_by_id, points
            )
            starter_score = sum(points.get(player_id, 0) for player_id in starters)
            bench_score = sum(points.get(player_id, 0) for player_id in route_squad) - starter_score
            structure = structures[gameweek]
            for chip, edge, detail in (
                (
                    "3xc",
                    points.get(captain, 0) if captain is not None else 0,
                    {"captain_player_id": captain},
                ),
                (
                    "bboost",
                    bench_score,
                    {"bench_player_ids": sorted(set(route_squad) - set(starters))},
                ),
            ):
                if not chip_available(chip_state, chip):
                    continue
                status, reason = candidate_status(
                    chip, edge, structure, horizon_reaches_expiry
                )
                candidates.append({
                    "chip": chip,
                    "chip_name": CHIP_LABELS[chip],
                    "gameweek": gameweek,
                    "route_index": route_index,
                    "event_structure": structure,
                    "incremental_expected_points": round(edge, 3),
                    "discounted_incremental_points": round((discount ** offset) * edge, 3),
                    "status": status,
                    "reason": reason,
                    **detail,
                })

            if chip_available(chip_state, "freehit"):
                free_hit = optimise_budget_squad(player_by_id, points, total_budget)
                if free_hit:
                    fh_ids, fh_cost, fh_score, fh_starters, fh_captain = free_hit
                    edge = fh_score - baseline_by_gw.get(gameweek, normal_score)
                    status, reason = candidate_status(
                        "freehit", edge, structure, horizon_reaches_expiry
                    )
                    candidates.append({
                        "chip": "freehit",
                        "chip_name": CHIP_LABELS["freehit"],
                        "gameweek": gameweek,
                        "route_index": route_index,
                        "event_structure": structure,
                        "incremental_expected_points": round(edge, 3),
                        "discounted_incremental_points": round((discount ** offset) * edge, 3),
                        "status": status,
                        "reason": reason,
                        "temporary_squad_player_ids": list(fh_ids),
                        "starter_player_ids": fh_starters,
                        "captain_player_id": fh_captain,
                        "squad_cost": round(fh_cost, 1),
                        "squad_reverts_after_gameweek": True,
                    })

            if chip_available(chip_state, "wildcard"):
                remaining_points = {
                    player_id: sum(
                        (discount ** (future_offset - offset))
                        * matrix.get(future_gw, {}).get(player_id, 0)
                        for future_offset, future_gw in enumerate(gameweeks[offset:], start=offset)
                    )
                    for player_id in player_by_id
                }
                wildcard = optimise_budget_squad(
                    player_by_id, remaining_points, total_budget
                )
                if wildcard:
                    wc_ids, wc_cost, _, _, _ = wildcard
                    wildcard_points = 0.0
                    for future_offset, future_gw in enumerate(gameweeks[offset:], start=offset):
                        score, _, _ = optimise_gameweek_lineup(
                            wc_ids, player_by_id, matrix.get(future_gw, {})
                        )
                        wildcard_points += (discount ** (future_offset - offset)) * score
                    baseline_points = sum(
                        (discount ** (future_offset - offset))
                        * baseline_by_gw.get(future_gw, 0)
                        for future_offset, future_gw in enumerate(gameweeks[offset:], start=offset)
                    )
                    edge = wildcard_points - baseline_points
                    transfers = len(set(wc_ids) - set(route_squad))
                    status, reason = candidate_status(
                        "wildcard", edge, structure, horizon_reaches_expiry
                    )
                    if transfers < 4 and status == "play":
                        status = "hold"
                        reason = "The optimal rebuild changes fewer than four players, so a Wildcard is unnecessary."
                    candidates.append({
                        "chip": "wildcard",
                        "chip_name": CHIP_LABELS["wildcard"],
                        "gameweek": gameweek,
                        "route_index": route_index,
                        "event_structure": structure,
                        "incremental_expected_points": round(edge, 3),
                        "discounted_incremental_points": round((discount ** offset) * edge, 3),
                        "status": status,
                        "reason": reason,
                        "replacement_squad_player_ids": list(wc_ids),
                        "transfers_in_rebuild": transfers,
                        "squad_cost": round(wc_cost, 1),
                        "permanent_squad_change": True,
                    })

    best_by_chip: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        chip = str(candidate["chip"])
        current = best_by_chip.get(chip)
        if current is None or number(candidate["discounted_incremental_points"]) > number(current["discounted_incremental_points"]):
            best_by_chip[chip] = candidate
    for chip, best in best_by_chip.items():
        alternatives = sorted(
            (
                candidate
                for candidate in candidates
                if candidate["chip"] == chip
                and candidate["gameweek"] != best["gameweek"]
            ),
            key=lambda row: number(row["discounted_incremental_points"]),
            reverse=True,
        )
        next_best = number(alternatives[0]["discounted_incremental_points"]) if alternatives else 0
        best["timing_edge_over_next_best"] = round(
            number(best["discounted_incremental_points"]) - next_best, 3
        )

    playable_by_chip_week: dict[str, dict[int, dict[str, Any]]] = {}
    for candidate in candidates:
        if candidate["status"] != "play":
            continue
        chip = str(candidate["chip"])
        gameweek = integer(candidate["gameweek"])
        current = playable_by_chip_week.setdefault(chip, {}).get(gameweek)
        if current is None or number(candidate["discounted_incremental_points"]) > number(current["discounted_incremental_points"]):
            playable_by_chip_week[chip][gameweek] = candidate

    schedule_states: dict[tuple[int, ...], tuple[float, list[dict[str, Any]]]] = {
        (): (0.0, [])
    }
    for chip in CHIP_LABELS:
        options = list(playable_by_chip_week.get(chip, {}).values())
        next_states = dict(schedule_states)
        for used, (score, selected) in schedule_states.items():
            used_set = set(used)
            for candidate in options:
                gameweek = integer(candidate["gameweek"])
                if gameweek in used_set:
                    continue
                key = tuple(sorted((*used, gameweek)))
                candidate_score = score + number(candidate["discounted_incremental_points"])
                if key not in next_states or candidate_score > next_states[key][0]:
                    next_states[key] = (candidate_score, selected + [candidate])
        schedule_states = next_states
    _, schedule = max(schedule_states.values(), key=lambda row: row[0])
    schedule.sort(key=lambda row: integer(row["gameweek"]))
    current_use = next(
        (candidate for candidate in schedule if integer(candidate["gameweek"]) == integer(target_gameweek)),
        None,
    )
    recommendation = (
        {"action": "play", **current_use}
        if current_use
        else {
            "action": "hold",
            "gameweek": target_gameweek,
            "reason": "No available chip has a sufficient edge in the target Gameweek.",
            "next_planned_use": schedule[0] if schedule else None,
        }
    )
    return {
        "status": "ready",
        "horizon_gameweeks": gameweeks,
        "period_end_gameweek": period_end,
        "horizon_reaches_chip_expiry": horizon_reaches_expiry,
        "gameweek_structures": [
            {"gameweek": gameweek, **structures[gameweek]} for gameweek in gameweeks
        ],
        "recommendation": recommendation,
        "schedule": schedule,
        "best_by_chip": best_by_chip,
        "candidates": sorted(
            candidates,
            key=lambda row: number(row["discounted_incremental_points"]),
            reverse=True,
        ),
        "method": (
            "Compare each available chip with the same no-chip transfer route, enforce one chip "
            "per Gameweek, and retain save thresholds while stronger unseen opportunities remain."
        ),
        "assumptions": [
            "Free Hit uses a temporary budget-legal 15-player squad and reverts after the Gameweek.",
            "Wildcard uses a permanent budget-legal rebuild over the remaining known horizon.",
            "Bench Boost adds the expected points of the four players outside the optimal XI.",
            "Triple Captain adds one further copy of the selected captain's expected points.",
            "Player prices are held constant across the known planning horizon.",
        ],
    }
