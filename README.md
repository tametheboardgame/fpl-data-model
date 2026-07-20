# FPL Data Model

Personal Fantasy Premier League data collection and analysis platform.

## Purpose

This repository collects current and historical Fantasy Premier League data and prepares analysis-ready datasets for use with ChatGPT.

## Architecture

FPL APIs → GitHub Actions → Python processing → CSV and JSON datasets → ChatGPT

The automated workflows retrieve public FPL data, preserve historical and human observations, build leakage-safe rolling features and simulate player-level FPL returns for conversation and decision support. Team results are context; individual FPL points are the prediction target.

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
- `snapshot_index.json`: index of daily and pre-deadline player market snapshots
- `teams.csv`: Premier League teams and strength ratings
- `fixtures.csv`: complete fixture list, scores and difficulty ratings
- `player_gameweeks.csv`: gameweek-by-gameweek player performance
- `player_fixtures.csv`: match-level player history, including separate double-gameweek fixtures
- `my_team.json`: manager profile and latest publicly available squad
- `my_gameweek_history.csv`: personal gameweek and rank history
- `my_transfers.csv`: players bought and sold, prices and transfer times
- `manager_history.json`: previous season summaries and chip usage
- `detailed_history_manifest.json`: status and row counts for the daily detailed-history synchronisation
- `player_rolling_features.csv`: player form and usage over the last 3, 6 and 10 fixtures
- `team_rolling_features.csv`: team attack and defence form over the last 3, 6 and 10 fixtures
- `player_projections.csv`: fixture-level player return distributions, including the live expected points and a shadow component-model breakdown with percentiles and 6+, 10+ and 15+ probabilities
- `player_projection_horizons.csv`: player expected points, distribution ranges, minutes and value over the next 1, 3, 5 and 6 gameweeks
- `projection_summary.json`: model version, row counts, limitations and leading projections
- `prediction_index.json`: index of immutable pre-deadline prediction snapshots
- `prediction_accuracy.csv`: gameweek-level MAE, RMSE and bias once results are known
- `prediction_evaluation.json`: compact prediction-accuracy history
- `scouting_observations.csv`: conversational copy of timestamped qualitative match observations
- `qualitative_signal_summary.json`: observation counts, adjustment limits and application status

Historical files under `data/history/` include one compact player market snapshot per day, a separate snapshot within eight hours of each deadline, prior-season records for players in the current FPL database, a normalised multi-season player-gameweek archive and historical position priors.

Pre-deadline projections are written under `data/predictions/gwNN/`. Each timestamped file is immutable, so later results cannot rewrite what the model genuinely predicted before a deadline.

Walk-forward evidence under `data/backtests/` includes detailed compressed predictions, gameweek metrics, model comparisons, held-out probability calibration and a compact success summary. Candidate calibration and component-model assessments are stored under `data/model/` but are not applied to live predictions until they clear explicit held-out promotion gates.

Latest source responses are also retained under `data/raw/latest/` for troubleshooting and future transformations.

Qualitative observations live under `data/scouting/` as an append-only JSONL journal. The raw note is retained alongside bounded signals for role, movement, fitness, minutes security, set pieces, team reliance and tactical fit. See [`docs/prediction_contract.md`](docs/prediction_contract.md) for the complete model contract.

## Automation

`.github/workflows/update-fpl-data.yml` performs the following:

1. Installs the Python dependency.
2. Runs the unit tests.
3. Collects current data from the public FPL API.
4. Validates the generated dataset structure and minimum row counts.
5. Commits updated datasets when running on the default branch.

Pull requests perform the complete collection and validation process without committing generated data.

`.github/workflows/sync-detailed-fpl-history.yml` runs daily and builds match-level history from each player's official FPL element summary. This preserves opponent, home/away status, price, ownership, transfers, minutes, underlying statistics and points separately for each fixture.

`.github/workflows/sync-historical-fpl.yml` runs weekly and imports completed seasons from the public [Vaastav FPL archive](https://github.com/vaastav/Fantasy-Premier-League). The import currently covers 2018/19 through 2024/25. The upstream `xP` field is deliberately excluded because it may contain post-match information and would create look-ahead bias.

`.github/workflows/build-fpl-model.yml` runs every six hours after refreshed inputs. It builds:

1. Rolling player and team features from match-level data.
2. Expected minutes from recent starts, minutes, availability, prior-season usage and historical position priors.
3. Deterministic player-level simulations covering appearances, attacking returns, clean sheets, saves, goals conceded, defensive contributions, discipline and bonus.
4. A separately auditable qualitative overlay with bounded, decaying adjustments.
5. FPL-points distributions and multi-gameweek totals over the next six gameweeks.
6. Immutable snapshots within eight hours of a deadline, followed by separate quantitative and qualitative accuracy evaluation when results arrive.

The current live model remains `player-sim-2.0`. Phase 12 adds `player-sim-3.0-candidate` in shadow mode with explicit appearance, minutes, attacking and FPL scoring components. It uses position-aware shrinkage and wider, correlated attacking-return distributions, while preserving the live model as an unchanged benchmark. See [`docs/component_model.md`](docs/component_model.md).

The initial held-out run improved MAE from 1.8250 to 1.7773 and marginally improved all three return-probability Brier scores. It reduced rank correlation from 0.4582 to 0.4422 and made RMSE 0.0021 worse, so the promotion gate correctly left it in shadow mode.

A development-selected hybrid now tests whether Version 2's ranking can be retained while borrowing Version 3's point and return-probability accuracy. Point and probability blend weights are fitted only on 2022/23-2023/24, frozen, then assessed on 2024/25. See [`docs/ensemble_model.md`](docs/ensemble_model.md).

`.github/workflows/backtest-fpl-model.yml` runs monthly and whenever the historical archive or model changes. It performs a gameweek-by-gameweek reconstruction using only prior information. Expected-points and probability calibration are fitted on 2022/23–2023/24 and assessed once on the held-out 2024/25 season.

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
python -m src.sync_detailed_history --output-dir data --max-workers 8
python -m src.sync_historical_fpl --output-dir data
python -m src.scouting_observations validate --path data/scouting/observations.jsonl
python -m src.build_fpl_model --data-dir data
python -m src.backtest_fpl_model --data-dir data
```

## Planned extensions

- Parquet historical archive and DuckDB analytical views
- Betting-market and team-strength features
- Confirmed team-news and workload features
- Calibrated model ensembles and uncertainty intervals
- Captaincy analysis
- Transfer recommendations
- Mini-league and rival analysis
