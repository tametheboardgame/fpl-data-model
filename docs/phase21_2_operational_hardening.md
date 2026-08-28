# Phase 21.2: Deadline-aware operational hardening

Phase 21.2 closes the remaining gap between the normal six-hour production cycle and a moving FPL deadline. It keeps the system advisory while making the final recommendation timely, safety-gated and less sensitive to speculative transfer noise.

## Deadline refresh schedule

`.github/workflows/deadline-fpl-refresh.yml` assesses the next official FPL deadline four times an hour. It treats the refresh times as persistent checkpoints rather than one-hour trigger bands:

- 24 hours before the deadline;
- eight hours before the deadline, when the immutable freeze snapshot becomes mandatory;
- four hours before the deadline;
- one hour before the deadline.

Each checkpoint remains due until both the official FPL data and the model report are demonstrably newer than the checkpoint. Inside eight hours, the report must also contain the immutable snapshot. A delayed GitHub schedule therefore catches up on its next run instead of permanently missing a narrow trigger band. Completed checkpoints are idempotent, and a 20-minute grace period lets an already-dispatched model build finish before the scheduler retries a stale build or missing snapshot.

The dispatched workflow retains the established sequence: collect official data, validate it, commit the refreshed datasets, then start the prediction-model workflow. Routine six-hour refreshes continue unchanged. A manual forced dispatch remains available.

## Advice safety gate

The operational report now exposes `operational_readiness` with:

- `advice_level`: provisional, firm, final or blocked;
- `firm_advice_allowed`: true only inside the final 24 hours when the applicable weekly validation has passed and no high-severity operational issue exists;
- `blocking_reasons`: machine-readable reasons the operator must not issue firm advice;
- a mandatory late team-news review flag before any manual FPL action.

Inside the final four hours, official FPL data may be no more than two hours old. A missing Phase 19 snapshot inside the eight-hour freeze window is a high-severity failure and blocks firm advice. A failed deadline build therefore becomes visible as stale data, a missing snapshot, or both.

## Transfer stability

The six-Gameweek route now includes a 1.25-point decision-friction cost for each planned transfer and a further 1.5-point penalty for selling and then quickly rebuying a player, or reversing an earlier purchase. A route containing transfers must beat holding by at least four decision-adjusted expected points and lead the best alternative incoming target by at least 1.5 points. If either condition fails, the model explicitly recommends holding. These controls represent forecast uncertainty and the option value of retaining free transfers. They affect route selection but do not alter the separately reported raw expected points.

Gameweek 1 uses the launch validation contract. From Gameweek 2 onward, readiness validates the registered 15-player squad, legal XI and bench, captaincy pair, ready multi-Gameweek route and transfer robustness directly; the expired launch-only gate is no longer reused.

## Team configuration

The data workflow no longer repeats the team ID. It uses the single `DEFAULT_TEAM_ID` value in `src/update_fpl_data.py`, which is already set to the current 2026/27 team ID `39395` and can still be overridden by `FPL_TEAM_ID` when required.

No transfer, chip, line-up or captain action is performed automatically. The manager must review and apply every recommendation in FPL.
