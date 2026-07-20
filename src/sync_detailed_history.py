from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import local
from typing import Any

from src.update_fpl_data import FPLClient, POSITION_NAMES, price, utc_now, write_csv, write_json


PLAYER_IDENTITY_FIELDS = [
    "player_id",
    "player_code",
    "web_name",
    "team_id",
    "team_name",
    "position",
]

FIXTURE_FIELDS = PLAYER_IDENTITY_FIELDS + [
    "fixture",
    "round",
    "kickoff_time",
    "opponent_team",
    "opponent_name",
    "was_home",
    "team_h_score",
    "team_a_score",
    "value",
    "selected",
    "transfers_balance",
    "transfers_in",
    "transfers_out",
    "minutes",
    "starts",
    "goals_scored",
    "assists",
    "clean_sheets",
    "goals_conceded",
    "own_goals",
    "penalties_saved",
    "penalties_missed",
    "yellow_cards",
    "red_cards",
    "saves",
    "bonus",
    "bps",
    "influence",
    "creativity",
    "threat",
    "ict_index",
    "expected_goals",
    "expected_assists",
    "expected_goal_involvements",
    "expected_goals_conceded",
    "defensive_contribution",
    "clearances_blocks_interceptions",
    "recoveries",
    "tackles",
    "total_points",
]

PAST_FIELDS = PLAYER_IDENTITY_FIELDS + [
    "season_name",
    "start_cost",
    "end_cost",
    "total_points",
    "minutes",
    "goals_scored",
    "assists",
    "clean_sheets",
    "goals_conceded",
    "own_goals",
    "penalties_saved",
    "penalties_missed",
    "yellow_cards",
    "red_cards",
    "saves",
    "bonus",
    "bps",
    "influence",
    "creativity",
    "threat",
    "ict_index",
    "starts",
    "expected_goals",
    "expected_assists",
    "expected_goal_involvements",
    "expected_goals_conceded",
]


def identity(player: dict[str, Any], teams: dict[int, dict[str, Any]]) -> dict[str, Any]:
    team = teams.get(player.get("team"), {})
    return {
        "player_id": player.get("id"),
        "player_code": player.get("code"),
        "web_name": player.get("web_name"),
        "team_id": player.get("team"),
        "team_name": team.get("name"),
        "position": POSITION_NAMES.get(player.get("element_type"), "Unknown"),
    }


def flatten_detail(
    player: dict[str, Any],
    payload: dict[str, Any],
    teams: dict[int, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    base = identity(player, teams)
    fixture_rows: list[dict[str, Any]] = []
    for item in payload.get("history", []):
        opponent = teams.get(item.get("opponent_team"), {})
        row = {**base, **item}
        row["opponent_name"] = opponent.get("name")
        row["value"] = price(item.get("value"))
        fixture_rows.append(row)

    past_rows: list[dict[str, Any]] = []
    for item in payload.get("history_past", []):
        row = {**base, **item}
        row.pop("element_code", None)
        row["start_cost"] = price(item.get("start_cost"))
        row["end_cost"] = price(item.get("end_cost"))
        past_rows.append(row)
    return fixture_rows, past_rows


def complete_fields(rows: list[dict[str, Any]], preferred: list[str]) -> list[str]:
    extras = sorted({key for row in rows for key in row}.difference(preferred))
    return preferred + extras


def sync_detailed_history(
    client: FPLClient,
    output_dir: Path,
    max_workers: int = 8,
    max_players: int = 0,
) -> dict[str, Any]:
    bootstrap = client.get("bootstrap-static/")
    if not isinstance(bootstrap, dict):
        raise ValueError("The FPL bootstrap response was not an object")

    players = list(bootstrap.get("elements", []))
    if max_players > 0:
        players = players[:max_players]
    teams = {team["id"]: team for team in bootstrap.get("teams", [])}

    fixture_rows: list[dict[str, Any]] = []
    past_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    thread_state = local()

    def fetch(player: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        if not hasattr(thread_state, "client"):
            thread_state.client = FPLClient(base_url=client.base_url, timeout=client.timeout)
        payload = thread_state.client.get(f"element-summary/{player['id']}/")
        if not isinstance(payload, dict):
            raise ValueError("Unexpected element-summary response")
        return player, payload

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch, player): player for player in players}
        for future in as_completed(futures):
            player = futures[future]
            try:
                resolved_player, payload = future.result()
                player_fixtures, player_past = flatten_detail(resolved_player, payload, teams)
                fixture_rows.extend(player_fixtures)
                past_rows.extend(player_past)
            except Exception as exc:  # each failed player is reported and assessed below
                failures.append(
                    {
                        "player_id": player.get("id"),
                        "web_name": player.get("web_name"),
                        "error": str(exc),
                    }
                )

    if players and len(failures) / len(players) > 0.1:
        raise RuntimeError(f"Detailed history failed for {len(failures)} of {len(players)} players")

    fixture_rows.sort(key=lambda row: (row.get("round") or 0, row.get("fixture") or 0, row.get("player_id") or 0))
    past_rows.sort(key=lambda row: (row.get("season_name") or "", row.get("player_id") or 0))
    chatgpt_dir = output_dir / "chatgpt"
    history_dir = output_dir / "history"
    fixture_count = write_csv(
        chatgpt_dir / "player_fixtures.csv",
        fixture_rows,
        complete_fields(fixture_rows, FIXTURE_FIELDS),
    )
    past_count = write_csv(
        history_dir / "current_player_past_seasons.csv",
        past_rows,
        complete_fields(past_rows, PAST_FIELDS),
    )

    manifest = {
        "generated_at": utc_now(),
        "players_requested": len(players),
        "players_failed": len(failures),
        "fixture_rows": fixture_count,
        "past_season_rows": past_count,
        "files": [
            "data/chatgpt/player_fixtures.csv",
            "data/history/current_player_past_seasons.csv",
        ],
        "failures": failures,
    }
    write_json(chatgpt_dir / "detailed_history_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronise fixture-level FPL player history")
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--max-players", type=int, default=0)
    args = parser.parse_args()
    manifest = sync_detailed_history(
        FPLClient(),
        args.output_dir,
        max_workers=args.max_workers,
        max_players=args.max_players,
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
