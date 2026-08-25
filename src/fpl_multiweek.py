from __future__ import annotations

from dataclasses import dataclass
import math
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
TRANSFER_FRICTION_POINTS = 1.25
ROUND_TRIP_PENALTY_POINTS = 1.5
MINIMUM_ROUTE_EDGE_POINTS = 4.0
MINIMUM_ROUTE_SEPARATION_POINTS = 1.5
NEGATIVE_CORRELATION_WEIGHT = 0.35
DEFENSIVE_CAPTAIN_UNCERTAINTY_PENALTY = 0.35


def number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def integer(value: Any) -> int:
    return int(number(value))


def fixture_rows_by_player(
    fixture_projections: list[dict[str, Any]], gameweek: int
) -> dict[int, list[dict[str, Any]]]:
    rows: dict[int, list[dict[str, Any]]] = {}
    for row in fixture_projections:
        if integer(row.get("gameweek")) != gameweek:
            continue
        player_id = integer(row.get("player_id"))
        if player_id:
            rows.setdefault(player_id, []).append(row)
    return rows


def lineup_correlation_analysis(
    starter_ids: list[int] | tuple[int, ...] | set[int],
    player_by_id: dict[int, dict[str, Any]],
    fixtures_by_player: dict[int, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    fixtures_by_player = fixtures_by_player or {}
    starters = sorted(set(starter_ids))
    pairs: list[dict[str, Any]] = []
    defensive_positions = {"Goalkeeper", "Defender"}
    attacking_positions = {"Midfielder", "Forward"}

    for defender_id in starters:
        defender = player_by_id.get(defender_id, {})
        if str(defender.get("position")) not in defensive_positions:
            continue
        defender_team = integer(defender.get("team_id"))
        for attacker_id in starters:
            attacker = player_by_id.get(attacker_id, {})
            if str(attacker.get("position")) not in attacking_positions:
                continue
            attacker_team = integer(attacker.get("team_id"))
            if not defender_team or defender_team == attacker_team:
                continue
            for defender_fixture in fixtures_by_player.get(defender_id, []):
                fixture_id = integer(defender_fixture.get("fixture_id"))
                if (
                    not fixture_id
                    or integer(defender_fixture.get("opponent_team_id"))
                    != attacker_team
                ):
                    continue
                attacker_fixture = next(
                    (
                        row
                        for row in fixtures_by_player.get(attacker_id, [])
                        if integer(row.get("fixture_id")) == fixture_id
                        and integer(row.get("opponent_team_id")) == defender_team
                    ),
                    None,
                )
                if attacker_fixture is None:
                    continue
                clean_sheet_probability = number(
                    defender_fixture.get("decision_clean_sheet_probability")
                    or defender_fixture.get("clean_sheet_probability")
                )
                clean_sheet_value = number(
                    defender_fixture.get("component_clean_sheet_points")
                )
                if clean_sheet_value <= 0 and clean_sheet_probability > 0:
                    expected_minutes = number(
                        defender_fixture.get("expected_minutes")
                    )
                    clean_sheet_value = (
                        4
                        * clean_sheet_probability
                        * min(1.0, expected_minutes / 60)
                    )
                attacking_return_probability = number(
                    attacker_fixture.get("component_attacking_return_probability")
                )
                if attacking_return_probability <= 0:
                    attacking_return_probability = 1 - math.exp(
                        -max(
                            0.0,
                            number(attacker_fixture.get("expected_goals"))
                            + number(attacker_fixture.get("expected_assists")),
                        )
                    )
                exposure = clean_sheet_value * attacking_return_probability
                pairs.append(
                    {
                        "fixture_id": fixture_id,
                        "defender_player_id": defender_id,
                        "defender": defender.get("web_name"),
                        "defender_team_id": defender_team,
                        "attacker_player_id": attacker_id,
                        "attacker": attacker.get("web_name"),
                        "attacker_team_id": attacker_team,
                        "clean_sheet_expected_points": round(
                            clean_sheet_value, 4
                        ),
                        "attacking_return_probability": round(
                            attacking_return_probability, 4
                        ),
                        "negative_correlation_exposure": round(exposure, 4),
                    }
                )

    pairs.sort(
        key=lambda row: number(row.get("negative_correlation_exposure")),
        reverse=True,
    )
    return {
        "opposing_pairs": pairs,
        "opposing_pair_count": len(pairs),
        "negative_correlation_exposure": round(
            sum(number(row.get("negative_correlation_exposure")) for row in pairs),
            4,
        ),
        "principle": (
            "Opposing attackers and defenders do not change mean expected points, "
            "but they reduce line-up variance and ceiling. Balanced selection keeps "
            "mean points primary; aggressive selection applies a bounded exposure penalty."
        ),
    }


def _legal_starting_lineup(
    starter_ids: set[int], player_by_id: dict[int, dict[str, Any]]
) -> bool:
    if len(starter_ids) != 11:
        return False
    counts = {
        position: sum(
            str(player_by_id.get(player_id, {}).get("position")) == position
            for player_id in starter_ids
        )
        for position in POSITION_LIMITS
    }
    return all(
        MINIMUM_STARTERS[position]
        <= counts[position]
        <= MAXIMUM_STARTERS[position]
        for position in POSITION_LIMITS
    )


def optimise_gameweek_lineup(
    squad_ids: tuple[int, ...],
    player_by_id: dict[int, dict[str, Any]],
    points_by_player: dict[int, float],
    fixtures_by_player: dict[int, list[dict[str, Any]]] | None = None,
    risk_profile: str = "balanced",
) -> tuple[float, list[int], int | None]:
    def captain_key(player_id: int) -> tuple[float, float]:
        points = points_by_player.get(player_id, 0)
        position = str(player_by_id.get(player_id, {}).get("position"))
        uncertainty_penalty = (
            DEFENSIVE_CAPTAIN_UNCERTAINTY_PENALTY
            if position in {"Goalkeeper", "Defender"}
            else 0.0
        )
        return points - uncertainty_penalty, points

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

    if risk_profile == "aggressive" and fixtures_by_player:
        current = set(starters)
        opposing_pairs = lineup_correlation_analysis(
            set(squad_ids), player_by_id, fixtures_by_player
        ).get("opposing_pairs", [])

        def objective(candidate: set[int]) -> tuple[float, float]:
            captain = max(
                candidate,
                key=captain_key,
                default=None,
            )
            expected_points = sum(
                points_by_player.get(player_id, 0) for player_id in candidate
            ) + points_by_player.get(captain, 0)
            exposure = sum(
                number(row.get("negative_correlation_exposure"))
                for row in opposing_pairs
                if integer(row.get("defender_player_id")) in candidate
                and integer(row.get("attacker_player_id")) in candidate
            )
            return (
                expected_points - NEGATIVE_CORRELATION_WEIGHT * exposure,
                expected_points,
            )

        for _ in range(4):
            current_score = objective(current)
            best = current
            best_score = current_score
            bench = set(squad_ids).difference(current)
            for outgoing in current:
                for incoming in bench:
                    candidate = set(current)
                    candidate.remove(outgoing)
                    candidate.add(incoming)
                    if not _legal_starting_lineup(candidate, player_by_id):
                        continue
                    candidate_score = objective(candidate)
                    if candidate_score > best_score:
                        best = candidate
                        best_score = candidate_score
            if best == current:
                break
            current = best
        starters = list(current)

    captain = max(starters, key=captain_key, default=None)
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
    decision_cost: float
    round_trip_reversals: int
    moves: tuple[dict[str, Any], ...]

    def price_map(self) -> dict[int, float]:
        return dict(self.sale_prices)


def transfer_decision_cost(
    previous_moves: tuple[dict[str, Any], ...],
    transfers: list[dict[str, Any]],
    transfer_friction: float = TRANSFER_FRICTION_POINTS,
    round_trip_penalty: float = ROUND_TRIP_PENALTY_POINTS,
) -> tuple[float, int]:
    """Return an uncertainty cost for transfers and short-horizon reversals."""
    sold_before: set[int] = set()
    bought_before: set[int] = set()
    for gameweek_move in previous_moves:
        for move in gameweek_move.get("transfers", []):
            sold_before.add(integer(move.get("sell_player_id")))
            bought_before.add(integer(move.get("buy_player_id")))

    reversals = 0
    for move in transfers:
        outgoing = integer(move.get("sell_player_id"))
        incoming = integer(move.get("buy_player_id"))
        if incoming in sold_before or outgoing in bought_before:
            reversals += 1
        sold_before.add(outgoing)
        bought_before.add(incoming)
    return (
        len(transfers) * transfer_friction + reversals * round_trip_penalty,
        reversals,
    )


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
        decision_cost=0,
        round_trip_reversals=0,
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
                decision_cost, reversals = transfer_decision_cost(
                    state.moves, transfers
                )
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
                        score=state.score
                        + (discount ** offset) * (net_points - decision_cost),
                        undiscounted_points=state.undiscounted_points + net_points,
                        decision_cost=state.decision_cost + decision_cost,
                        round_trip_reversals=(
                            state.round_trip_reversals + reversals
                        ),
                        moves=state.moves + (move_record,),
                    )
                )
        deduplicated: dict[tuple[tuple[int, ...], int, float], RouteState] = {}
        for state in next_states:
            key = (state.squad_ids, state.free_transfers, state.bank)
            if key not in deduplicated or state.score > deduplicated[key].score:
                deduplicated[key] = state
        states = sorted(deduplicated.values(), key=lambda state: state.score, reverse=True)[:beam_width]

    hold_moves: list[dict[str, Any]] = []
    hold_free_transfers = max(0, free_transfers)
    hold_discounted_points = 0.0
    for offset, gameweek in enumerate(future_gameweeks):
        points, starters, captain = optimise_gameweek_lineup(
            squad_ids, player_by_id, matrix.get(gameweek, {})
        )
        hold_discounted_points += (discount**offset) * points
        hold_moves.append(
            {
                "gameweek": gameweek,
                "transfers": [],
                "free_transfers_before": hold_free_transfers,
                "hit_cost": 0,
                "bank_after": round(bank, 1),
                "lineup_expected_points": round(points, 3),
                "net_expected_points": round(points, 3),
                "captain_player_id": captain,
                "captain": (
                    player_by_id[captain].get("web_name") if captain else None
                ),
                "starter_player_ids": starters,
            }
        )
        hold_free_transfers = min(
            maximum_free_transfers, hold_free_transfers + 1
        )
    hold_state = RouteState(
        squad_ids=squad_ids,
        sale_prices=initial_prices,
        bank=bank,
        free_transfers=hold_free_transfers,
        score=hold_discounted_points,
        undiscounted_points=hold_points,
        decision_cost=0.0,
        round_trip_reversals=0,
        moves=tuple(hold_moves),
    )

    def first_transfer_signature(state: RouteState) -> tuple[int, ...]:
        for move in state.moves:
            transfers = move.get("transfers", [])
            if transfers:
                # Compare route families by their incoming targets. Selling a
                # different low-value player to reach the same target is not
                # independent evidence that the target itself is ambiguous.
                return tuple(
                    sorted(integer(item.get("buy_player_id")) for item in transfers)
                )
        return ()

    best_state = states[0]
    best_has_transfers = any(
        move.get("transfers") for move in best_state.moves
    )
    best_adjusted_gain = (
        best_state.undiscounted_points - hold_points - best_state.decision_cost
    )
    best_signature = first_transfer_signature(best_state)
    runner_up = next(
        (
            state
            for state in states[1:]
            if first_transfer_signature(state) != best_signature
        ),
        None,
    )
    runner_up_gap = (
        best_state.score - runner_up.score if runner_up is not None else None
    )
    recommendation_reason = "Highest robust decision-adjusted expected return."
    rejected_transfer_reason = None
    if best_has_transfers and best_adjusted_gain < MINIMUM_ROUTE_EDGE_POINTS:
        rejected_transfer_reason = "insufficient_edge"
        recommendation_reason = (
            "Hold: no transfer route clears the minimum decision-adjusted edge "
            "after uncertainty costs."
        )
    elif (
        best_has_transfers
        and runner_up_gap is not None
        and runner_up_gap < MINIMUM_ROUTE_SEPARATION_POINTS
    ):
        rejected_transfer_reason = "ambiguous_best_route"
        recommendation_reason = (
            "Hold: competing transfer routes are too close to distinguish reliably."
        )
    if rejected_transfer_reason:
        states = [hold_state] + [
            state
            for state in states
            if first_transfer_signature(state)
        ]
        best_state = hold_state

    routes = []
    for state in states[:5]:
        routes.append({
            "projected_net_points": round(state.undiscounted_points, 3),
            "discounted_objective": round(state.score, 3),
            "net_gain_vs_hold": round(state.undiscounted_points - hold_points, 3),
            "decision_adjusted_gain_vs_hold": round(
                state.undiscounted_points - hold_points - state.decision_cost, 3
            ),
            "transfer_decision_cost": round(state.decision_cost, 3),
            "round_trip_reversals": state.round_trip_reversals,
            "total_hit_cost": sum(integer(move.get("hit_cost")) for move in state.moves),
            "final_bank": round(state.bank, 1),
            "free_transfers_after_horizon": state.free_transfers,
            "gameweek_plan": list(state.moves),
            "final_squad_player_ids": list(state.squad_ids),
        })
    return {
        "status": "ready",
        "objective": "Maximise discounted expected starting-XI and captain points, net of transfer hits and short-horizon transfer uncertainty.",
        "horizon_gameweeks": future_gameweeks,
        "discount_per_gameweek": discount,
        "recommendation_reason": recommendation_reason,
        "robustness": {
            "passed": True,
            "selected_action": (
                "make_transfer"
                if first_transfer_signature(best_state)
                else "hold"
            ),
            "best_transfer_decision_adjusted_gain": round(
                best_adjusted_gain, 3
            ),
            "minimum_route_edge_points": MINIMUM_ROUTE_EDGE_POINTS,
            "runner_up_route_gap": (
                round(runner_up_gap, 3)
                if runner_up_gap is not None
                else None
            ),
            "minimum_route_separation_points": MINIMUM_ROUTE_SEPARATION_POINTS,
            "rejected_transfer_reason": rejected_transfer_reason,
        },
        "hold_current_squad_expected_points": round(hold_points, 3),
        "recommended_route": routes[0],
        "alternative_routes": routes[1:],
        "routes": routes,
        "search": {
            "beam_width": beam_width,
            "candidate_players_per_position": 10,
            "maximum_transfers_per_gameweek": 2,
            "states_retained": len(states),
            "transfer_friction_points": TRANSFER_FRICTION_POINTS,
            "round_trip_penalty_points": ROUND_TRIP_PENALTY_POINTS,
            "minimum_route_edge_points": MINIMUM_ROUTE_EDGE_POINTS,
            "minimum_route_separation_points": MINIMUM_ROUTE_SEPARATION_POINTS,
        },
        "assumptions": [
            "Player prices are held constant across the planning horizon.",
            "Only same-position transfers are considered, preserving squad structure.",
            "No chip is assumed within the route.",
            "Later Gameweeks are discounted because forecasts become less certain.",
            "Every planned transfer carries a small uncertainty cost, with an additional penalty for selling and quickly rebuying the same player.",
        ],
    }
