from __future__ import annotations

import argparse
import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests


API_BASE = "https://fantasy.premierleague.com/api"
DEFAULT_TEAM_ID = 6435140
POSITION_NAMES = {1: "Goalkeeper", 2: "Defender", 3: "Midfielder", 4: "Forward"}


class FPLAPIError(RuntimeError):
    """Raised when the FPL API cannot provide a required dataset."""


class FPLClient:
    def __init__(self, base_url: str = API_BASE, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "tametheboardgame/fpl-data-model",
            }
        )

    def get(self, path: str, *, optional: bool = False) -> Any | None:
        url = f"{self.base_url}/{path.lstrip('/')}"
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.session.get(url, timeout=self.timeout)
                if optional and response.status_code in {401, 403, 404}:
                    return None
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(2**attempt)
        raise FPLAPIError(f"Failed to retrieve {url}: {last_error}")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def infer_season(events: list[dict[str, Any]]) -> str | None:
    deadlines = [event.get("deadline_time") for event in events if event.get("deadline_time")]
    if not deadlines:
        return None
    first_year = datetime.fromisoformat(deadlines[0].replace("Z", "+00:00")).year
    last_year = datetime.fromisoformat(deadlines[-1].replace("Z", "+00:00")).year
    return f"{first_year}/{str(last_year)[-2:]}"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> int:
    materialised = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(materialised)
    return len(materialised)


def current_and_next_event(events: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    current = next((event for event in events if event.get("is_current")), None)
    next_event = next((event for event in events if event.get("is_next")), None)
    if current is None:
        finished = [event for event in events if event.get("finished")]
        current = finished[-1] if finished else None
    return current, next_event


def player_rows(bootstrap: dict[str, Any]) -> list[dict[str, Any]]:
    teams = {team["id"]: team for team in bootstrap.get("teams", [])}
    rows: list[dict[str, Any]] = []
    for player in bootstrap.get("elements", []):
        team = teams.get(player.get("team"), {})
        rows.append(
            {
                "player_id": player.get("id"),
                "web_name": player.get("web_name"),
                "first_name": player.get("first_name"),
                "second_name": player.get("second_name"),
                "team_id": player.get("team"),
                "team_name": team.get("name"),
                "team_short_name": team.get("short_name"),
                "position": POSITION_NAMES.get(player.get("element_type"), "Unknown"),
                "price": round((player.get("now_cost") or 0) / 10, 1),
                "status": player.get("status"),
                "news": player.get("news"),
                "chance_of_playing_next_round": player.get("chance_of_playing_next_round"),
                "selected_by_percent": player.get("selected_by_percent"),
                "form": player.get("form"),
                "points_per_game": player.get("points_per_game"),
                "total_points": player.get("total_points"),
                "event_points": player.get("event_points"),
                "minutes": player.get("minutes"),
                "starts": player.get("starts"),
                "goals_scored": player.get("goals_scored"),
                "assists": player.get("assists"),
                "clean_sheets": player.get("clean_sheets"),
                "goals_conceded": player.get("goals_conceded"),
                "saves": player.get("saves"),
                "bonus": player.get("bonus"),
                "bps": player.get("bps"),
                "expected_goals": player.get("expected_goals"),
                "expected_assists": player.get("expected_assists"),
                "expected_goal_involvements": player.get("expected_goal_involvements"),
                "expected_goals_conceded": player.get("expected_goals_conceded"),
                "influence": player.get("influence"),
                "creativity": player.get("creativity"),
                "threat": player.get("threat"),
                "ict_index": player.get("ict_index"),
                "transfers_in_event": player.get("transfers_in_event"),
                "transfers_out_event": player.get("transfers_out_event"),
            }
        )
    return rows


def team_rows(bootstrap: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "team_id": team.get("id"),
            "name": team.get("name"),
            "short_name": team.get("short_name"),
            "strength": team.get("strength"),
            "strength_overall_home": team.get("strength_overall_home"),
            "strength_overall_away": team.get("strength_overall_away"),
            "strength_attack_home": team.get("strength_attack_home"),
            "strength_attack_away": team.get("strength_attack_away"),
            "strength_defence_home": team.get("strength_defence_home"),
            "strength_defence_away": team.get("strength_defence_away"),
        }
        for team in bootstrap.get("teams", [])
    ]


