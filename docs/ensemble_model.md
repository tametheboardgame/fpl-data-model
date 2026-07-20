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

## Held-out result and promotion

Development selected these frozen weights:

- expected points: 20% component model
- 6+ probability: 50% component model
- 10+ probability: 40% component model
- 15+ probability: 100% component model

On 12,937 held-out 2024/25 predictions, the hybrid produced:

| Metric | player-sim-2.0 | hybrid |
|---|---:|---:|
| MAE | 1.8250 | 1.8120 |
| RMSE | 2.6666 | 2.6620 |
| rank correlation | 0.4582 | 0.4575 |
| top-10 hit rate | 0.1543 | 0.1571 |
| captaincy regret | 9.2000 | 9.2000 |
| 6+ Brier | 0.10971 | 0.10917 |
| 10+ Brier | 0.02938 | 0.02934 |
| 15+ Brier | 0.00614 | 0.00613 |

Every promotion criterion passed. The frozen hybrid is therefore exposed as `player-ensemble-1.0` for live recommendations.

Every output retains the `player-sim-2.0` control and `player-sim-3.0-candidate` component values, so the ensemble can be inspected or reverted without losing either underlying forecast.
