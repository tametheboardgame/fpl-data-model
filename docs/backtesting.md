# Walk-forward backtesting methodology

## Question

Can the quantitative player-return model predict individual FPL points and useful FPL decisions better than simple, leakage-safe alternatives?

## Historical split and holdout history

The original component/ensemble development process used:

- development/calibration: 2022/23 and 2023/24;
- first held-out validation: 2024/25.

That process selected a 20% component expected-points blend and separate probability weights, and the hybrid passed the then-predeclared 2024/25 gate.

During the September 2026 review, the backtest control arm was corrected to reproduce live early-season control behaviour more faithfully, including previous-season usage information. The frozen architecture was then exposed once to a genuinely fresh 2025/26 holdout.

The frozen 20% blend improved MAE slightly (`1.9467 -> 1.9377`) but failed the predeclared standard because the gain was below 0.5% and both rank correlation (`0.4095 -> 0.4062`) and top-10 hit rate (`0.1528 -> 0.1472`) worsened. Production therefore returned to the `player-sim-2.0` control.

**The 2025/26 holdout is now closed. Do not tune new parameters or acceptance gates against it after exposure.**

Production activation is governed separately by `data/model/ensemble_production_policy.json`; a recurring development backtest cannot silently promote a candidate.

## Walk-forward reconstruction

For each target Gameweek, the backtester:

1. Uses player and team match data from earlier completed Gameweeks/fixtures only.
2. Reconstructs rolling player minutes, starts, xG, xA, saves, bonus, defensive contributions where season rules apply, and discipline.
3. Reconstructs team attacking and defensive context from earlier fixtures.
4. Supplies previous-season usage context where the corresponding live model would have had it, without target-season lookahead.
5. Reads only pre-match identity, opponent and venue information from the target fixture.
6. Simulates/predicts the player's FPL return.
7. Records the actual points only after prediction, then makes that target result available to later iterations.

A regression test changes the target Gameweek's goals, xG and points and verifies that its pre-Gameweek prediction remains unchanged.

## Evaluation universe

A player becomes eligible only from prior observable information. The current backtest requires enough prior fixture history for the relevant rolling features and never uses the eventual target minutes to decide whether a player was selectable.

Double-Gameweek fixtures are predicted independently and combined before player-Gameweek evaluation.

## Scoring-rule fidelity

Historical scoring is season-aware.

- Pre-2025/26 seasons do not receive defensive-contribution FPL points because those rules did not apply.
- 2025/26 and later historical rows may use defensive-contribution inputs and the applicable season scoring rules.
- 2026/27 live bonus-transition assumptions remain separate from earlier historical seasons.

No qualitative observations are backfilled. They did not exist with trustworthy pre-deadline timestamps and would introduce hindsight bias.

## Baselines and challengers

Typical comparisons include:

- running position average;
- running player season average;
- last-three average points;
- last-six average points;
- expected minutes multiplied by a fixed position scoring rate;
- `player-sim-2.0` control;
- shadow `player-sim-3.0-candidate` component simulator;
- explicitly frozen candidate blends or decision policies being evaluated.

A rejected/shadow challenger may still be measured, but it must not influence production selections unless production policy explicitly approves it.

## Core metrics

Player-prediction metrics include:

- MAE, RMSE and bias;
- mean Gameweek Spearman rank correlation;
- top-10 and top-25 overlap with actual leading scorers;
- captaincy regret against the hindsight-best eligible scorer;
- Brier scores and reliability bins for 6+, 10+ and 15+ returns;
- breakdowns by season, position, venue and relevant early-season subgroups.

For FPL-22C shared-captain validation, also measure at minimum:

- actual captain FPL points;
- mean captain regret versus best available squad captain;
- best-captain hit rate;
- 10+ and 15+ captain-haul rates;
- premium-attacker and high-ownership/high-ceiling cases;
- defensive-captain false positives;
- stability by season rather than pooled averages alone.

## Promotion discipline

Acceptance criteria must be declared before inspecting the final evaluation used for promotion.

Do not:

- weaken a gate after seeing a desired live-week result;
- tune for a named current player or fixture;
- reuse the closed 2025/26 holdout as a fresh test set;
- let strategic-selection bonuses contaminate mean expected-points accounting.

If genuinely fresh historical data are unavailable for a new captain/decision objective, prefer prospective 2026/27 evaluation over repeated post-hoc tuning on already-exposed seasons.

For current production governance and the active package sequence, read `PROJECT_STATE.md` and `ROADMAP.md`.
