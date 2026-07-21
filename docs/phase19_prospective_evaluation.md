# Phase 19: prospective decision evaluation

## Purpose

Phase 19 measures whether the live system improves real FPL decisions during 2026/27. It does not reconstruct recommendations after results are known.

Within eight hours of every deadline, the model writes an immutable decision snapshot under `data/prospective/gwNN/`. Evaluation uses the final pre-deadline snapshot and waits until the official event reports both `finished=true` and `data_checked=true`.

## Experiment arms

Every snapshot freezes six comparable strategies:

- `system_strategy`: the complete recommendation, including the first transfer-route move, captain and any current chip recommendation
- `full_context_selection`: full model, qualitative observations and all external context on the current squad
- `no_odds_selection`: the same selection process with bookmaker and Odds API signals removed
- `no_external_selection`: the model and qualitative observations without external context
- `quantitative_only_selection`: the untouched quantitative ensemble
- `ownership_baseline`: a legal XI and captain selected only by FPL ownership

The current manager's official Gameweek points are recorded alongside the experiment. They are a real-world benchmark rather than a perfectly controlled comparison because the manager may not follow the recommended transfers or chips.

## Outputs

- `data/chatgpt/prospective_index.json`: immutable snapshot index
- `data/chatgpt/prospective_evaluation.csv`: Gameweek-by-arm scoring detail
- `data/chatgpt/prospective_evaluation.json`: cumulative arm totals and paired comparisons

The paired comparisons isolate all-context value, Odds API value, qualitative-observation value, model value over ownership and complete-strategy value over ownership.

At least ten finalised Gameweeks are required before the report can label evidence positive, inconclusive or worthy of review. The evaluation reports evidence but never changes source weights automatically, preventing short noisy runs from silently altering production recommendations.

## Scoring rules

Starting XI points, captain multipliers, Bench Boost, Triple Captain and transfer hits are scored from official player Gameweek totals. The first-Gameweek points difference between recommended incoming and outgoing players is also retained as a short-term transfer diagnostic.

This is a prospective decision experiment, not a claim that one Gameweek proves a transfer or chip was correct. Multi-Gameweek route value and chip opportunity cost remain part of the optimiser's original objective.
