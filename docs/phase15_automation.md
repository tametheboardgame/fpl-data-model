# Phase 15: automated context and prospective evaluation

Phase 15 turns the provider-independent Phase 14 journal into an automated, auditable feed.

## Live providers

The initial adapter uses API-Football for Premier League injuries and confirmed line-ups. The provider is currently marked `plan_blocked` because its free account cannot access the current season. Scheduled retries are disabled, but the adapter remains available for manual testing or a future plan change.

The live market adapter uses The Odds API for UK `h2h` and `totals` markets. It runs every six hours and makes at most one request costing no more than two credits. With four scheduled runs per day, the maximum expected usage is 240 credits in a 30-day month, leaving at least 260 of the free plan's 500 credits for manual tests and contingencies.

Bookmaker margins are removed within each market before probabilities are aggregated. The adapter fits independent team goal rates to the no-vig win/draw/loss consensus and the bookmaker goal total where available. It emits team win, team scoring, clean-sheet and expected-goal signals. If no totals market is returned, it uses an explicit 2.85-goal league prior rather than pretending totals data existed.

Raw latest provider payloads are retained under `data/raw/external/api-football/latest/` and `data/raw/external/odds-api/latest/`. Normalised observations are appended to `data/context/signals.jsonl`; they never rewrite an earlier observation.

Repeated snapshots from the same source and target do not compound confidence. The live decision layer uses only the newest applicable snapshot, while all pre-kickoff snapshots remain available for evaluation.

## Honest evaluation

`external_context_accuracy.csv` scores player and team probability signals with Brier score. Expected minutes and team expected goals use absolute error. A signal is only evaluated when its `observed_at` timestamp is strictly before kickoff.

## Chip state

Manager chip usage is compared with a season-specific rules file. If the current season is not configured, remaining chip counts are deliberately reported as unknown instead of assuming last season's rules.

## Activation

Add The Odds API key as an Actions secret named `ODDS_API_KEY`. Manual workflow runs force one provider check even when FPL has not published future fixtures. Scheduled runs do not use quota until future FPL fixtures exist.
