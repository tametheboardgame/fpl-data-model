# Phase 18: Blank and Double Gameweek chip optimisation

Phase 18 places the four FPL chips inside the six-Gameweek decision horizon created in Phase 17. It compares chip use with the same no-chip transfer routes and produces both a target-Gameweek decision and a provisional schedule for the known horizon.

## Fixture structure

Fixture-level player projections are grouped by team and Gameweek. A team with no fixture is marked blank and a team with more than one fixture is marked double. The decision output records every affected team rather than treating all unusual Gameweeks as equally valuable.

## Chip valuation

- Triple Captain adds one further copy of the optimal captain's expected points.
- Bench Boost adds the expected points of the four players outside the optimal legal starting XI.
- Free Hit searches for a temporary budget-legal 15-player squad, including positional limits and the three-player-per-club rule. The squad is explicitly marked as reverting after the Gameweek.
- Wildcard searches for a permanent budget-legal squad using discounted expected points over the remaining known horizon. It is held when the proposed rebuild changes fewer than four players.

Every candidate records its incremental expected points over the corresponding no-chip route, its discounted value, Gameweek structure, squad or player details, and the reason to play, hold or reject it.

## Opportunity cost and expiry

The optimiser keeps minimum save thresholds while the active half-season extends beyond the six-Gameweek horizon. This prevents a modest current opportunity from consuming a chip that may be materially stronger in a later Blank or Double Gameweek.

When the known horizon reaches the active chip-set expiry, the save threshold is removed, although Free Hit, Bench Boost and Triple Captain still require relevant Blank or Double Gameweek structure. The schedule uses each available chip at most once and enforces the FPL rule that only one chip can be played in a Gameweek.

The current recommendation is `play` only when the target Gameweek appears in the optimal schedule. Otherwise it is an explicit `hold`, with the next provisional use attached when one is visible.

## Boundaries

- Prices remain constant across the known horizon.
- Optimisation uses expected points, so later forecasts are discounted for uncertainty.
- The provisional schedule is rebuilt whenever fixture projections, the squad, transfer state or chip state changes.
- No chip recommendation is fabricated before Phase 17 has valid future-fixture routes.
