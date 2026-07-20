# Walk-forward backtesting methodology

## Question

Can the quantitative player-return model predict individual FPL points better than simple, leakage-safe alternatives?

## Time split

- Development and calibration: 2022/23 and 2023/24
- Untouched held-out evaluation: 2024/25

Expected-points regression and probability multipliers are fitted only on the development seasons. The held-out season is used once to decide whether the candidate calibration generalises.

Expected-points calibration is recommended only when its held-out MAE gain is both statistically positive across gameweeks at the 95% level and practically material, defined as at least a 0.5% relative reduction. This prevents negligible numerical movement from being promoted into the live model.

## Walk-forward reconstruction

For each gameweek, the backtester:

1. Uses player and team match data from earlier gameweeks only.
2. Reconstructs rolling player minutes, starts, xG, xA, saves, bonus and discipline.
3. Reconstructs team attacking and defensive context from earlier fixtures.
4. Reads only pre-match identity, opponent and venue information from the target fixture.
5. Simulates the player's FPL return.
6. Records the actual points, then makes that gameweek available to the next iteration.

A regression test changes the target gameweek's goals, xG and points and verifies that its pre-gameweek prediction remains unchanged.

## Evaluation universe

A player becomes eligible after at least three prior fixture rows and at least one appearance in their last three fixtures. This avoids using the eventual target minutes to decide who was selectable, but excludes the earliest gameweeks and immediate new signings.

Double-gameweek fixtures are predicted independently and combined before player-gameweek evaluation.

## Baselines

- running position average
- running player season average
- last-three average points
- last-six average points
- expected minutes multiplied by a fixed position scoring rate
- raw `player-sim-2.0`
- development-calibrated `player-sim-2.0`
- shadow `player-sim-3.0-candidate` component simulator

## Metrics

- MAE, RMSE and bias
- mean gameweek Spearman rank correlation
- top-10 and top-25 overlap with actual leading scorers
- captaincy regret against the hindsight-best eligible scorer
- Brier scores and reliability bins for 6+, 10+ and 15+ returns
- breakdowns by season, position and venue

## Important limitations

No qualitative observations are backfilled. They did not exist with trustworthy pre-deadline timestamps and would introduce hindsight bias. Historical scoring also excludes defensive-contribution points because those rules did not apply in the evaluation seasons.

Candidate calibration parameters remain separate from the live model until held-out evidence supports applying them. The Phase 12 component model is evaluated against the unchanged `player-sim-2.0` control and remains in shadow mode unless it passes every documented promotion gate.
