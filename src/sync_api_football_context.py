from __future__ import annotations

import argparse
import csv
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.external_context import read_context_signals, load_source_registry


BASE_URL = "https://v3.football.api-sports.io"
PREMIER_LEAGUE_ID = 39
TEAM_ALIASES = {
    "manchester city": "man city",
    "manchester united": "man utd",
    "newcastle united": "newcastle",
    "nottingham forest": "nott'm forest",
    "tottenham hotspur": "spurs",
    "wolverhampton wanderers": "wolves",
}


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalise(value: Any) -> str:
    ascii_value = unicodedata.normalize("NFKD", str(value or "")).encode(
        "ascii", "ignore"
    ).decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def normalise_team(value: Any) -> str:
    name = normalise(value)
    return normalise(TEAM_ALIASES.get(name, name))


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def season_start(season: str) -> int:
    match = re.search(r"(20\d{2})", season)
    if not match:
        raise ValueError(f"Cannot determine API-Football season from {season!r}")
    return int(match.group(1))


def match_player(
    provider_player: dict[str, Any], provider_team: Any, players: list[dict[str, Any]]
) -> dict[str, Any] | None:
    provider_name = normalise(provider_player.get("name"))
    provider_surname = provider_name.split()[-1:] or [""]
    team = normalise_team(provider_team)
    candidates = []
    for player in players:
        if normalise_team(player.get("team_name")) != team:
            continue
        names = {
            normalise(player.get("web_name")),
            normalise(player.get("second_name")),
            normalise(f"{player.get('first_name', '')} {player.get('second_name', '')}"),
        }
        surnames = {name.split()[-1] for name in names if name}
        if provider_name in names or provider_surname[0] in surnames:
            candidates.append(player)
    return candidates[0] if len(candidates) == 1 else None


def injury_availability(reason: Any, injury_type: Any = None) -> float:
    text = normalise(f"{injury_type or ''} {reason or ''}")
    if any(term in text for term in ("suspended", "red card", "ban")):
        return 0.0
    if "doubtful" in text:
        return 0.25
    if any(term in text for term in ("questionable", "knock", "fitness")):
        return 0.5
    return 0.1


def match_fixtures(
    provider_rows: list[dict[str, Any]], fpl_fixtures: list[dict[str, Any]]
) -> dict[int, dict[str, Any]]:
    matched = {}
    for provider in provider_rows:
        fixture = provider.get("fixture", {})
        kickoff = parse_time(fixture.get("date"))
        home = normalise_team(provider.get("teams", {}).get("home", {}).get("name"))
        away = normalise_team(provider.get("teams", {}).get("away", {}).get("name"))
        if not kickoff:
            continue
        candidates = [
            row for row in fpl_fixtures
            if normalise_team(row.get("home_team_name")) == home
            and normalise_team(row.get("away_team_name")) == away
            and parse_time(row.get("kickoff_time"))
            and abs((parse_time(row.get("kickoff_time")) - kickoff).total_seconds()) <= 12 * 3600
        ]
        if len(candidates) == 1:
            matched[int(fixture["id"])] = candidates[0]
    return matched


def _signal(
    *, source_id: str, signal_type: str, value: float, player: dict[str, Any],
    fpl_fixture: dict[str, Any], provider_fixture_id: int, provider_player_id: int,
    observed_at: datetime, note: str,
) -> dict[str, Any]:
    stamp = observed_at.replace(microsecond=0).strftime("%Y%m%dT%H%M%SZ")
    kickoff = parse_time(fpl_fixture.get("kickoff_time"))
    expires = (kickoff + timedelta(hours=4)) if kickoff else observed_at + timedelta(days=2)
    return {
        "signal_id": f"api-football-{signal_type}-{provider_fixture_id}-{provider_player_id}-{stamp}",
        "observed_at": observed_at.replace(microsecond=0).isoformat(),
        "valid_from": observed_at.replace(microsecond=0).isoformat(),
        "expires_at": expires.replace(microsecond=0).isoformat(),
        "source_id": source_id,
        "signal_type": signal_type,
        "value": value,
        "confidence": 1.0 if source_id.endswith("lineup") else 0.9,
        "player_id": int(float(player["player_id"])),
        "team_id": int(float(player["team_id"])),
        "fixture_id": int(float(fpl_fixture["fixture_id"])),
        "gameweek": int(float(fpl_fixture.get("gameweek") or 0)),
        "source_url": f"{BASE_URL}/fixtures/id/{provider_fixture_id}",
        "note": note,
        "status": "active",
    }


def signals_from_injuries(
    payload: dict[str, Any], players: list[dict[str, Any]], fixture_map: dict[int, dict[str, Any]],
    observed_at: datetime,
) -> tuple[list[dict[str, Any]], int]:
    signals, unmatched = [], 0
    for row in payload.get("response", []):
        provider_fixture = int(row.get("fixture", {}).get("id") or 0)
        fpl_fixture = fixture_map.get(provider_fixture)
        player_data = row.get("player", {})
        matched = match_player(player_data, row.get("team", {}).get("name"), players)
        if not fpl_fixture or not matched:
            unmatched += bool(fpl_fixture and not matched)
            continue
        reason = player_data.get("reason") or player_data.get("type") or "reported unavailable"
        signals.append(_signal(
            source_id="api_football_injury", signal_type="availability_probability",
            value=injury_availability(reason, player_data.get("type")), player=matched,
            fpl_fixture=fpl_fixture, provider_fixture_id=provider_fixture,
            provider_player_id=int(player_data.get("id") or 0), observed_at=observed_at,
            note=f"API-Football injury report: {reason}",
        ))
    return signals, unmatched


