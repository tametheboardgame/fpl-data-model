# Phase 12 component player model

## Purpose

Phase 12 tests whether a position-aware, component-level simulator improves player selection and explosive-return probabilities over the frozen `player-sim-2.0` control.

The challenger remains separate as `player-sim-3.0-candidate` until leakage-safe held-out evidence supports promotion.

## Prediction structure

The challenger predicts and simulates:

- appearance, start and 60-minute probabilities
- starter and substitute minutes separately
- goals and assists with position-specific shrinkage
- clean sheets and goals-conceded deductions
- goalkeeper saves and penalty saves
- defensive-contribution points
- bonus and disciplinary events
- complete 6+, 10+ and 15+ return probabilities

Each expected-points prediction is decomposed into:

- appearance points
- goal points
- assist points
- clean-sheet points
- goals-conceded points
- save points
- penalty-save points
- defensive-contribution points
- bonus points
- discipline points

The components sum to the challenger expected-points prediction, making every projection auditable.

## Minutes model

Recent appearance and start rates are Beta-smoothed towards historical positional priors. Starter minutes and substitute minutes are estimated separately and shrunk towards position-specific priors.

This avoids treating a player with repeated 20-minute substitute appearances like an uncertain 60-minute starter.

## Attacking-return model

Recent xG and xA are blended over six and ten fixtures, then shrunk by observed minutes towards position priors.

Goals and assists share a mean-preserving Gamma attack state before their Poisson event draws. This creates correlated, overdispersed attacking returns while preserving the underlying expected event rates. Forwards receive the widest distribution, followed by midfielders, defenders and goalkeepers.

Bonus remains based on the player's historical rate but is conditionally weighted towards simulations containing goals, assists, clean sheets or goalkeeper saves.

## Promotion gate

The candidate is tested against the unchanged `player-sim-2.0` control on held-out 2024/25 predictions.

Live promotion requires all of the following:

1. Better mean gameweek rank correlation.
2. Better RMSE.
3. MAE no more than 0.5% worse than the control.
4. Better Brier scores for at least two of 6+, 10+ and 15+ returns.

The result is written to `data/model/component_model_candidate.json`. A failed gate leaves the existing live model untouched.

## Known limitations

- Historical qualitative observations do not exist with trustworthy pre-deadline timestamps.
- The candidate does not yet include bookmaker probabilities or confirmed line-ups.
- Bonus is still an approximation rather than a complete BPS event model.
- The attack-state distribution is position-specific, not yet player-archetype-specific.
- New signings and early-season players remain dependent on positional priors.
