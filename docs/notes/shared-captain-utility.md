# Shared strategic captain utility

FPL-22B replaces the duplicated weekly and Wildcard captain objectives with one reusable utility in `src/fpl_captaincy.py`.

## Accounting boundary

The utility decides **who is doubled**. Its ceiling, ownership/rank and position terms are selection utilities only. Reported expected points continue to equal the selected XI's risk-adjusted mean expected points plus the selected captain's risk-adjusted mean expected points.

## Inputs

The shared score uses:

- risk-adjusted current-Gameweek mean expected points as the primary component;
- p90 gap, P(10+) and P(15+) as bounded ceiling evidence;
- bounded ownership pressure for rank exposure;
- a defensive uncertainty penalty plus a 1.5-point exception margin so a defender can captain only when the evidence materially dominates.

Expected minutes, availability confidence and the selection-risk penalty are recorded in the weekly audit. They already affect the risk-adjusted mean upstream and are not subtracted again inside captain utility.

## Reused coefficients

FPL-22B does not tune new strategic coefficients against the exposed 2025/26 holdout. It centralises the coefficients already used by the captaincy-aware Wildcard objective. FPL-22C is responsible for leakage-safe historical/prospective validation and promotion/rejection evidence.

## Wiring

The shared utility now drives:

- weekly current-Gameweek captain ranking;
- the first actionable Gameweek captain score map supplied to multi-Gameweek routing;
- Wildcard strategic captaincy;
- target-Gameweek Triple Captain selection;
- target-Gameweek Free Hit final squad/captain scoring.

Future-Gameweek route and chip captaincy may continue to use the simpler mean-based rule where equivalent decision-layer reliability inputs are unavailable.

Current utility version: `strategic-captain-1.0`.
