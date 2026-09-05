# Ensemble challenger and production policy

## Purpose

The ensemble work combines the unchanged `player-sim-2.0` control with the auditable `player-sim-3.0-candidate` component simulator. The component remains useful as a research/shadow challenger, but it is **not currently authorised to influence production recommendations**.

The live authority is `data/model/ensemble_production_policy.json`, not the latest development backtest candidate file.

## Development selection history

Expected-points weights were evaluated from 0.0 to 1.0 in increments of 0.1 on 2022/23 and 2023/24. The selector:

1. found the best development-season gameweek rank correlation;
2. retained weights within 0.002 of that best rank;
3. selected the retained weight with the lowest MAE, followed by RMSE.

The 6+, 10+ and 15+ probability weights were selected independently by development-season Brier score.

That process selected:

- expected points: 20% component model;
- 6+ probability: 50% component model;
- 10+ probability: 40% component model;
- 15+ probability: 100% component model.

On the original 2024/25 held-out evaluation, the hybrid passed the then-predeclared gate:

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

That historical result explains why the ensemble was temporarily exposed as the live recommendation surface.

## Independent 2025/26 holdout rejection

A later frozen 2025/26 holdout was used as an independent test after the backtest/control harness had been made more faithful to production. The architecture and weights were frozen before exposing that season.

The 20% blend produced approximately:

| Metric | control | frozen blend |
|---|---:|---:|
| MAE | 1.9467 | 1.9377 |
| rank correlation | 0.4095 | 0.4062 |
| top-10 hit rate | 0.1528 | 0.1472 |

RMSE, return-probability Brier scores and captaincy regret improved, but the predeclared promotion standard was not met: the MAE gain was below the required 0.5%, while rank correlation and top-10 hit rate both worsened. For the project objective of winning mini-leagues, the top-end/ranking regression is material.

The frozen 2025/26 holdout is now closed. Do not tune new parameters against it after exposure.

## Current production policy

Production is governed by `data/model/ensemble_production_policy.json` and currently states:

- status: `holdout_rejected`;
- live model: `player-sim-2.0`;
- live component point weight: `0.0`;
- live component 6+/10+/15+ probability weights: `0.0`;
- challenger mode: `shadow_only`.

PR #45 separated recurring development evaluation from production approval. A monthly/automatic backtest may regenerate `data/model/ensemble_model_candidate.json`, but that file cannot activate a challenger while the production policy remains rejected.

Future reconsideration requires both:

1. sufficient prospective 2026/27 evidence; and
2. an explicit production-policy change to approve the challenger.

Malformed or missing approval information must fail closed rather than silently activating candidate weights.

## Shadow outputs

The control and component forecasts remain available side by side for diagnosis and research. A rejected challenger must not:

- alter live expected points or return probabilities;
- create model-disagreement penalties in decision support;
- influence captaincy, transfers, XI or chip selection;
- be described as the live model in reporting.

See `PROJECT_STATE.md` and `ROADMAP.md` for the current work plan.
