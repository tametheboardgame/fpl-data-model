from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
from pathlib import Path
from typing import Any

import requests

from src.sync_historical_fpl import HISTORICAL_FIELDS
from src.update_fpl_data import utc_now, write_json


PLAYER_METADATA_TEMPLATE = (
    "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/"
    "master/data/{season}/players_raw.csv"
)
FIXTURE_METADATA_TEMPLATE = (
    "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/"
    "master/data/{season}/fixtures.csv"
)
ELEMENT_TYPE_TO_POSITION = {
    "1": "GK",
    "2": "DEF",
    "3": "MID",
    "4": "FWD",
}
VALID_POSITIONS = set(ELEMENT_TYPE_TO_POSITION.values())


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "t", "yes", "y"}


def parse_position_metadata(text: str) -> dict[str, str]:
    """Return only the stable player-id to position-code mapping.

    No price, ownership, club, availability or result field from players_raw.csv is
    retained. This keeps the fallback restricted to the metadata gap that prevents
    legal historical squad reconstruction in older seasons.
    """

    output: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(text)):
        player_id = str(row.get("id") or "").strip()
        position = ELEMENT_TYPE_TO_POSITION.get(
            str(row.get("element_type") or "").strip()
        )
        if player_id and position:
            output[player_id] = position
    return output


def parse_fixture_teams(text: str) -> dict[str, tuple[str, str]]:
    """Return only fixture id to (home team id, away team id).

    Fixture scores, stats, finished flags and every other result-bearing field are
    deliberately ignored. The mapping is structural schedule metadata used solely
    to restore the archived player's club from fixture id plus `was_home`.
    """

    output: dict[str, tuple[str, str]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        fixture_id = str(row.get("id") or "").strip()
        team_h = str(row.get("team_h") or "").strip()
        team_a = str(row.get("team_a") or "").strip()
        if fixture_id and team_h and team_a:
            output[fixture_id] = (team_h, team_a)
    return output


def fetch_structural_metadata(
    seasons: list[str],
    *,
    session: requests.Session | None = None,
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, dict[str, tuple[str, str]]],
    dict[str, dict[str, Any]],
]:
    client = session or requests.Session()
    position_mappings: dict[str, dict[str, str]] = {}
    fixture_mappings: dict[str, dict[str, tuple[str, str]]] = {}
    audit: dict[str, dict[str, Any]] = {}
    for season in seasons:
        player_url = PLAYER_METADATA_TEMPLATE.format(season=season)
        player_response = client.get(player_url, timeout=120)
        player_response.raise_for_status()
        player_raw = player_response.text
        position_mapping = parse_position_metadata(player_raw)
        position_mappings[season] = position_mapping

        fixture_url = FIXTURE_METADATA_TEMPLATE.format(season=season)
        fixture_response = client.get(fixture_url, timeout=120)
        fixture_response.raise_for_status()
        fixture_raw = fixture_response.text
        fixture_mapping = parse_fixture_teams(fixture_raw)
        fixture_mappings[season] = fixture_mapping

        audit[season] = {
            "players_raw_url": player_url,
            "players_raw_sha256": hashlib.sha256(
                player_raw.encode("utf-8")
            ).hexdigest(),
            "players_raw_rows": len(list(csv.DictReader(io.StringIO(player_raw)))),
            "usable_position_rows": len(position_mapping),
            "fixtures_url": fixture_url,
            "fixtures_sha256": hashlib.sha256(
                fixture_raw.encode("utf-8")
            ).hexdigest(),
            "fixture_rows": len(list(csv.DictReader(io.StringIO(fixture_raw)))),
            "usable_fixture_team_rows": len(fixture_mapping),
        }
    return position_mappings, fixture_mappings, audit


