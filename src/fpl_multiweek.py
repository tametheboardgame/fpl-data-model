from __future__ import annotations

from dataclasses import dataclass
from typing import Any


POSITION_LIMITS = {
    "Goalkeeper": 2,
    "Defender": 5,
    "Midfielder": 5,
    "Forward": 3,
}
MINIMUM_STARTERS = {
    "Goalkeeper": 1,
    "Defender": 3,
    "Midfielder": 2,
    "Forward": 1,
}
MAXIMUM_STARTERS = {
    "Goalkeeper": 1,
    "Defender": 5,
    "Midfielder": 5,
    "Forward": 3,
}


def number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def integer(value: Any) -> int:
    return int(number(value))


def optimise_gameweek_lineup(
    squad_ids: tuple[int, ...],
    player_by_id: dict[int, dict[str, Any]],
    points_by_player: dict[int, float],
) -> tuple[float, list[int], int | None]:
    by_position: dict[str, list[int]] = {position: [] for position in POSITION_LIMITS}
    for player_id in squad_ids:
        position = str(player_by_id.get(player_id, {}).get("position"))
        if position in by_position:
            by_position[position].append(player_id)
    for rows in by_position.values():
        rows.sort(key=lambda player_id: points_by_player.get(player_id, 0), reverse=True)

    starters: list[int] = []
    for position, minimum in MINIMUM_STARTERS.items():
        starters.extend(by_position[position][:minimum])
    selected = set(starters)
    remaining = sorted(
        (player_id for player_id in squad_ids if player_id not in selected),
        key=lambda player_id: points_by_player.get(player_id, 0),
        reverse=True,
    )
    for player_id in remaining:
        if len(starters) == 11:
            break
        position = str(player_by_id[player_id].get("position"))
        if sum(str(player_by_id[item].get("position")) == position for item in starters) >= MAXIMUM_STARTERS[position]:
            continue
        starters.append(player_id)
    captain = max(starters, key=lambda player_id: points_by_player.get(player_id, 0), default=None)
    lineup_points = sum(points_by_player.get(player_id, 0) for player_id in starters)
    captain_points = points_by_player.get(captain, 0) if captain is not None else 0
    return lineup_points + captain_points, starters, captain


def legal_squad(
    squad_ids: tuple[int, ...], player_by_id: dict[int, dict[str, Any]]
) -> bool:
    if len(squad_ids) != 15 or len(set(squad_ids)) != 15:
        return False
    positions: dict[str, int] = {}
    clubs: dict[int, int] = {}
    for player_id in squad_ids:
        player = player_by_id.get(player_id)
        if not player:
            return False
        position = str(player.get("position"))
        team_id = integer(player.get("team_id"))
        positions[position] = positions.get(position, 0) + 1
        clubs[team_id] = clubs.get(team_id, 0) + 1
    return positions == POSITION_LIMITS and max(clubs.values(), default=0) <= 3


def projection_matrix(
    fixture_projections: list[dict[str, Any]],
    gameweeks: list[int],
    first_gameweek_multiplier: dict[int, float] | None = None,
) -> dict[int, dict[int, float]]:
    selected = set(gameweeks)
    matrix: dict[int, dict[int, float]] = {}
    for row in fixture_projections:
        gameweek = integer(row.get("gameweek"))
        if gameweek not in selected:
            continue
        player_id = integer(row.get("player_id"))
        points = number(row.get("expected_points"))
        if gameweeks and gameweek == gameweeks[0]:
            points *= number((first_gameweek_multiplier or {}).get(player_id, 1.0))
        matrix.setdefault(gameweek, {})[player_id] = (
            matrix.setdefault(gameweek, {}).get(player_id, 0) + points
        )
    return matrix


@dataclass(frozen=True)
class RouteState:
    squad_ids: tuple[int, ...]
    sale_prices: tuple[tuple[int, float], ...]
    bank: float
    free_transfers: int
    score: float
    undiscounted_points: float
    moves: tuple[dict[str, Any], ...]

    def price_map(self) -> dict[int, float]:
        return dict(self.sale_prices)


