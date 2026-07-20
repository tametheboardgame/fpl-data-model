from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


REQUIRED_FILES = [
    "manifest.json",
    "current_gameweek.json",
    "fpl_summary.json",
    "my_team.json",
    "players.csv",
    "teams.csv",
    "fixtures.csv",
    "player_gameweeks.csv",
    "my_gameweek_history.csv",
]


def csv_count(path: Path) -> int:
    with path.open(encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def validate(data_dir: Path) -> None:
    directory = data_dir / "chatgpt"
    missing = [name for name in REQUIRED_FILES if not (directory / name).is_file()]
    if missing:
        raise ValueError(f"Missing required ChatGPT datasets: {', '.join(missing)}")

    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("generated_at") or not manifest.get("season"):
        raise ValueError("Manifest is missing generated_at or season")

    players = csv_count(directory / "players.csv")
    teams = csv_count(directory / "teams.csv")
    fixtures = csv_count(directory / "fixtures.csv")
    if players < 100:
        raise ValueError(f"Unexpected player count: {players}")
    if teams != 20:
        raise ValueError(f"Unexpected team count: {teams}")
    if fixtures < 300:
        raise ValueError(f"Unexpected fixture count: {fixtures}")

    my_team = json.loads((directory / "my_team.json").read_text(encoding="utf-8"))
    if "team_id" not in my_team or "available" not in my_team:
        raise ValueError("my_team.json does not contain the required identity fields")

    print(f"Validated {players} players, {teams} teams and {fixtures} fixtures")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate generated FPL datasets")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    validate(args.data_dir)


if __name__ == "__main__":
    main()