def prepare_history(
    source_path: Path,
    output_path: Path,
    seasons: list[str],
    *,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    position_mappings, fixture_mappings, source_audit = fetch_structural_metadata(
        seasons,
        session=session,
    )
    requested = set(seasons)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    source_rows = 0
    repaired_position_rows = 0
    unresolved_position_rows = 0
    repaired_team_rows = 0
    unresolved_team_rows = 0
    repaired_position_by_season: dict[str, int] = {season: 0 for season in seasons}
    unresolved_position_by_season: dict[str, int] = {season: 0 for season in seasons}
    repaired_team_by_season: dict[str, int] = {season: 0 for season in seasons}
    unresolved_team_by_season: dict[str, int] = {season: 0 for season in seasons}

    with gzip.open(source_path, "rt", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        with output_path.open("wb") as raw_output:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=raw_output,
                mtime=0,
            ) as compressed:
                with io.TextIOWrapper(
                    compressed,
                    encoding="utf-8",
                    newline="",
                ) as text_output:
                    writer = csv.DictWriter(
                        text_output,
                        fieldnames=HISTORICAL_FIELDS,
                        extrasaction="ignore",
                    )
                    writer.writeheader()
                    for row in reader:
                        source_rows += 1
                        season = str(row.get("season") or "")
                        if season not in requested:
                            writer.writerow(row)
                            continue

                        position = str(row.get("position") or "").strip().upper()
                        if position not in VALID_POSITIONS:
                            player_id = str(row.get("element") or "").strip()
                            fallback = position_mappings.get(season, {}).get(player_id)
                            if fallback:
                                row["position"] = fallback
                                repaired_position_rows += 1
                                repaired_position_by_season[season] += 1
                            else:
                                unresolved_position_rows += 1
                                unresolved_position_by_season[season] += 1

                        team = str(row.get("team") or "").strip()
                        if not team:
                            fixture_id = str(row.get("fixture") or "").strip()
                            fixture_teams = fixture_mappings.get(season, {}).get(fixture_id)
                            if fixture_teams:
                                team_h, team_a = fixture_teams
                                row["team"] = team_h if truthy(row.get("was_home")) else team_a
                                repaired_team_rows += 1
                                repaired_team_by_season[season] += 1
                            else:
                                unresolved_team_rows += 1
                                unresolved_team_by_season[season] += 1

                        writer.writerow(row)

    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    return {
        "generated_at": utc_now(),
        "purpose": "FPL-22C legacy structural metadata reconstruction",
        "source_history": str(source_path),
        "prepared_history": str(output_path),
        "prepared_history_sha256": digest,
        "requested_seasons": seasons,
        "source_rows": source_rows,
        "repaired_position_rows": repaired_position_rows,
        "unresolved_position_rows": unresolved_position_rows,
        "repaired_team_rows": repaired_team_rows,
        "unresolved_team_rows": unresolved_team_rows,
        "repaired_position_rows_by_season": repaired_position_by_season,
        "unresolved_position_rows_by_season": unresolved_position_by_season,
        "repaired_team_rows_by_season": repaired_team_by_season,
        "unresolved_team_rows_by_season": unresolved_team_by_season,
        "structural_metadata_sources": source_audit,
        "retained_fields_from_players_raw": ["id", "element_type"],
        "retained_fields_from_fixtures": ["id", "team_h", "team_a"],
        "explicitly_not_retained_from_players_raw": [
            "now_cost",
            "selected_by_percent",
            "team",
            "status",
            "chance_of_playing_next_round",
            "chance_of_playing_this_round",
            "total_points",
            "event_points",
        ],
        "explicitly_not_retained_from_fixtures": [
            "team_h_score",
            "team_a_score",
            "stats",
            "finished",
            "finished_provisional",
            "minutes",
        ],
        "leakage_statement": (
            "players_raw.csv is used only to map stable player id to position when "
            "the archived Gameweek row has no valid position. fixtures.csv is used "
            "only to map fixture id to its scheduled home/away club ids; the row's "
            "archived was_home flag selects the player's club. No fixture score, "
            "stat, completion state, target-Gameweek ownership, availability or "
            "result is imported into the captain validation."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair missing legacy structural metadata for FPL-22C only."
    )
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit", required=True)
    parser.add_argument("--seasons", nargs="+", required=True)
    args = parser.parse_args()

    audit = prepare_history(
        Path(args.source),
        Path(args.output),
        list(args.seasons),
    )
    write_json(Path(args.audit), audit)
    print(
        "CAPTAIN_STRUCTURAL_FALLBACK="
        f"position_repaired:{audit['repaired_position_rows']} "
        f"position_unresolved:{audit['unresolved_position_rows']} "
        f"team_repaired:{audit['repaired_team_rows']} "
        f"team_unresolved:{audit['unresolved_team_rows']}"
    )


if __name__ == "__main__":
    main()