def transfer_options(
    state: RouteState,
    player_by_id: dict[int, dict[str, Any]],
    candidate_ids: dict[str, list[int]],
    remaining_points: dict[int, float],
    max_transfers: int = 2,
) -> list[tuple[tuple[int, ...], dict[int, float], float, list[dict[str, Any]]]]:
    options: list[tuple[tuple[int, ...], dict[int, float], float, list[dict[str, Any]]]] = [
        (state.squad_ids, state.price_map(), state.bank, [])
    ]
    frontier = options
    for _ in range(max_transfers):
        expanded: list[tuple[tuple[int, ...], dict[int, float], float, list[dict[str, Any]]]] = []
        for squad_ids, sale_prices, bank, moves in frontier:
            squad = set(squad_ids)
            possible: list[tuple[float, tuple[int, ...], dict[int, float], float, list[dict[str, Any]]]] = []
            for outgoing_id in squad_ids:
                outgoing = player_by_id[outgoing_id]
                position = str(outgoing.get("position"))
                sale_price = number(sale_prices.get(outgoing_id, outgoing.get("price")))
                for incoming_id in candidate_ids.get(position, []):
                    if incoming_id in squad:
                        continue
                    incoming = player_by_id[incoming_id]
                    buy_price = number(incoming.get("price"))
                    new_bank = bank + sale_price - buy_price
                    if new_bank < -1e-9:
                        continue
                    new_squad = tuple(sorted((squad - {outgoing_id}) | {incoming_id}))
                    if not legal_squad(new_squad, player_by_id):
                        continue
                    new_prices = dict(sale_prices)
                    new_prices.pop(outgoing_id, None)
                    new_prices[incoming_id] = buy_price
                    gain = remaining_points.get(incoming_id, 0) - remaining_points.get(outgoing_id, 0)
                    move = {
                        "sell_player_id": outgoing_id,
                        "buy_player_id": incoming_id,
                        "sell_price": round(sale_price, 1),
                        "buy_price": round(buy_price, 1),
                    }
                    possible.append((gain, new_squad, new_prices, new_bank, moves + [move]))
            possible.sort(key=lambda row: row[0], reverse=True)
            expanded.extend((squad, prices, bank, moves) for _, squad, prices, bank, moves in possible[:24])
        if not expanded:
            break
        options.extend(expanded)
        frontier = expanded[:24]

    unique: dict[tuple[int, ...], tuple[tuple[int, ...], dict[int, float], float, list[dict[str, Any]]]] = {}
    for option in options:
        squad_ids, _, bank, moves = option
        current = unique.get(squad_ids)
        if current is None or (len(moves), -bank) < (len(current[3]), -current[2]):
            unique[squad_ids] = option
    return list(unique.values())


