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
ELEMENT_TYPE_TO_POSITION = {
    "1": "GK",
    "2": "DEF",
    "3": "MID",
    "4": "FWD",
}
VALID_POSITIONS = set(ELEMENT_TYPE_TO_POSITION.values())


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


def fetch_position_metadata(
    seasons: list[str],
    *,
    session: requests.Session | None = None,
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, Any]]]:
    client = session or requests.Session()
    mappings: dict[str, dict[str, str]] = {}
    audit: dict[str, dict[str, Any]] = {}
    for season in seasons:
        url = PLAYER_METADATA_TEMPLATE.format(season=season)
        response = client.get(url, timeout=120)
        response.raise_for_status()
        raw = response.text
        mapping = parse_position_metadata(raw)
        mappings[season] = mapping
        audit[season] = {
            "url": url,
            "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "metadata_rows": len(list(csv.DictReader(io.StringIO(raw)))),
            "usable_position_rows": len(mapping),
        }
    return mappings, audit


def prepare_history(
    source_path: Path,
    output_path: Path,
    seasons: list[str],
    *,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    mappings, source_audit = fetch_position_metadata(seasons, session=session)
    requested = set(seasons)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    source_rows = 0
    repaired_rows = 0
    unresolved_rows = 0
    repaired_by_season: dict[str, int] = {season: 0 for season in seasons}
    unresolved_by_season: dict[str, int] = {season: 0 for season in seasons}

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
                        position = str(row.get("position") or "").strip().upper()
                        if season in requested and position not in VALID_POSITIONS:
                            player_id = str(row.get("element") or "").strip()
                            fallback = mappings.get(season, {}).get(player_id)
                            if fallback:
                                row["position"] = fallback
                                repaired_rows += 1
                                repaired_by_season[season] += 1
                            else:
                                unresolved_rows += 1
                                unresolved_by_season[season] += 1
                        writer.writerow(row)

    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    return {
        "generated_at": utc_now(),
        "purpose": "FPL-22C legacy position-only metadata reconstruction",
        "source_history": str(source_path),
        "prepared_history": str(output_path),
        "prepared_history_sha256": digest,
        "requested_seasons": seasons,
        "source_rows": source_rows,
        "repaired_position_rows": repaired_rows,
        "unresolved_position_rows": unresolved_rows,
        "repaired_position_rows_by_season": repaired_by_season,
        "unresolved_position_rows_by_season": unresolved_by_season,
        "position_metadata_sources": source_audit,
        "retained_fields_from_players_raw": ["id", "element_type"],
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
        "leakage_statement": (
            "players_raw.csv is used only to map stable player id to position when "
            "the archived Gameweek row has no valid position. Target-Gameweek price, "
            "ownership, club, availability and results remain sourced from the "
            "walk-forward Gameweek archive."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair missing legacy position metadata for FPL-22C only."
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
        "CAPTAIN_POSITION_FALLBACK="
        f"repaired:{audit['repaired_position_rows']} "
        f"unresolved:{audit['unresolved_position_rows']}"
    )


if __name__ == "__main__":
    main()
