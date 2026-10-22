"""Run a diagnostic-only forced first-GW transfer through the unchanged control optimiser.

Does not write files, change production configuration or mutate FPL account state.
Requires a fresh, verified official team snapshot and the exact production model
inputs. This is an investigative tool, not a transfer recommendation.
"""
import argparse
import csv
import json
from pathlib import Path
from unittest.mock import patch

from src import fpl_multiweek


def load_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def forced_first_week_route(fixture_projections, players, squad, bank,
                            free_transfers, candidate_id, target_gameweek,
                            maximum_free_transfers=5, hit_cost=4,
                            first_gameweek_multiplier=None,
                            first_gameweek_captain_scores=None):
    original = fpl_multiweek.transfer_options
    first_call = True

    def diagnostic_options(state, player_by_id, candidate_ids, remaining_points,
                           max_transfers=2):
        nonlocal first_call
        if not first_call:
            return original(state, player_by_id, candidate_ids, remaining_points, max_transfers)
        first_call = False
        if candidate_id not in player_by_id:
            raise ValueError("Candidate absent from player data")
        position = str(player_by_id[candidate_id].get("position"))
        augmented = {key: list(ids) for key, ids in candidate_ids.items()}
        augmented.setdefault(position, [])
        if candidate_id not in augmented[position]:
            augmented[position].append(candidate_id)
        options = original(state, player_by_id, augmented, remaining_points, max_transfers)
        forced = [option for option in options
                  if any(move["buy_player_id"] == candidate_id for move in option[3])]
        if not forced:
            raise ValueError("No legal first-week purchase of candidate; check budget and club limits")
        return forced

    with patch.object(fpl_multiweek, "transfer_options", diagnostic_options):
        result = fpl_multiweek.optimise_multi_gameweek_route(
            fixture_projections, players, squad, bank, free_transfers,
            maximum_free_transfers=maximum_free_transfers,
            hit_cost=hit_cost, target_gameweek=target_gameweek,
            first_gameweek_multiplier=first_gameweek_multiplier,
            first_gameweek_captain_scores=first_gameweek_captain_scores,
        )
    route = result.get("recommended_route") or {}
    first = (route.get("gameweek_plan") or [{}])[0]
    if not any(move.get("buy_player_id") == candidate_id for move in first.get("transfers", [])):
        raise ValueError("Forced first-week purchase absent from returned route")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--players", type=Path, required=True)
    p.add_argument("--fixtures", type=Path, required=True)
    p.add_argument("--team", type=Path, required=True)
    p.add_argument("--candidate-id", type=int, required=True)
    p.add_argument("--target-gameweek", type=int, required=True)
    p.add_argument("--bank", type=float, required=True)
    p.add_argument("--free-transfers", type=int, required=True)
    args = p.parse_args()
    team = json.loads(args.team.read_text(encoding="utf-8"))
    squad = team.get("squad")
    if not isinstance(squad, list) or not squad:
        raise ValueError("Provide a verified registered squad list in team.squad")
    result = forced_first_week_route(
        load_csv(args.fixtures), load_csv(args.players), squad,
        args.bank, args.free_transfers, args.candidate_id, args.target_gameweek)
    print(json.dumps({
        "scope": "diagnostic_only_not_exact_production_replay_without_context_multipliers",
        "candidate_id": args.candidate_id,
        "gameweek": args.target_gameweek,
        "route": result.get("recommended_route"),
        "limitations": [
            "Supply the same fixture projections and evaluated player data as production.",
            "Exact production replay requires first-GW risk multipliers and captain scores.",
            "This compares a constrained beam-search result, not a global optimum.",
        ],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