def optimise_multi_gameweek_route(
    fixture_projections: list[dict[str, Any]],
    players: list[dict[str, Any]],
    squad: list[dict[str, Any]],
    bank: float,
    free_transfers: int | None,
    maximum_free_transfers: int = 5,
    hit_cost: int = 4,
    target_gameweek: int | None = None,
    horizon: int = 6,
    beam_width: int = 60,
    discount: float = 0.96,
    first_gameweek_multiplier: dict[int, float] | None = None,
) -> dict[str, Any]:
    future_gameweeks = sorted(
        {
            integer(row.get("gameweek"))
            for row in fixture_projections
            if integer(row.get("gameweek"))
            and (target_gameweek is None or integer(row.get("gameweek")) >= target_gameweek)
        }
    )[:horizon]
    if not future_gameweeks or not squad or free_transfers is None:
        return {
            "status": "waiting_for_projections" if not future_gameweeks else "unavailable",
            "horizon_gameweeks": future_gameweeks,
            "routes": [],
        }

    player_by_id = {integer(player.get("player_id")): player for player in players}
    squad_ids = tuple(sorted(integer(row.get("player_id")) for row in squad))
    if not legal_squad(squad_ids, player_by_id):
        return {"status": "invalid_current_squad", "horizon_gameweeks": future_gameweeks, "routes": []}
    matrix = projection_matrix(fixture_projections, future_gameweeks, first_gameweek_multiplier)
    total_remaining = {
        player_id: sum(matrix.get(gameweek, {}).get(player_id, 0) for gameweek in future_gameweeks)
        for player_id in player_by_id
    }
    candidate_ids: dict[str, list[int]] = {}
    for position in POSITION_LIMITS:
        candidates = [
            player_id for player_id, player in player_by_id.items()
            if str(player.get("position")) == position and total_remaining.get(player_id, 0) > 0
        ]
        candidates.sort(
            key=lambda player_id: (
                total_remaining.get(player_id, 0),
                total_remaining.get(player_id, 0) / max(0.1, number(player_by_id[player_id].get("price"))),
            ),
            reverse=True,
        )
        current = [player_id for player_id in squad_ids if str(player_by_id[player_id].get("position")) == position]
        candidate_ids[position] = list(dict.fromkeys(candidates[:10] + current))

    initial_prices = tuple(sorted(
        (
            integer(row.get("player_id")),
            number(row.get("selling_price")) / 10
            if number(row.get("selling_price")) >= 10
            else number(row.get("selling_price")) or number(player_by_id[integer(row.get("player_id"))].get("price")),
        )
        for row in squad
    ))
    initial = RouteState(
        squad_ids=squad_ids,
        sale_prices=initial_prices,
        bank=bank,
        free_transfers=max(0, free_transfers),
        score=0,
        undiscounted_points=0,
        moves=(),
    )

    hold_points = 0.0
    for gameweek in future_gameweeks:
        points, _, _ = optimise_gameweek_lineup(squad_ids, player_by_id, matrix.get(gameweek, {}))
        hold_points += points

    states = [initial]
    for offset, gameweek in enumerate(future_gameweeks):
        remaining = {
            player_id: sum(matrix.get(gw, {}).get(player_id, 0) for gw in future_gameweeks[offset:])
            for player_id in player_by_id
        }
        next_states: list[RouteState] = []
        for state in states:
            options = transfer_options(state, player_by_id, candidate_ids, remaining)
            for new_squad, new_prices, new_bank, transfers in options:
                transfers_used = len(transfers)
                paid_transfers = max(0, transfers_used - state.free_transfers)
                points, starters, captain = optimise_gameweek_lineup(
                    new_squad, player_by_id, matrix.get(gameweek, {})
                )
                net_points = points - paid_transfers * hit_cost
                next_free_transfers = min(
                    maximum_free_transfers,
                    max(0, state.free_transfers - transfers_used) + 1,
                )
                move_record = {
                    "gameweek": gameweek,
                    "transfers": [
                        {
                            **move,
                            "sell": player_by_id[move["sell_player_id"]].get("web_name"),
                            "buy": player_by_id[move["buy_player_id"]].get("web_name"),
                        }
                        for move in transfers
                    ],
                    "free_transfers_before": state.free_transfers,
                    "hit_cost": paid_transfers * hit_cost,
                    "bank_after": round(new_bank, 1),
                    "lineup_expected_points": round(points, 3),
                    "net_expected_points": round(net_points, 3),
                    "captain_player_id": captain,
                    "captain": player_by_id[captain].get("web_name") if captain else None,
                    "starter_player_ids": starters,
                }
                next_states.append(
                    RouteState(
                        squad_ids=new_squad,
                        sale_prices=tuple(sorted(new_prices.items())),
                        bank=round(new_bank, 1),
                        free_transfers=next_free_transfers,
                        score=state.score + (discount ** offset) * net_points,
                        undiscounted_points=state.undiscounted_points + net_points,
                        moves=state.moves + (move_record,),
                    )
                )
        deduplicated: dict[tuple[tuple[int, ...], int, float], RouteState] = {}
        for state in next_states:
            key = (state.squad_ids, state.free_transfers, state.bank)
            if key not in deduplicated or state.score > deduplicated[key].score:
                deduplicated[key] = state
        states = sorted(deduplicated.values(), key=lambda state: state.score, reverse=True)[:beam_width]

    best = states[0]
    routes = []
    for state in states[:5]:
        routes.append({
            "projected_net_points": round(state.undiscounted_points, 3),
            "discounted_objective": round(state.score, 3),
            "net_gain_vs_hold": round(state.undiscounted_points - hold_points, 3),
            "total_hit_cost": sum(integer(move.get("hit_cost")) for move in state.moves),
            "final_bank": round(state.bank, 1),
            "free_transfers_after_horizon": state.free_transfers,
            "gameweek_plan": list(state.moves),
            "final_squad_player_ids": list(state.squad_ids),
        })
    return {
        "status": "ready",
        "objective": "Maximise discounted expected starting-XI and captain points, net of transfer hits.",
        "horizon_gameweeks": future_gameweeks,
        "discount_per_gameweek": discount,
        "hold_current_squad_expected_points": round(hold_points, 3),
        "recommended_route": routes[0],
        "alternative_routes": routes[1:],
        "routes": routes,
        "search": {
            "beam_width": beam_width,
            "candidate_players_per_position": 10,
            "maximum_transfers_per_gameweek": 2,
            "states_retained": len(states),
        },
        "assumptions": [
            "Player prices are held constant across the planning horizon.",
            "Only same-position transfers are considered, preserving squad structure.",
            "No chip is assumed within the route.",
            "Later Gameweeks are discounted because forecasts become less certain.",
        ],
    }
