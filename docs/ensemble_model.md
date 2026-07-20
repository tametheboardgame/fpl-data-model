# Development-selected hybrid model

## Purpose

The hybrid candidate combines the complementary strengths of the live `player-sim-2.0` control and the Phase 12 `player-sim-3.0-candidate` component simulator.

It does not use 2024/25 results to choose blend weights.

## Development-only selection

Expected-points weights are evaluated from 0.0 to 1.0 in increments of 0.1 on 2022/23 and 2023/24.

The selector:

1. Finds the best development-season gameweek rank correlation.
2. Retains weights within 0.002 of that best rank.
3. Selects the retained weight with the lowest MAE, followed by RMSE.

This makes ranking the protected objective while allowing the component model to improve point accuracy when it does not materially damage ordering.

The 6+, 10+ and 15+ probability weights are selected independently by the lowest development-season Brier score. This allows the hybrid to use a different mixture for ordinary returns and rare hauls.

After selection, all weights are frozen and evaluated on 2024/25.

## Promotion gate

Live promotion requires:

- held-out rank correlation within 0.002 of `player-sim-2.0`
- at least a 0.5% MAE improvement
- no RMSE regression
- no top-10 hit-rate regression
- no captaincy-regret regression
- at least two return-probability Brier scores no worse than the control

The fitted weights, every development trial and the held-out verdict are written to `data/model/ensemble_model_candidate.json`.

The ensemble remains shadow-only unless all criteria pass.
