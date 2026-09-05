# Repository agent instructions

These instructions apply to the whole repository.

## Before doing development work

Always read, in this order:

1. `PROJECT_STATE.md`
2. `ROADMAP.md`
3. `data/model/ensemble_production_policy.json`
4. any detailed design document relevant to the requested phase

Then check live GitHub state (current `main`, open PRs and CI) before acting. Repository state can change after these handoff documents are written.

## Fresh-chat start commands

- `Start FPL-NEXT` means: continue the first incomplete item in `ROADMAP.md`.
- `Start FPL-22A`, `Start FPL-22B`, etc. means: execute that named phase after satisfying prerequisites.

If the requested phase is already complete, do not repeat it. Record the current state and continue to the next required incomplete phase.

After material progress, update both `PROJECT_STATE.md` and `ROADMAP.md` so a future chat can resume without conversation history.

## Permanent engineering rules

- Optimise for winning FPL mini-leagues with sensible upside/variance, not only median error.
- Never hard-code a current player, club or player ID as a model fix.
- Never weaken a validation gate after seeing a preferred live-week outcome.
- Never leak post-match or unfinished-current-fixture information into pre-deadline forecasts.
- Only genuinely completed fixtures may count as completed usage/form evidence.
- `data/model/ensemble_production_policy.json` is authoritative for live model activation.
- A rejected or shadow challenger must not influence production selections, expected points or disagreement penalties.
- Strategic captain/ceiling/rank utilities may change selections but must never be added to displayed mean expected points.
- The captain shown to the user must be the captain whose mean return is doubled in route/report xPts.
- Keep model changes auditable, deterministic where intended, tested and reversible.
- FPL actions remain advisory; do not automatically make transfers, set a lineup, change captaincy or play a chip.

## Current project identifiers

- repository: `tametheboardgame/fpl-data-model`
- FPL team ID: `39395`
- season: `2026/27`

Do not rely on this file for dynamic PR or Gameweek state; use `PROJECT_STATE.md`, `ROADMAP.md` and live GitHub/runtime outputs.
