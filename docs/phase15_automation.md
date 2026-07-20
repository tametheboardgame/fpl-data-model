# Phase 15: automated context and prospective evaluation

Phase 15 turns the provider-independent Phase 14 journal into an automated, auditable feed.

## Live provider

The initial adapter uses API-Football for Premier League injuries and confirmed line-ups. It runs every two hours with a hard budget of eight requests per run. It only requests line-ups for matched fixtures within three hours of kickoff.

Raw latest provider payloads are retained under `data/raw/external/api-football/latest/`. Normalised observations are appended to `data/context/signals.jsonl`; they never rewrite an earlier observation.

Repeated snapshots from the same source and target do not compound confidence. The live decision layer uses only the newest applicable snapshot, while all pre-kickoff snapshots remain available for evaluation.

## Honest evaluation

`external_context_accuracy.csv` scores probability signals with Brier score and expected minutes with absolute error. A signal is only evaluated when its `observed_at` timestamp is strictly before kickoff.

## Chip state

Manager chip usage is compared with a season-specific rules file. If the current season is not configured, remaining chip counts are deliberately reported as unknown instead of assuming last season's rules.

## Activation

Create an API-Football key and add it to the repository as an Actions secret named `API_FOOTBALL_KEY`. The scheduled workflow remains safely dormant until that secret exists.
