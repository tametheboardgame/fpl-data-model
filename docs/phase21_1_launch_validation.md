# Phase 21.1: Launch Validation and Hardening

## Purpose

Phase 21.1 validates the first live 2026/27 projections and prevents the launch optimiser from presenting a squad as ready when the player hierarchy, squad contract or operational report is unsafe.

## Root cause corrected

At Gameweek 1, current-season rolling history is empty. The control layer used previous-season minutes for established players, but its attacking rates and the component layer fell back to generic positional averages. This compressed premium-attacker projections and allowed defenders to dominate captaincy.

The launch model now:

- derives player-specific per-90 priors from the latest previous season;
- shrinks those rates towards the long-run positional prior;
- carries previous-season start, appearance and minutes evidence into both model components;
- fades previous-season minutes evidence over the first six current-season fixtures;
- records the evidence source, previous season and previous-season minutes on every projection.

Historical predictions and completed-season evaluation files are not rewritten.

## Validation gate

The initial-squad plan now validates:

- canonical player, club and position mappings;
- Gameweek 1 expected-points scale;
- premium-attacker projections relative to leading defenders;
- previous-season evidence coverage;
- ordering against a simple previous-season points-per-90 baseline;
- all three legal 2-5-5-3 squad strategies;
- legal starting formations, benches and club limits;
- captain and vice-captain membership and expected-points sanity;
- the opening multi-Gameweek transfer route.

Any high-severity failure changes the initial-squad plan to `review_required`, sets `readiness.ready` to `false` and prevents the operational report from reporting `ready`.

## Gameweek 1 operations

Before an FPL team is registered, the operational report now uses the validated initial-squad plan as its recommendation source. It reports the proposed 15-player squad, starting XI, bench, captain, vice-captain and opening route without treating the empty current-team response as an invalid lineup.

The system remains advisory only. It never creates a team, confirms a squad or performs an FPL action.

## Production outputs

- `data/chatgpt/initial_squad_plan.json`
- `data/chatgpt/launch_validation.json`
- `data/chatgpt/gameweek_report.json`
- `data/chatgpt/gameweek_report.md`
- `data/chatgpt/fpl_decisions.json`

## Readiness rule

Launch recommendations are usable only when `launch_validation.status` is `passed`, `launch_validation.usable_for_selection` is `true`, and the operational report has no high-severity warnings.
