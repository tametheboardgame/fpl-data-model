# Phase 14: external context and decision intelligence

## Purpose

The validated ensemble remains the numerical prediction baseline. Phase 14 adds a
separate, auditable decision layer for information that may arrive shortly before a
deadline and cannot safely be reconstructed after the event, including confirmed team
news, predicted line-ups, injuries, suspensions, bookmaker markets and set-piece roles.

The decision layer produces practical FPL outputs for the manager's actual squad:

- recommended starting XI and bench order
- captain and vice-captain shortlist
- affordable same-position transfer pairs, respecting the three-player club limit
- low-ownership differentials
- provisional bench boost, triple captain and wildcard indicators

## Source registry

`data/context/sources.json` records each accepted source and two explicit judgements:

- reliability, from 0 to 1
- freshness half-life in hours

The initial registry supports confirmed line-ups, official club updates, aggregated
bookmaker markets, predicted line-ups, trusted reporters and manually verified inputs.
Provider-specific collectors can be added without changing the model contract.

## Append-only signal journal

Signals are stored in `data/context/signals.jsonl`. Every signal requires:

- a stable signal ID and observation timestamp
- a registered source
- a supported signal type and bounded value
- at least one target: player, team, fixture or gameweek
- confidence, optional validity dates, status, source URL and note

Supported signal types are availability probability, start probability, expected
minutes, anytime goal probability, clean-sheet probability, attack multiplier,
penalty-taker probability and set-piece share.

Signals decay according to source reliability, confidence and age. Expired, future,
inactive and mismatched signals never enter a decision. The journal is validated before
every production build.

## Prediction boundary

External context does not silently rewrite `player-ensemble-1.0`. The original expected
points are retained as `model_expected_points`; a bounded context adjustment produces
`decision_expected_points` only for the decision surface. Signal IDs, source IDs and
human-readable reasons are attached to the affected player.

Bookmaker team expected goals and clean-sheet probabilities adjust only the components
they can support:

- team expected goals scale projected goal and assist points
- clean-sheet probabilities scale clean-sheet points for goalkeepers, defenders and midfielders
- goalkeeper and defender goals-conceded deductions are recalculated from the blended market rate

The market value is blended 75% towards the source-weighted signal and bounded before
use. Availability, expected-minutes, starting-probability and attacking-role signals
retain their separate bounded multiplier. Raw ensemble outputs are never overwritten.

This separation is deliberate. Once enough prospective signals and outcomes exist, the
external layer can be evaluated honestly and promoted into the simulator only if it
improves held-out performance.

## Decision logic

Line-up selection maximises next-gameweek decision expected points while enforcing one
goalkeeper and legal defender, midfielder and forward limits. Captaincy uses expected
FPL points first, with 10+ probability and the 90th-percentile return as tie-breakers.

Every selected XI also receives an opposing-player correlation analysis. A goalkeeper
or defender facing a selected opposing midfielder or forward is reported with a
point-scaled negative-correlation exposure based on clean-sheet value and attacking-return
probability. This does not reduce the balanced strategy's mean expected-points score.
The aggressive initial-squad strategy applies a bounded exposure penalty so that it can
prefer a slightly lower-mean but higher-ceiling line-up where the trade-off is small.

Single-transfer candidates:

- replace a player with another player in the same FPL position
- use the current selling price plus bank balance
- respect the maximum of three players per Premier League club
- rank by expected-points gain over the next three gameweeks

Differentials are currently players at 10% ownership or below. Chip outputs are indicators
rather than automatic instructions because confirmed blank/double gameweeks and the
manager's remaining-chip state are required for a final chip recommendation.

## Generated outputs

- `data/chatgpt/external_context_signals.csv`: conversational copy of the journal
- `data/chatgpt/external_context_summary.json`: source, freshness and activity summary
- `data/chatgpt/fpl_decisions.json`: line-up, captaincy, transfer, differential and chip support

When no future FPL fixtures exist, the decision file is still generated with status
`waiting_for_future_fixtures` and empty recommendations.

## Adding a signal

Append one JSON object per line, for example:

```json
{"signal_id":"lineup-gw01-10","observed_at":"2026-08-15T13:00:00Z","source_id":"confirmed_lineup","signal_type":"start_probability","value":1.0,"confidence":1.0,"player_id":10,"fixture_id":100,"gameweek":1,"expires_at":"2026-08-15T18:00:00Z","status":"active","source_url":"https://example.com/lineup"}
```

Validate locally with:

```bash
python -m src.external_context validate --signals data/context/signals.jsonl --sources data/context/sources.json
```