def signals_from_lineup(
    payload: dict[str, Any], players: list[dict[str, Any]], fpl_fixture: dict[str, Any],
    provider_fixture_id: int, observed_at: datetime,
) -> tuple[list[dict[str, Any]], int]:
    signals, unmatched = [], 0
    for team in payload.get("response", []):
        team_name = team.get("team", {}).get("name")
        for group, probability in (("startXI", 1.0), ("substitutes", 0.0)):
            for item in team.get(group, []):
                provider_player = item.get("player", {})
                matched = match_player(provider_player, team_name, players)
                if not matched:
                    unmatched += 1
                    continue
                signals.append(_signal(
                    source_id="api_football_confirmed_lineup",
                    signal_type="start_probability", value=probability, player=matched,
                    fpl_fixture=fpl_fixture, provider_fixture_id=provider_fixture_id,
                    provider_player_id=int(provider_player.get("id") or 0), observed_at=observed_at,
                    note="API-Football confirmed starting XI" if probability else "API-Football confirmed substitute",
                ))
    return signals, unmatched


class ApiFootballClient:
    def __init__(self, api_key: str, max_requests: int = 8) -> None:
        self.api_key = api_key
        self.max_requests = max_requests
        self.request_count = 0

    def get(self, endpoint: str, **params: Any) -> dict[str, Any]:
        import requests

        if self.request_count >= self.max_requests:
            raise RuntimeError("API-Football request budget exhausted")
        response = requests.get(
            f"{BASE_URL}/{endpoint.lstrip('/')}", params=params,
            headers={"x-apisports-key": self.api_key}, timeout=30,
        )
        self.request_count += 1
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError(f"API-Football error: {payload['errors']}")
        return payload


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def append_signals(path: Path, signals: list[dict[str, Any]], registry_path: Path) -> int:
    registry = load_source_registry(registry_path)
    existing = {str(row["signal_id"]) for row in read_context_signals(path, registry)}
    fresh = [row for row in signals if str(row["signal_id"]) not in existing]
    if fresh:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for row in fresh:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    read_context_signals(path, registry)
    return len(fresh)


def sync(data_dir: Path, client: ApiFootballClient, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    chatgpt = data_dir / "chatgpt"
    players = read_csv(chatgpt / "players.csv")
    fpl_fixtures = read_csv(chatgpt / "fixtures.csv")
    manifest = json.loads((chatgpt / "manifest.json").read_text(encoding="utf-8"))
    season = str(manifest.get("season"))
    raw_dir = data_dir / "raw" / "external" / "api-football" / "latest"
    fixtures_payload = client.get("fixtures", league=PREMIER_LEAGUE_ID, season=season_start(season), next=20)
    _write_json(raw_dir / "fixtures.json", fixtures_payload)
    fixture_map = match_fixtures(fixtures_payload.get("response", []), fpl_fixtures)
    injuries_payload = client.get("injuries", league=PREMIER_LEAGUE_ID, season=season_start(season))
    _write_json(raw_dir / "injuries.json", injuries_payload)
    signals, unmatched = signals_from_injuries(injuries_payload, players, fixture_map, now)
    lineup_fixtures = []
    for provider_id, fpl_fixture in fixture_map.items():
        kickoff = parse_time(fpl_fixture.get("kickoff_time"))
        if kickoff and timedelta(0) <= kickoff - now <= timedelta(hours=3):
            lineup_fixtures.append((provider_id, fpl_fixture))
    for provider_id, fpl_fixture in lineup_fixtures[: max(0, client.max_requests - client.request_count)]:
        payload = client.get("fixtures/lineups", fixture=provider_id)
        _write_json(raw_dir / f"lineups-{provider_id}.json", payload)
        rows, misses = signals_from_lineup(payload, players, fpl_fixture, provider_id, now)
        signals.extend(rows)
        unmatched += misses
    appended = append_signals(
        data_dir / "context" / "signals.jsonl", signals,
        data_dir / "context" / "sources.json",
    )
    status = {
        "provider": "API-Football", "status": "ok", "season": season,
        "generated_at": now.replace(microsecond=0).isoformat(),
        "request_count": client.request_count,
        "provider_fixtures": len(fixtures_payload.get("response", [])),
        "matched_fixtures": len(fixture_map), "signals_generated": len(signals),
        "signals_appended": appended, "unmatched_players": unmatched,
    }
    _write_json(data_dir / "context" / "provider_status.json", status)
    return status


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync API-Football context into the append-only signal journal")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--max-requests", type=int, default=8)
    args = parser.parse_args()
    key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if not key:
        raise SystemExit("API_FOOTBALL_KEY is not configured")
    print(json.dumps(sync(args.data_dir, ApiFootballClient(key, args.max_requests)), indent=2))


if __name__ == "__main__":
    main()
