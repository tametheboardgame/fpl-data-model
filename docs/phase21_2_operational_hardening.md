# Phase 21.2: Deadline-aware operational hardening

Phase 21.2 closes the remaining gap between the normal six-hour production cycle and a moving FPL deadline. It keeps the system advisory while making the final recommendation timely, safety-gated and less sensitive to speculative transfer noise.

## Deadline refresh schedule

`.github/workflows/deadline-fpl-refresh.yml` assesses the next official FPL deadline hourly. It dispatches the existing `Update FPL data` workflow once in each of these windows:

- between 24 and 23 hours before the deadline;
- between four and three hours before the deadline;
- during the final hour before the deadline.

The dispatched workflow retains the established sequence: collect official data, validate it, commit the refreshed datasets, then start the prediction-model workflow. Routine six-hour refreshes continue unchanged. A manual forced dispatch remains available.

## Advice safety gate

The operational report now exposes `operational_readiness` with:

- `advice_level`: provisional, firm, final or blocked;
- `firm_advice_allowed`: true only inside the final 24 hours when launch validation has passed and no high-severity operational issue exists;
- `blocking_reasons`: machine-readable reasons the operator must not issue firm advice;
- a mandatory late team-news review flag before any manual FPL action.

Inside the final four hours, official FPL data may be no more than two hours old. A missing Phase 19 snapshot inside the eight-hour freeze window is a high-severity failure and blocks firm advice. A failed deadline build therefore becomes visible as stale data, a missing snapshot, or both.

## Transfer stability

The six-Gameweek route now includes a 0.75-point decision-friction cost for each planned transfer and a further 1.5-point penalty for selling and then quickly rebuying a player, or reversing an earlier purchase. A route containing transfers must then beat holding by at least one full decision-adjusted expected point before it becomes the recommendation. These controls represent forecast uncertainty and the option value of retaining free transfers. They affect route selection but do not alter the separately reported raw expected points.

## Team configuration

The data workflow no longer repeats the team ID. It uses the single `DEFAULT_TEAM_ID` value in `src/update_fpl_data.py`, which is already set to the current 2026/27 team ID `39395` and can still be overridden by `FPL_TEAM_ID` when required.

No transfer, chip, line-up or captain action is performed automatically. The manager must review and apply every recommendation in FPL.