def fixture_rows(fixtures: list[dict[str, Any]], bootstrap: dict[str, Any]) -> list[dict[str, Any]]:
    teams = {team["id"]: team for team in bootstrap.get("teams", [])}
    rows: list[dict[str, Any]] = []
    for fixture in fixtures:
        home = teams.get(fixture.get("team_h"), {})
        away = teams.get(fixture.get("team_a"), {})
        rows.append(
            {
                "fixture_id": fixture.get("id"),
                "gameweek": fixture.get("event"),
                "kickoff_time": fixture.get("kickoff_time"),
                "started": fixture.get("started"),
                "finished": fixture.get("finished"),
                "home_team_id": fixture.get("team_h"),
                "home_team": home.get("name"),
                "away_team_id": fixture.get("team_a"),
                "away_team": away.get("name"),
                "home_score": fixture.get("team_h_score"),
                "away_score": fixture.get("team_a_score"),
                "home_difficulty": fixture.get("team_h_difficulty"),
                "away_difficulty": fixture.get("team_a_difficulty"),
            }
        )
    return rows


def gameweek_rows(
    live_by_event: dict[int, dict[str, Any]], bootstrap: dict[str, Any]
) -> list[dict[str, Any]]:
    players = {player["id"]: player for player in bootstrap.get("elements", [])}
    teams = {team["id"]: team for team in bootstrap.get("teams", [])}
    rows: list[dict[str, Any]] = []
    stat_fields = [
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
        "total_points",
    ]
    for event, payload in sorted(live_by_event.items()):
        for item in payload.get("elements", []):
            player = players.get(item.get("id"), {})
            team = teams.get(player.get("team"), {})
            row = {
                "gameweek": event,
                "player_id": item.get("id"),
                "web_name": player.get("web_name"),
                "team_id": player.get("team"),
                "team_name": team.get("name"),
                "position": POSITION_NAMES.get(player.get("element_type"), "Unknown"),
            }
            stats = item.get("stats", {})
            row.update({field: stats.get(field) for field in stat_fields})
            rows.append(row)
    return rows


def personal_team_payload(
    team_id: int,
    profile: dict[str, Any] | None,
    history: dict[str, Any] | None,
    picks: dict[str, Any] | None,
    bootstrap: dict[str, Any],
) -> dict[str, Any]:
    if profile is None:
        return {
            "team_id": team_id,
            "available": False,
            "message": "The team is not available in the current FPL season. Team IDs change each season.",
        }

    players = {player["id"]: player for player in bootstrap.get("elements", [])}
    teams = {team["id"]: team for team in bootstrap.get("teams", [])}
    squad = []
    for pick in (picks or {}).get("picks", []):
        player = players.get(pick.get("element"), {})
        club = teams.get(player.get("team"), {})
        squad.append(
            {
                "squad_position": pick.get("position"),
                "player_id": pick.get("element"),
                "web_name": player.get("web_name"),
                "club": club.get("name"),
                "position": POSITION_NAMES.get(player.get("element_type"), "Unknown"),
                "multiplier": pick.get("multiplier"),
                "is_captain": pick.get("is_captain"),
                "is_vice_captain": pick.get("is_vice_captain"),
                "purchase_price": (pick.get("purchase_price") / 10) if pick.get("purchase_price") is not None else None,
                "selling_price": (pick.get("selling_price") / 10) if pick.get("selling_price") is not None else None,
            }
        )

    current_history = (history or {}).get("current", [])
    latest_event = max((row.get("event", 0) for row in current_history), default=None)
    return {
        "team_id": team_id,
        "available": True,
        "team_name": profile.get("name"),
        "manager": " ".join(
            part for part in [profile.get("player_first_name"), profile.get("player_last_name")] if part
        ),
        "overall_points": profile.get("summary_overall_points"),
        "overall_rank": profile.get("summary_overall_rank"),
        "last_gameweek_points": profile.get("summary_event_points"),
        "latest_squad_gameweek": latest_event,
        "entry_history": (picks or {}).get("entry_history"),
        "active_chip": (picks or {}).get("active_chip"),
        "squad": squad,
    }


