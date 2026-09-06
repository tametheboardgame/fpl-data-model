# Phase 14: external context and decision intelligence

## Purpose

The production forecast remains the numerical prediction baseline. Phase 14 adds a
separate, auditable decision layer for information that may arrive shortly before a
deadline and cannot safely be reconstructed after the event, including confirmed team
news, predicted line-ups, injuries, suspensions, bookmaker markets and set-piece roles.

Production-model authority is governed by `data/model/ensemble_production_policy.json`.
As of the current handoff, the live baseline is `player-sim-2.0`; the component challenger
is shadow-only after the independent holdout rejection.

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

External context does not silently rewrite the production forecast. The original expected
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
retain their separate bounded multiplier. Raw production-model outputs are never
overwritten.

This separation is deliberate. Once enough prospective signals and outcomes exist, the
external layer can be evaluated honestly and promoted into the simulator only if it
improves held-out/prospective performance.

## Decision logic

Line-up selection maximises a separate `selection_expected_points` score while enforcing
one goalkeeper and legal defender, midfielder and forward limits. The raw forecast is
retained, but selection is conservatively reduced where projected minutes conflict with
observed starts or official availability is uncertain.

Model-disagreement penalties are policy-gated: an active approved ensemble/challenger may
contribute disagreement risk, but a rejected/shadow-only challenger must not penalise
production selections.

Captaincy combines the robust selection basis with upside information such as 10+/15+
probabilities and the 90th-percentile return, with bounded position/uncertainty treatment.
`FPL-22B` in `ROADMAP.md` is the active package to consolidate the remaining duplicated
current-Gameweek captain objectives into one shared strategic utility.

Every selected XI also receives an opposing-player correlation analysis. A goalkeeper
or defender facing a selected opposing midfielder or forward is reported with a
point-scaled negative-correlation exposure based on clean-sheet value and attacking-return
probability. This does not reduce the balanced strategy's mean expected-points score.
The aggressive strategy may use a bounded exposure penalty so that it can prefer a
slightly lower-mean but higher-ceiling line-up where the trade-off is small.

Single-transfer candidates:

- replace a player with another player in the same FPL position
- use the current selling price plus bank balance
- respect the maximum of three players per Premier League club
- rank by expected-points gain over the planning horizon

Differentials are currently players at 10% ownership or below. Chip recommendations are
season-aware and remain subject to the same production-model and expected-points
accounting rules as normal weekly decisions.

## Captaincy accounting boundary

Strategic captain utility may decide which player is doubled, but it is not itself
expected points. The current actionable Gameweek report must expose the same captain used
by route scoring, and route/report xPts must equal mean player xPts plus the selected
captain's mean xPts.

PR #47 / FPL-22A enforced that invariant at the operations/route hand-off. FPL-22B will
unify the remaining captain-utility implementations.

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

For current production status and active work, read `PROJECT_STATE.md` and `ROADMAP.md`.
