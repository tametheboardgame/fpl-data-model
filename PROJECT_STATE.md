# FPL project state

This file is the fresh-chat handoff for the repository. Read it before starting new model-development work.

Last updated: 2026-09-05
Repository: `tametheboardgame/fpl-data-model`
FPL team ID: `39395`
Season: `2026/27`

## Fresh-chat bootstrap

A new project chat can start with either:

- `Start FPL-NEXT` — continue the first incomplete item in `ROADMAP.md`.
- `Start FPL-22A`, `Start FPL-22B`, etc. — start that named roadmap phase.

When receiving one of those commands, the assistant should:

1. Connect to GitHub and read this file plus `ROADMAP.md` from `main`.
2. Check live GitHub state before acting: current `main`, open PRs, exact-head CI and current production outputs can have changed since this document was written.
3. Treat `data/model/ensemble_production_policy.json` as authoritative for which prediction model may drive production decisions.
4. If the requested phase is already complete, record that and continue to the next incomplete prerequisite/phase rather than repeating work.
5. Update `PROJECT_STATE.md` and `ROADMAP.md` whenever a material phase is completed, rejected or replaced so the next chat remains self-contained.

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

Current policy:

- live model: `player-sim-2.0`
- production ensemble point weight: `0.0`
- production 6+/10+/15+ challenger weights: `0.0`
- policy status: `holdout_rejected`
- component challenger: `player-sim-3.0-candidate`, `shadow_only`
- reconsideration requires prospective 2026/27 evidence and an explicit production-policy approval

PR #45 made this rejection sticky so recurring development backtests cannot silently reactivate the challenger.

## Completed safeguards from the September model review

The following are already merged on `main` and should not be undone:

- PR #43: production fallback to control after the independent holdout rejection.
- PR #45: separate sticky production policy from development candidate/backtest status.
- PR #46: exclude unfinished current-Gameweek player-history rows from rolling form/minutes/team features.
- observed usage denominator uses actual completed player fixtures rather than `target_gameweek - 1`.
- rejected/shadow challenger disagreement cannot penalise control-model selections.
- Wildcard optimisation is budget-safe, captaincy/ceiling aware and contains no hard-coded player.
- Wildcard strategic bonuses are selection utilities only; displayed expected points remain mean xPts.

The completed-history fix was verified on live data: 1,888 raw player-fixture history rows were reduced to 1,236 genuinely completed rows in the relevant build, preventing unfinished GW rows from diluting usage/form.

## Active captain-route work at handoff

PR #47 — **Unify current-Gameweek captaincy with route scoring**

Validated implementation head:

- head: `ec5c2be96b5222c4ba5619a3a341f05b64cc0149`
- exact-head `update-and-validate`: GREEN
- exact-head full `build`: GREEN
- 140 tests passed in that exact-head build

After those checks completed, `main` advanced with the persistent handoff/documentation work and an automated dataset refresh. Current comparison at this handoff shows PR #47 is **diverged** from `main`: 4 commits ahead and 8 commits behind its merge base, and GitHub currently reports it as not mergeable.

Therefore **do not merge the stale PR #47 head directly**. FPL-22A must first refresh/rebase the validated change onto latest `main` (or create a clean superseding branch/PR carrying the same five intended source/test diffs), then rerun exact-head CI before merge.

The intended #47 code diff is limited to:

- `src/fpl_decisions.py`
- `src/fpl_gameweek_operations.py`
- `src/fpl_multiweek.py`
- `tests/test_phase17_multiweek.py`
- `tests/test_phase21_gameweek_operations.py`

What the change fixes:

- decision support had a strategic/tail-aware captain choice;
- the multi-Gameweek route could independently choose a different mean-xPts captain;
- operations could display the decision captain while copying xPts calculated with the route captain doubled.

The validated implementation makes the first actionable Gameweek route accept the same strategic captain-utility map while still calculating all route points from mean expected points, then makes the route captain the operational scoring authority.

Exact-head GW4 audit from the validated branch:

- transfer action: `roll_or_hold`
- captain: `B.Fernandes`
- vice: `Haaland`
- expected points: `44.492`
- production ensemble status: `holdout_rejected`
- production ensemble weight: `0.0`
- Haaland control next-GW xPts in that build: `5.317`

These are validation observations, not permanent player-specific rules and not final GW4 advice.

## Important research conclusions already reached

Do not repeat these experiments unless there is new evidence or a materially different hypothesis:

- Component versions 3.1–3.4 tested player-specific previous-season role/minutes priors. They repaired early-season component minutes but did not improve the required FPL decision metrics enough to justify production promotion.
- 3.1 failed the held-out top-10 gate.
- 3.2 fixed the early-season minutes diagnosis but did not clear the global MAE-improvement gate.
- 3.3/3.4 improved targeted minutes behaviour but were slightly worse than production on broader FPL accuracy/ranking checks.
- A per-player early-season attenuation of component influence was rejected; development data selected no attenuation.
- A rank-safe/component-tail-only compromise was also rejected because top-haul shortlist precision did not generalise.
- The frozen 2025/26 holdout is closed. Do not tune model parameters against it after exposure.

## Known remaining work

The next work is deliberately about consistency and validation, not another Haaland-specific repair:

1. refresh/rebase the validated #47 captain-route change onto latest `main`, rerun CI, merge and production-validate it;
2. build one shared strategic captain utility for current-GW weekly, Wildcard, multiweek first-GW and applicable chip decisions;
3. validate that captain objective historically without weakening gates;
4. make reporting/model-description text policy-aware and expose captain audit cleanly;
5. only then reassess the current actionable Gameweek from scratch using fresh production outputs plus an independent news/fixture sanity check.

See `ROADMAP.md` for acceptance gates and start codes.
