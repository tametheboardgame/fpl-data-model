# FPL project state

This file is the fresh-chat handoff for the repository. Read it before starting new model-development work.

Last updated: 2026-09-06
Repository: `tametheboardgame/fpl-data-model`
FPL team ID: `39395`
Season: `2026/27`

## Fresh-chat bootstrap

A new project chat can simply say:

- `Start FPL-NEXT` — continue the first incomplete item in `ROADMAP.md`; **currently FPL-22B**.
- `Start FPL-22B` — start the shared strategic captain-utility work directly.
- `Start FPL-22C`, `Start FPL-22D`, `Start FPL-22E` — request a later roadmap phase, subject to prerequisites.

When receiving one of those commands, the assistant should:

1. Connect to GitHub and read this file plus `ROADMAP.md` from `main`.
2. Check live GitHub state before acting: current `main`, open PRs, exact-head CI and current production outputs can have changed since this document was written.
3. Treat `data/model/ensemble_production_policy.json` as authoritative for which prediction model may drive production decisions.
4. If the requested phase is already complete, record that and continue to the next incomplete prerequisite/phase rather than repeating work.
5. Update `PROJECT_STATE.md` and `ROADMAP.md` whenever a material phase is completed, rejected or replaced.

## Strategic objective

Optimise to win mini-leagues, accepting sensible upside/variance rather than merely minimising median error. Mean expected points remains the accounting basis for reported xPts. Strategic ceiling/rank terms may affect choices but must never fabricate xPts.

Do not hard-code named players or player IDs to solve a current-week symptom. General mechanisms must be justified and tested.

## Source-of-truth order

When documents disagree, use this order:

1. Current GitHub/CI/runtime state.
2. `data/model/ensemble_production_policy.json` for live model governance.
3. This `PROJECT_STATE.md`.
4. `ROADMAP.md`.
5. Detailed historical design docs under `docs/`.

## Current production model governance

The component/ensemble challenger was independently rejected on the frozen 2025/26 holdout after it worsened rank correlation and top-10 hit rate despite a small MAE improvement. Production therefore uses the control model.

Current production policy:

- live model: `player-sim-2.0`;
- production ensemble point weight: `0.0`;
- production 6+/10+/15+ challenger weights: `0.0`;
- policy status: `holdout_rejected`;
- component challenger: `player-sim-3.0-candidate`, shadow-only;
- reconsideration requires prospective 2026/27 evidence and an explicit production-policy approval.

PR #45 made this rejection sticky so recurring development backtests cannot silently reactivate the challenger.

## Completed safeguards from the September model review

The following are merged on `main` and should not be undone:

- PR #43: production fallback to control after the independent holdout rejection.
- PR #45: separate sticky production policy from development candidate/backtest status.
- PR #46: exclude unfinished current-Gameweek player-history rows from rolling form/minutes/team features.
- observed usage denominator uses actual completed player fixtures rather than `target_gameweek - 1`.
- rejected/shadow challenger disagreement cannot penalise control-model selections.
- Wildcard optimisation is budget-safe, captaincy/ceiling aware and contains no hard-coded player.
- Wildcard strategic bonuses are selection utilities only; displayed expected points remain mean xPts.
- PR #47: current-Gameweek captaincy and route scoring now use one captain authority, so the player shown as captain is the player whose mean return is doubled in route/report xPts.

## FPL-22A completion record

PR #47 — `Unify current-Gameweek captaincy with route scoring` — is complete.

Validation and landing:

- validated head: `ec5c2be96b5222c4ba5619a3a341f05b64cc0149`;
- exact-head data validation: GREEN;
- exact-head full model build: GREEN;
- 140 tests passed at exact head;
- squash merge: `4e3efbbc946c7055c8088871fcc9ab3ea353d099`;
- post-merge production build run `34022620843`: SUCCESS;
- post-merge model-output commit: `d4279c867a0f5d70ae5df8fb1ed44d7e7794a0ec`.

Fresh post-merge production output generated `2026-09-06T08:44:35Z` confirms:

- `operations_version = fpl-gameweek-operations-1.7`;
- `model_version = player-sim-2.0`;
- `ensemble_status = holdout_rejected`;
- ensemble point weight `0.0`;
- 6+/10+/15+ challenger weights all `0.0`;
- challenger remains not applied to the live model;
- raw player-fixture history rows `1889`;
- completed rows admitted to rolling features `1236`;
- unfinished current-GW history remains excluded;
- current provisional GW4 report captain = player `426` / `B.Fernandes`;
- first GW4 route captain = the same player;
- report and route expected points both `44.474`.

That current named recommendation is a validation observation only. It must not become a player-specific rule or be inherited as final GW4 advice without a fresh FPL-22E reassessment.

## Current live-output caveat

`data/chatgpt/projection_summary.json` is structurally correct about the live model and weights, but its human-readable `method` text still says `Development-selected ensemble ...`. That text is stale. FPL-22D is explicitly responsible for making this reporting policy-aware.

## Important research conclusions already reached

Do not repeat these experiments unless there is new evidence or a materially different hypothesis:

- Component versions 3.1–3.4 tested player-specific previous-season role/minutes priors. They repaired early-season component minutes but did not improve required FPL decision metrics enough to justify production promotion.
- 3.1 failed the held-out top-10 gate.
- 3.2 fixed the early-season minutes diagnosis but did not clear the global MAE-improvement gate.
- 3.3/3.4 improved targeted minutes behaviour but were slightly worse than production on broader FPL accuracy/ranking checks.
- A per-player early-season attenuation of component influence was rejected; development data selected no attenuation.
- A rank-safe/component-tail-only compromise was rejected because top-haul shortlist precision did not generalise.
- The frozen 2025/26 holdout is closed. Do not tune model parameters against it after exposure.

## Current roadmap position

**FPL-22A is complete. The next package is FPL-22B.**

FPL-22B builds one shared strategic captain utility for the current actionable Gameweek across weekly decision support, the first multiweek route Gameweek, Wildcard target-GW captaincy and applicable chip decisions.

The shared utility is intended to use auditable, bounded inputs for mean xPts, p90/ceiling, P(10+), P(15+), expected minutes/availability, ownership/rank exposure and position/uncertainty treatment. It must contain no hard-coded players and must never add strategic utility to reported mean xPts.

After FPL-22B:

1. FPL-22C — leakage-safe historical/prospective validation of the shared captain objective, with predeclared gates and no reuse of the closed 2025/26 holdout for tuning.
2. FPL-22D — policy-aware reporting and captain-audit cleanup, including the stale `projection_summary.json` method text.
3. FPL-22E — fresh current-Gameweek reassessment using new production outputs plus independent news/fixture sanity checks.

See `ROADMAP.md` for exact scope, acceptance gates and start codes.
