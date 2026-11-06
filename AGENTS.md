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

## Between-deadline squad state (permanent operator rule)

- The official public entry's most recently published picks are the **last locked Gameweek**, not a live view of the currently editable Gameweek. Treat these as the working registered-squad baseline between deadlines; do not falsely report the expected publication lag as an API or pipeline failure.
- Reconstruct the current *operator-known* state from that published baseline, any verified public transfer records, and the manager's **explicit subsequent confirmations** (including a screenshot of the current FPL interface). A specific "done" response to a specific set of agreed actions confirms only those actions, not unspecified changes.
- Once the manager confirms an action, treat it as applied for conversation/notification purposes unless newer evidence contradicts it. Do not repeatedly request public verification of an expected pre-deadline lag or resend unchanged advice. Label the state `user-confirmed, pending public reconciliation`, never `officially verified`.
- Do not assume the manager executed a recommendation without confirmation. For any further advice within that Gameweek, reconcile user-confirmed changes with the published baseline and ensure the model's transfer/lineup calculations are applicable to the reconstructed state. If a material discrepancy or unknown transfer/bank state prevents a sound reconstruction, withhold actionable instructions rather than pretending the production model has incorporated the override.
- When the next locked Gameweek's public picks/transfer history appears, reconcile the observed squad, transfer, captain and bench against the manager-confirmed state. A genuine mismatch is worth investigating; an expected delay before publication is not.
- This visibility rule **does not** waive operational-readiness, governance, freshness, player-availability or final team-news checks, and it never permits automatic FPL actions. Preserve the 48-hour notification policy; no status-only messages or repetitive warnings.

## Current project identifiers

- repository: `tametheboardgame/fpl-data-model`
- FPL team ID: `39395`
- season: `2026/27`

Do not rely on this file for dynamic PR or Gameweek state; use `PROJECT_STATE.md`, `ROADMAP.md` and live GitHub/runtime outputs.
