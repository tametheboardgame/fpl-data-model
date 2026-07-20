# FPL Data Model

Personal Fantasy Premier League data collection and analysis platform.

## Purpose

This repository collects current and historical Fantasy Premier League data and prepares analysis-ready datasets for use with ChatGPT.

## Architecture

FPL APIs → GitHub Actions → Python processing → CSV and JSON datasets → ChatGPT

The workflow runs every six hours and can also be started manually. It retrieves public FPL data, builds a compact ChatGPT-facing export layer, validates the outputs and commits refreshed datasets to the repository.

## Current personal team

- FPL team ID: `6435140`
- The ID belongs to the 2025/26 season and will need replacing when the 2026/27 team is created.
- FPL team IDs are season-specific.

No FPL password or private account credentials are used.

## Generated datasets

The files under `data/chatgpt/` are the conversational interface to the model:

- `manifest.json`: refresh time, season, source and row counts
- `fpl_summary.json`: compact season, manager and leading-player summary
- `current_gameweek.json`: current and next gameweek details
- `players.csv`: player prices, ownership, availability and performance statistics
- `teams.csv`: Premier League teams and strength ratings
- `fixtures.csv`: complete fixture list, scores and difficulty ratings
- `player_gameweeks.csv`: gameweek-by-gameweek player performance
- `my_team.json`: manager profile and latest publicly available squad
- `my_gameweek_history.csv`: personal gameweek and rank history

Latest source responses are also retained under `data/raw/latest/` for troubleshooting and future transformations.

## Automation

`.github/workflows/update-fpl-data.yml` performs the following:

1. Installs the Python dependency.
2. Runs the unit tests.
3. Collects current data from the public FPL API.
4. Validates the generated dataset structure and minimum row counts.
5. Commits updated datasets when running on the default branch.

Pull requests perform the complete collection and validation process without committing generated data.

## Local use

Install the dependency:

```bash
python -m pip install --requirement requirements.txt
```

Run the tests:

```bash
python -m unittest discover -s tests -v
```

Refresh the datasets:

```bash
python -m src.update_fpl_data --team-id 6435140 --output-dir data
python -m src.validate_fpl_data --data-dir data
```

## Planned extensions

- Parquet historical archive and DuckDB analytical views
- Expected-points model
- Fixture-adjusted form
- Captaincy analysis
- Transfer recommendations
- Mini-league and rival analysis
