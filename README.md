# FPL Data Model

Personal Fantasy Premier League data collection and analysis platform.

## Purpose

This repository collects current and historical Fantasy Premier League data and prepares analysis-ready datasets for use with ChatGPT.

## Architecture

FPL APIs → GitHub Actions → Python processing → CSV and JSON datasets → ChatGPT

The automated workflows retrieve public FPL data, preserve historical and human observations, build leakage-safe rolling features and simulate player-level FPL returns for conversation and decision support. Team results are context; individual FPL points are the prediction target.

## Current personal team

- FPL team ID: `39395`
- The ID belongs to the 2026/27 season.
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
- `prediction_evaluation.json`: compact prediction-accuracy history, including a separate submitted-XI audit so whole-player-pool MAE cannot conceal poor manager-facing selections
- `scouting_observations.csv`: conversational copy of timestamped qualitative match observations
- `qualitative_signal_summary.json`: observation counts, adjustment limits and application status
- `external_context_signals.csv`: validated team-news, market and role signals with source provenance
- `external_context_summary.json`: freshness, reliability and active-signal summary
- `external_context_accuracy.csv`: leakage-safe Brier scores and minutes errors for pre-kickoff context signals
- `external_context_evaluation.json`: compact prospective context-evaluation summary by source and signal type
- `fpl_decisions.json`: recommended line-up, captaincy, multi-Gameweek transfer routes, differentials and opportunity-costed chip schedule
- `initial_squad_plan.json`: launch-readiness checks and, only after the 2026/27 data gate passes, legal balanced, aggressive and ownership-protected opening-squad structures

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
6. Freshness-weighted external context and squad-specific line-up, captaincy, transfer, differential and chip decision support.
7. Immutable snapshots within eight hours of a deadline, followed by separate quantitative and qualitative accuracy evaluation when results arrive.

The original control model remains `player-sim-2.0`. Phase 12 adds `player-sim-3.0-candidate` in shadow mode with explicit appearance, minutes, attacking and FPL scoring components. It uses position-aware shrinkage and wider, correlated attacking-return distributions, while preserving the live model as an unchanged benchmark. See [`docs/component_model.md`](docs/component_model.md).

The initial held-out run improved MAE from 1.8250 to 1.7773 and marginally improved all three return-probability Brier scores. It reduced rank correlation from 0.4582 to 0.4422 and made RMSE 0.0021 worse, so the promotion gate correctly left it in shadow mode.

The development-selected hybrid passed every held-out gate and is now the live recommendation surface as `player-ensemble-1.0`. It uses 20% component weight for expected points, 50% for 6+, 40% for 10+ and 100% for 15+. The unchanged Version 2 control and Version 3 component outputs remain beside each recommendation for audit. See [`docs/ensemble_model.md`](docs/ensemble_model.md).

Phase 14 adds a provider-independent external-context journal, explicit source reliability and freshness decay, plus squad-specific decision support. External signals remain separately attributable and do not silently overwrite the validated ensemble. See [`docs/external_context_and_decisions.md`](docs/external_context_and_decisions.md).

Phase 15 adds an API-Football adapter for injuries and confirmed line-ups, a quota-bounded two-hourly sync, newest-snapshot resolution, leakage-safe prospective scoring and explicit season-aware chip state. See [`docs/phase15_automation.md`](docs/phase15_automation.md).

Phase 16 makes scoring, Bonus Points System transition assumptions, half-season chips, free-transfer balances, transfer hits and score finality season-aware. See [`docs/2026_27_rules_compatibility.md`](docs/2026_27_rules_compatibility.md).

Phase 17 adds a six-Gameweek beam-search optimiser for legal squad and transfer routes. It carries bank, selling prices, free transfers, hits, club limits, formations and captaincy between Gameweeks, and compares each route with holding the current squad. See [`docs/multi_gameweek_optimisation.md`](docs/multi_gameweek_optimisation.md).

Phase 18 adds budget-legal Blank and Double Gameweek optimisation for Wildcard, Free Hit, Bench Boost and Triple Captain. It compares every use with no-chip transfer routes, accounts for half-season expiry and saving opportunity cost, and enforces one chip per Gameweek. See [`docs/phase18_chip_optimisation.md`](docs/phase18_chip_optimisation.md).

Phase 19 adds immutable pre-deadline strategy snapshots and prospective comparison arms for the full system, no-odds, no-external-context, quantitative-only and ownership baselines. See [`docs/phase19_prospective_evaluation.md`](docs/phase19_prospective_evaluation.md).

Phase 20 adds a strict 2026/27 launch gate and budget-legal initial-squad optimisation across balanced, aggressive and ownership-protected structures. It emits no player recommendations while the official API still serves the closed season. See [`docs/phase20_initial_squad_readiness.md`](docs/phase20_initial_squad_readiness.md).

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
python -m src.update_fpl_data --team-id 39395 --output-dir data
python -m src.validate_fpl_data --data-dir data
python -m src.sync_detailed_history --output-dir data --max-workers 8
python -m src.sync_historical_fpl --output-dir data
python -m src.scouting_observations validate --path data/scouting/observations.jsonl
python -m src.external_context validate --signals data/context/signals.jsonl --sources data/context/sources.json
python -m src.build_fpl_model --data-dir data
python -m src.finalise_external_context --data-dir data
python -m src.backtest_fpl_model --data-dir data
```

## Planned extensions

- Parquet historical archive and DuckDB analytical views
- Bookmaker-market normalisation and a second independent team-news source
- Prospective promotion gates for external-context features after sufficient samples exist
- Mini-league and rival analysis
