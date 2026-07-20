# Player-level FPL prediction contract

## Objective

The prediction target is an individual player's FPL return, not the match result. Team attack, defence and fixture strength are contextual inputs used to estimate the opportunities available to each player.

The model forecasts no more than the next six gameweeks and treats separate fixtures in a double gameweek independently before combining them at player-horizon level.

## Fixture-level outputs

Every player-fixture projection includes:

- appearance, starting and availability probabilities
- quantitative expected minutes and any qualitative minutes adjustment
- expected minutes plus the 10th, 50th and 90th percentiles
- expected goals, assists and clean-sheet probability
- quantitative expected FPL points
- separately identified qualitative expected-points adjustment
- final expected FPL points
- 10th, 50th and 90th FPL-points percentiles
- probabilities of 6+, 10+ and 15+ points and of scoring 3 or fewer
- the qualitative observation IDs and bounded signals used
- live ensemble, control, component, scoring-rules and simulation versions
- the frozen ensemble weights applied to expected points and return probabilities

## FPL return simulation

The live recommendation model is `player-ensemble-1.0`. It blends the unchanged `player-sim-2.0` control with the auditable `player-sim-3.0-candidate` component simulator using weights selected only on 2022/23-2023/24 and validated on 2024/25.

The control and component forecasts remain separate in every output. The ensemble uses 20% component weight for expected points, 50% for 6+ probability, 40% for 10+ probability and 100% for 15+ probability.

Both underlying models use deterministic Monte Carlo samples. The scoring implementation covers:

- appearance and 60-minute points
- position-specific goal points and three points per assist
- position-specific clean-sheet points
- goalkeeper saves and penalty saves
- deductions for goals conceded by goalkeepers and defenders
- bonus points
- yellow cards, red cards, own goals and missed penalties
- 2025/26 defensive-contribution thresholds

The simulations are seeded by model version, fixture and player. Unchanged inputs therefore produce unchanged distributions. The ensemble is a deterministic combination of those distributions.

## Qualitative overlay

The quantitative forecast is always retained. Qualitative notes can modify expected minutes and attacking involvement only through bounded, decaying signals. Raw notes, timestamps, confidence, expiry and observation IDs remain available for audit.

Qualitative performance is evaluated against the untouched quantitative prediction after results arrive. Historical qualitative backfilling is prohibited because it would introduce hindsight bias.

## External context and decision layer

Phase 14 accepts timestamped availability, line-up, expected-minutes, market, clean-sheet, penalty and set-piece signals from a registered source. Each signal is weighted by declared source reliability, signal confidence and freshness.

The validated ensemble forecast is retained as `model_expected_points`. High-value availability, minutes and starting-role signals may produce a bounded `decision_expected_points` value, with every signal ID, source ID and reason attached. This decision value is not treated as a promoted simulator feature until prospective evidence demonstrates improvement.

The squad-specific decision contract includes:

- a legal recommended starting XI and bench order
- captain and vice-captain choices, using expected points first and haul probability as a tie-breaker
- affordable same-position transfer pairs ranked by three-gameweek expected-points gain
- differentials at 10% ownership or lower
- advisory chip indicators that explicitly acknowledge missing chip-state or blank/double-gameweek information

## Interpretation

Expected points is the average across plausible returns. The percentile range describes uncertainty, while the 10+ and 15+ probabilities describe upside relevant to captaincy and differential decisions. A high team win probability is neither required nor sufficient for a high individual FPL projection.
