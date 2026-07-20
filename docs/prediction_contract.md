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
- model, scoring-rules and simulation versions

## FPL return simulation

`player-sim-2.0` uses deterministic Monte Carlo samples. The scoring implementation covers:

- appearance and 60-minute points
- position-specific goal points and three points per assist
- position-specific clean-sheet points
- goalkeeper saves and penalty saves
- deductions for goals conceded by goalkeepers and defenders
- bonus points
- yellow cards, red cards, own goals and missed penalties
- 2025/26 defensive-contribution thresholds

The simulation is seeded by model version, fixture and player. Unchanged inputs therefore produce unchanged distributions.

## Qualitative overlay

The quantitative forecast is always retained. Qualitative notes can modify expected minutes and attacking involvement only through bounded, decaying signals. Raw notes, timestamps, confidence, expiry and observation IDs remain available for audit.

Qualitative performance is evaluated against the untouched quantitative prediction after results arrive. Historical qualitative backfilling is prohibited because it would introduce hindsight bias.

## Interpretation

Expected points is the average across plausible returns. The percentile range describes uncertainty, while the 10+ and 15+ probabilities describe upside relevant to captaincy and differential decisions. A high team win probability is neither required nor sufficient for a high individual FPL projection.
