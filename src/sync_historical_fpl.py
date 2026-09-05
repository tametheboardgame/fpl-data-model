from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import requests

from src.update_fpl_data import utc_now, write_csv, write_json


SOURCE_REPOSITORY = "https://github.com/vaastav/Fantasy-Premier-League"
RAW_TEMPLATE = (
    "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/"
    "master/data/{season}/gws/merged_gw.csv"
)
DEFAULT_SEASONS = [
    "2018-19",
    "2019-20",
    "2020-21",
    "2021-22",
    "2022-23",
    "2023-24",
    "2024-25",
    "2025-26",
]

HISTORICAL_FIELDS = [
    "season",
    "gameweek",
    "player_name",
    "position",
    "team",
    "element",
    "fixture",
    "opponent_team",
    "was_home",
    "kickoff_time",
    "value",
    "selected",
    "transfers_balance",
    "transfers_in",
    "transfers_out",
    "minutes",
    "starts",
    "total_points",
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
    "defensive_contribution",
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
]


def first_value(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value not in {None, ""}:
            return value
    return ""


def normalise_position(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "GOALKEEPER": "GK",
        "GKP": "GK",
        "DEFENDER": "DEF",
        "MIDFIELDER": "MID",
        "FORWARD": "FWD",
        "STRIKER": "FWD",
    }
    return aliases.get(text, text)


def normalise_history_row(row: dict[str, Any], season: str) -> dict[str, Any]:
    # xP/ep_this is deliberately excluded because the upstream archive warns it can
    # contain post-match information and therefore cause look-ahead bias.
    return {
        "season": season,
        "gameweek": first_value(row, "GW", "round", "gameweek"),
        "player_name": first_value(row, "name", "player_name"),
        "position": normalise_position(first_value(row, "position", "element_type")),
        "team": first_value(row, "team", "team_name"),
        "element": first_value(row, "element", "id"),
        "fixture": row.get("fixture", ""),
        "opponent_team": row.get("opponent_team", ""),
        "was_home": row.get("was_home", ""),
        "kickoff_time": row.get("kickoff_time", ""),
        "value": first_value(row, "value", "now_cost"),
        "selected": row.get("selected", ""),
        "transfers_balance": row.get("transfers_balance", ""),
        "transfers_in": row.get("transfers_in", ""),
        "transfers_out": row.get("transfers_out", ""),
        "minutes": row.get("minutes", ""),
        "starts": row.get("starts", ""),
        "total_points": row.get("total_points", ""),
        "goals_scored": row.get("goals_scored", ""),
        "assists": row.get("assists", ""),
        "clean_sheets": row.get("clean_sheets", ""),
        "goals_conceded": row.get("goals_conceded", ""),
        "own_goals": row.get("own_goals", ""),
        "penalties_saved": row.get("penalties_saved", ""),
        "penalties_missed": row.get("penalties_missed", ""),
        "yellow_cards": row.get("yellow_cards", ""),
        "red_cards": row.get("red_cards", ""),
        "saves": row.get("saves", ""),
        "defensive_contribution": row.get("defensive_contribution", ""),
        "bonus": row.get("bonus", ""),
        "bps": row.get("bps", ""),
        "influence": row.get("influence", ""),
        "creativity": row.get("creativity", ""),
        "threat": row.get("threat", ""),
        "ict_index": row.get("ict_index", ""),
        "expected_goals": row.get("expected_goals", ""),
        "expected_assists": row.get("expected_assists", ""),
        "expected_goal_involvements": row.get("expected_goal_involvements", ""),
        "expected_goals_conceded": row.get("expected_goals_conceded", ""),
    }


def number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


class PositionAccumulator:
    def __init__(self) -> None:
        self.rows = 0
        self.appearances = 0
        self.starts = 0
        self.minutes = 0.0
        self.points = 0.0
        self.goals = 0.0
        self.assists = 0.0
        self.clean_sheets = 0.0
        self.saves = 0.0
        self.defensive_contribution = 0.0
        self.bonus = 0.0
        self.xg = 0.0
        self.xa = 0.0
        self.xgi = 0.0

    def add(self, row: dict[str, Any]) -> None:
        minutes = number(row.get("minutes"))
        self.rows += 1
        self.appearances += int(minutes > 0)
        starts = number(row.get("starts"))
        self.starts += int(starts > 0) if row.get("starts") not in {None, ""} else int(minutes >= 60)
        self.minutes += minutes
        self.points += number(row.get("total_points"))
        self.goals += number(row.get("goals_scored"))
        self.assists += number(row.get("assists"))
        self.clean_sheets += number(row.get("clean_sheets"))
        self.saves += number(row.get("saves"))
        self.defensive_contribution += number(row.get("defensive_contribution"))
        self.bonus += number(row.get("bonus"))
        self.xg += number(row.get("expected_goals"))
        self.xa += number(row.get("expected_assists"))
        self.xgi += number(row.get("expected_goal_involvements"))

    def output(self, season: str, position: str) -> dict[str, Any]:
        per90 = 90 / self.minutes if self.minutes else 0
        return {
            "season": season,
            "position": position,
            "fixture_rows": self.rows,
            "appearances": self.appearances,
            "appearance_rate": round(self.appearances / self.rows, 4) if self.rows else 0,
            "start_rate": round(self.starts / self.rows, 4) if self.rows else 0,
            "average_minutes_per_fixture": round(self.minutes / self.rows, 2) if self.rows else 0,
            "average_minutes_when_appearing": round(self.minutes / self.appearances, 2) if self.appearances else 0,
            "points_per_90": round(self.points * per90, 4),
            "goals_per_90": round(self.goals * per90, 4),
            "assists_per_90": round(self.assists * per90, 4),
            "clean_sheets_per_90": round(self.clean_sheets * per90, 4),
            "saves_per_90": round(self.saves * per90, 4),
            "defensive_contribution_per_90": round(self.defensive_contribution * per90, 4),
            "bonus_per_90": round(self.bonus * per90, 4),
            "xg_per_90": round(self.xg * per90, 4),
            "xa_per_90": round(self.xa * per90, 4),
            "xgi_per_90": round(self.xgi * per90, 4),
        }


def download_season(session: requests.Session, season: str) -> list[dict[str, Any]]:
    url = RAW_TEMPLATE.format(season=season)
    response = session.get(url, timeout=120)
    response.raise_for_status()
    return [normalise_history_row(row, season) for row in csv.DictReader(io.StringIO(response.text))]


def write_gzip_csv(path: Path, rows: Iterable[dict[str, Any]]) -> tuple[int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    count = 0
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                writer = csv.DictWriter(text, fieldnames=HISTORICAL_FIELDS, extrasaction="ignore")
                header = ",".join(HISTORICAL_FIELDS) + "\n"
                digest.update(header.encode("utf-8"))
                writer.writeheader()
                for row in rows:
                    digest.update(
                        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
                    )
                    writer.writerow(row)
                    count += 1
    return count, digest.hexdigest()


def sync_historical(output_dir: Path, seasons: list[str]) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update({"User-Agent": "tametheboardgame/fpl-data-model"})
    all_rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    season_counts: dict[str, int] = {}
    accumulators: dict[tuple[str, str], PositionAccumulator] = defaultdict(PositionAccumulator)
    overall: dict[str, PositionAccumulator] = defaultdict(PositionAccumulator)

    for season in seasons:
        try:
            rows = download_season(session, season)
        except requests.RequestException as exc:
            failures.append({"season": season, "error": str(exc)})
            continue
        season_counts[season] = len(rows)
        all_rows.extend(rows)
        for row in rows:
            position = row.get("position") or "Unknown"
            accumulators[(season, position)].add(row)
            overall[position].add(row)

    if not all_rows:
        raise RuntimeError("No historical FPL seasons could be downloaded")

    history_dir = output_dir / "history"
    row_count, content_sha256 = write_gzip_csv(
        history_dir / "historical_player_gameweeks.csv.gz", all_rows
    )
    prior_rows = [
        accumulator.output(season, position)
        for (season, position), accumulator in sorted(accumulators.items())
    ]
    prior_rows.extend(
        accumulator.output("ALL", position) for position, accumulator in sorted(overall.items())
    )
    prior_fields = list(prior_rows[0].keys())
    write_csv(history_dir / "position_priors.csv", prior_rows, prior_fields)

    manifest = {
        "generated_at": utc_now(),
        "source": SOURCE_REPOSITORY,
        "requested_seasons": seasons,
        "imported_seasons": list(season_counts),
        "season_row_counts": season_counts,
        "total_rows": row_count,
        "content_sha256": content_sha256,
        "failed_seasons": failures,
        "excluded_fields": {
            "xP": "Excluded because the upstream archive warns it can contain post-match information."
        },
        "files": [
            "data/history/historical_player_gameweeks.csv.gz",
            "data/history/position_priors.csv",
        ],
    }
    write_json(history_dir / "historical_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronise multi-season historical FPL data")
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    parser.add_argument("--seasons", nargs="*", default=DEFAULT_SEASONS)
    args = parser.parse_args()
    print(json.dumps(sync_historical(args.output_dir, args.seasons), indent=2))


if __name__ == "__main__":
    main()
