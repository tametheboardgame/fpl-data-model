# Player-level FPL prediction contract

## Objective

The prediction target is an individual player's FPL return, not the match result. Team attack, defence and fixture strength are contextual inputs used to estimate the opportunities available to each player.

The model forecasts no more than the next six Gameweeks and treats separate fixtures in a double Gameweek independently before combining them at player-horizon level.

The manager-facing strategic objective is to maximise the chance of winning mini-leagues while keeping all reported expected-points accounting honest. Bounded ceiling, haul and rank-exposure terms may change a strategic choice, but they are never added to mean expected points.

## Fixture-level outputs

Every player-fixture projection includes:

- appearance, starting and availability probabilities;
- quantitative expected minutes and any qualitative minutes adjustment;
- expected minutes plus the 10th, 50th and 90th percentiles;
- expected goals, assists and clean-sheet probability;
- quantitative expected FPL points;
- separately identified qualitative expected-points adjustment;
- final expected FPL points;
- 10th, 50th and 90th FPL-points percentiles;
- probabilities of 6+, 10+ and 15+ points and of scoring 3 or fewer;
- qualitative observation IDs and bounded signals used;
- live control, challenger, production-policy, scoring-rules and simulation versions;
- the production weights actually permitted by policy.

## Live prediction model and challenger governance

The current production recommendation model is the `player-sim-2.0` control.

`player-sim-3.0-candidate` remains an auditable shadow challenger. A previously selected ensemble blend was independently rejected on the frozen 2025/26 holdout because rank correlation and top-10 hit rate worsened despite a small MAE improvement.

`data/model/ensemble_production_policy.json` is authoritative. While its status is `holdout_rejected`:

- expected-points component weight is `0.0`;
- 6+, 10+ and 15+ component probability weights are `0.0`;
- the challenger may be logged for shadow research only;
- challenger disagreement must not penalise production selections.

Recurring backtests may generate a development candidate, but they cannot silently re-promote it. Reconsideration requires prospective 2026/27 evidence plus explicit production approval.

Both underlying models use deterministic Monte Carlo samples. The scoring implementation covers:

- appearance and 60-minute points;
- position-specific goal points and three points per assist;
- position-specific clean-sheet points;
- goalkeeper saves and penalty saves;
- deductions for goals conceded by goalkeepers and defenders;
- defensive-contribution scoring under the applicable season rules;
- bonus points;
- yellow cards, red cards, own goals and missed penalties.

The simulations are seeded by model version, fixture and player. Unchanged inputs therefore produce unchanged distributions.

## History finality and usage

Live rolling features must use only genuinely completed player fixtures. A row exposed by the FPL element-summary API for the current Gameweek is not evidence of a completed appearance merely because the deadline has passed or the Gameweek has opened.

Completed history is keyed to official fixture finality. Appearance/start/minutes denominators use actual completed player fixtures, not `target_gameweek - 1`.

This protects early-season role estimates from unfinished zero/partial rows and prevents current-GW data leakage into pre-match form.

## Qualitative overlay

The quantitative forecast is always retained. Qualitative notes can modify expected minutes and attacking involvement only through bounded, decaying signals. Raw notes, timestamps, confidence, expiry and observation IDs remain available for audit.

Qualitative performance is evaluated against the untouched quantitative prediction after results arrive. Historical qualitative backfilling is prohibited because it would introduce hindsight bias.

## External context and decision layer

Timestamped availability, line-up, expected-minutes, market, clean-sheet, penalty and set-piece signals may be accepted from registered sources. Each signal is weighted by declared source reliability, confidence and freshness.

The production model forecast is retained as `model_expected_points`. High-value availability, minutes and starting-role signals may produce a bounded `decision_expected_points` value, with every signal ID, source ID and reason attached. This decision value is not treated as a promoted simulator feature until prospective evidence demonstrates improvement.

The squad-specific decision contract includes:

- a legal recommended starting XI and bench order;
- captain and vice-captain choices;
- affordable transfer routes evaluated over the planning horizon;
- differentials and bounded rank-exposure context;
- season-aware chip recommendations and opportunity cost;
- explicit operational readiness and warning state.

## Captaincy accounting invariant

Captaincy may use a strategic utility that considers mean xPts, ceiling/p90, haul probabilities, expected minutes/availability and bounded ownership/rank exposure.

That utility selects **which player is doubled**. It is not itself expected points.

For any current actionable Gameweek report:

- the exposed captain must be the same captain used by the route/report scoring calculation;
- reported lineup xPts equal the sum of mean player xPts plus the selected captain's mean xPts;
- strategic captain bonuses must remain separate audit fields and must never inflate displayed xPts.

The roadmap phase `FPL-22B` will consolidate the remaining duplicated current-GW captain utilities into one shared implementation. Until that phase is validated, current code must preserve the same accounting invariant even where selection logic differs internally.

## Interpretation

Expected points is the average across plausible returns. The percentile range describes uncertainty, while 10+ and 15+ probabilities describe upside relevant to captaincy and differential decisions. A high team win probability is neither required nor sufficient for a high individual FPL projection.

For fresh-chat project state and the active development sequence, read `PROJECT_STATE.md` and `ROADMAP.md`.