def top_players(players: list[dict[str, Any]], key: str, limit: int = 15) -> list[dict[str, Any]]:
    def numeric(row: dict[str, Any]) -> float:
        try:
            return float(row.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    selected = sorted(players, key=numeric, reverse=True)[:limit]
    fields = ["player_id", "web_name", "team_name", "position", "price", key]
    return [{field: row.get(field) for field in fields} for row in selected]


def build_datasets(
    output_dir: Path,
    team_id: int,
    bootstrap: dict[str, Any],
    fixtures: list[dict[str, Any]],
    live_by_event: dict[int, dict[str, Any]],
    profile: dict[str, Any] | None,
    history: dict[str, Any] | None,
    picks: dict[str, Any] | None,
) -> dict[str, Any]:
    chatgpt_dir = output_dir / "chatgpt"
    raw_dir = output_dir / "raw" / "latest"
    generated_at = utc_now()
    events = bootstrap.get("events", [])
    current_event, next_event = current_and_next_event(events)

    players = player_rows(bootstrap)
    teams = team_rows(bootstrap)
    fixture_data = fixture_rows(fixtures, bootstrap)
    gameweeks = gameweek_rows(live_by_event, bootstrap)
    my_team = personal_team_payload(team_id, profile, history, picks, bootstrap)

    player_fields = list(players[0].keys()) if players else ["player_id"]
    team_fields = list(teams[0].keys()) if teams else ["team_id"]
    fixture_fields = list(fixture_data[0].keys()) if fixture_data else ["fixture_id"]
    gameweek_fields = list(gameweeks[0].keys()) if gameweeks else ["gameweek", "player_id"]
    history_rows = (history or {}).get("current", [])
    history_fields = sorted({key for row in history_rows for key in row}) or ["event"]

    counts = {
        "players": write_csv(chatgpt_dir / "players.csv", players, player_fields),
        "teams": write_csv(chatgpt_dir / "teams.csv", teams, team_fields),
        "fixtures": write_csv(chatgpt_dir / "fixtures.csv", fixture_data, fixture_fields),
        "player_gameweeks": write_csv(chatgpt_dir / "player_gameweeks.csv", gameweeks, gameweek_fields),
        "my_gameweek_history": write_csv(
            chatgpt_dir / "my_gameweek_history.csv", history_rows, history_fields
        ),
    }

    current_gameweek = {
        "generated_at": generated_at,
        "current": current_event,
        "next": next_event,
    }
    summary = {
        "generated_at": generated_at,
        "season": infer_season(events),
        "current_gameweek": current_event.get("id") if current_event else None,
        "next_gameweek": next_event.get("id") if next_event else None,
        "total_managers": bootstrap.get("total_players"),
        "team": {key: my_team.get(key) for key in ["team_id", "available", "team_name", "overall_points", "overall_rank"]},
        "top_total_points": top_players(players, "total_points"),
        "top_form": top_players(players, "form"),
        "most_transferred_in_this_gameweek": top_players(players, "transfers_in_event"),
    }

    write_json(chatgpt_dir / "current_gameweek.json", current_gameweek)
    write_json(chatgpt_dir / "my_team.json", my_team)
    write_json(chatgpt_dir / "fpl_summary.json", summary)
    write_json(raw_dir / "bootstrap-static.json", bootstrap)
    write_json(raw_dir / "fixtures.json", fixtures)
    if profile is not None:
        write_json(raw_dir / "entry.json", profile)
    if history is not None:
        write_json(raw_dir / "entry-history.json", history)
    if picks is not None:
        write_json(raw_dir / "latest-picks.json", picks)

    files = [
        "current_gameweek.json",
        "fixtures.csv",
        "fpl_summary.json",
        "my_gameweek_history.csv",
        "my_team.json",
        "player_gameweeks.csv",
        "players.csv",
        "teams.csv",
    ]
    manifest = {
        "generated_at": generated_at,
        "season": infer_season(events),
        "source": API_BASE,
        "team_id": team_id,
        "datasets": [{"path": f"data/chatgpt/{name}"} for name in files],
        "row_counts": counts,
    }
    write_json(chatgpt_dir / "manifest.json", manifest)
    return manifest


def collect(client: FPLClient, output_dir: Path, team_id: int) -> dict[str, Any]:
    bootstrap = client.get("bootstrap-static/")
    fixtures = client.get("fixtures/")
    if not isinstance(bootstrap, dict) or not isinstance(fixtures, list):
        raise FPLAPIError("The FPL API returned an unexpected core data structure")

    events = bootstrap.get("events", [])
    completed_events = [
        int(event["id"])
        for event in events
        if event.get("finished") or event.get("is_current")
    ]
    live_by_event: dict[int, dict[str, Any]] = {}
    for event in completed_events:
        payload = client.get(f"event/{event}/live/")
        if isinstance(payload, dict):
            live_by_event[event] = payload

    profile = client.get(f"entry/{team_id}/", optional=True)
    history = client.get(f"entry/{team_id}/history/", optional=True) if profile else None
    latest_event = max(
        (int(item.get("event", 0)) for item in (history or {}).get("current", [])),
        default=0,
    )
    picks = (
        client.get(f"entry/{team_id}/event/{latest_event}/picks/", optional=True)
        if profile and latest_event
        else None
    )
    return build_datasets(
        output_dir, team_id, bootstrap, fixtures, live_by_event, profile, history, picks
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh the FPL data model")
    parser.add_argument(
        "--team-id",
        type=int,
        default=int(os.environ.get("FPL_TEAM_ID", DEFAULT_TEAM_ID)),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    manifest = collect(FPLClient(), args.output_dir, args.team_id)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
