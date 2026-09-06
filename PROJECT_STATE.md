# FPL project state

This file is the fresh-chat handoff for the repository. Read it before starting new model-development work.

Last updated: 2026-09-06
Repository: `tametheboardgame/fpl-data-model`
FPL team ID: `39395`
Season: `2026/27`

## Fresh-chat bootstrap

A new project chat can simply say:

- `Start FPL-NEXT` — continue the first incomplete item in `ROADMAP.md`; **currently FPL-22E**.
- `Start FPL-22E` — fresh actionable-Gameweek reassessment from current production outputs plus independent current-news checks.

When receiving one of those commands:

1. Read this file and `ROADMAP.md` from current `main`.
2. Re-check current GitHub/CI/runtime state before acting because automated data/model commits can move `main`.
3. Treat `data/model/ensemble_production_policy.json` as authoritative for production model governance.
4. Do not repeat a completed phase; continue to the next incomplete prerequisite/package.
5. Update this file and `ROADMAP.md` whenever a material phase is completed, rejected or replaced.

## Strategic objective

Optimise to win mini-leagues, accepting sensible upside/variance rather than merely minimising median error. Mean expected points remains the accounting basis for reported xPts. Strategic ceiling/rank terms may affect choices but must never fabricate xPts.

Do not hard-code named players or player IDs to solve current-week symptoms. General mechanisms must be justified and tested.

## Source-of-truth order

1. Current GitHub/CI/runtime state.
2. `data/model/ensemble_production_policy.json`.
3. This `PROJECT_STATE.md`.
4. `ROADMAP.md`.
5. Historical design notes under `docs/`.

## Current production model governance

The component/ensemble challenger was independently rejected on the frozen 2025/26 holdout because it worsened rank correlation and top-10 hit rate despite a small MAE improvement. Production therefore remains on the control model.

Current policy:

- live model: `player-sim-2.0`;
- production ensemble point weight: `0.0`;
- production 6+/10+/15+ challenger weights: `0.0`;
- policy status: `holdout_rejected`;
- challenger: `player-sim-3.0-candidate`, shadow-only;
- reconsideration requires prospective 2026/27 evidence plus an explicit production-policy approval.

PR #45 made this rejection sticky. Do not allow recurring development backtests to silently reactivate the challenger.

## Permanent safeguards already merged

- PR #43: production fallback to control after holdout rejection.
- PR #45: sticky production policy separated from development candidate status.
- PR #46: unfinished current-GW history excluded from rolling form/minutes/team features; observed usage denominator uses actual completed player fixtures.
- rejected/shadow challenger disagreement cannot penalise control-model selections.
- Wildcard optimisation is budget-safe, captaincy/ceiling aware and contains no hard-coded current player.
- Wildcard strategic bonuses are selection utilities only; displayed expected points remain mean xPts.
- PR #47 / FPL-22A: one current-GW captain authority, so the displayed captain is the player whose mean return is doubled in route/report xPts.
- PR #48 / FPL-22B: one shared `strategic-captain-1.0` utility drives weekly current-GW captaincy, first actionable route GW, Wildcard target-GW captaincy, target-GW Triple Captain and current-GW Free Hit captaincy.
- PR #50 / FPL-22D: user-facing model-policy text now comes from the sticky production policy; captain/vice strategic utility is auditable separately from mean xPts.

## FPL-22A completion record

PR #47 — `Unify current-Gameweek captaincy with route scoring`

- validated head: `ec5c2be96b5222c4ba5619a3a341f05b64cc0149`;
- exact-head data validation: GREEN;
- exact-head full model build: GREEN;
- 140 tests passed;
- squash merge: `4e3efbbc946c7055c8088871fcc9ab3ea353d099`;
- post-merge production build `34022620843`: SUCCESS.

Permanent invariant: strategic captain logic decides who is doubled, but route/report totals use mean expected points only.

## FPL-22B completion record

PR #48 — `Implement FPL-22B shared strategic captain utility`

- validated PR head: `7b35fdf9c04187cc248c6b34dd7019d44e883292`;
- exact-head data validation: GREEN;
- exact-head full model build: GREEN;
- 147 tests passed;
- squash merge: `26be4484fdae7707a3c553f1cc032c10d65405f0`;
- post-merge production build `34025259144`: SUCCESS.

`strategic-captain-1.0` uses bounded mean, p90, P(10+), P(15+), ownership/rank pressure and defensive uncertainty. Minutes/availability are represented once through the risk-adjusted operational mean and exposed for audit, not double-penalised. Strategic utility never becomes displayed xPts.

## FPL-22C completion record

PR #49 — `Validate shared captain objective without holdout leakage` — is **COMPLETE / ACCEPTED**.

Governance:

- gates and split were predeclared in commit `9373201e509e01221d3c6b5cf18a0197ad6c692a` before the result workflow existed;
- primary gated seasons: 2018/19–2021/22;
- 2022/23–2023/24 descriptive only;
- 2024/25 and the closed/exposed 2025/26 holdout excluded from promotion gates;
- no captain coefficients were tuned in this phase;
- target-GW archived ownership was not used; ownership input is previous-GW selected counts converted to lagged ownership percentage.

Older archives lacked structural position/team metadata. FPL-22C repaired only:

- player ID -> position from `players_raw.csv`;
- fixture ID -> scheduled home/away team IDs from `fixtures.csv`, combined with archived `was_home`.

No fixture score/stat/result, target-GW ownership, availability or end-of-season player performance field was imported into the validation inputs. Final audit repaired 44,350 position rows and 44,350 team rows, with zero unresolved rows.

Final exact-head evidence on `5eef04298f0f7bac30d6c9f49a65181433f024a8`:

- captain validation run `34027036338`: SUCCESS;
- normal data validation run `34027036319`: SUCCESS;
- full suite: 155/155 tests passed;
- primary evaluated Gameweeks: `136` versus gate minimum `100`;
- lagged ownership coverage: `93.38%`;
- mean captain points difference: `+1.9412` points/GW, 95% CI `+1.0381` to `+2.8442`;
- mean regret difference: `-1.9412`;
- best-captain hit-rate difference: `+11.76` percentage points;
- captain 10+ rate difference: `+13.24pp`;
- captain 15+ rate difference: `+3.68pp`;
- all four primary seasons passed stability checks;
- failed gates: none;
- validation status: `accepted`;
- recommendation: retain `strategic-captain-1.0` as current-GW captain authority;
- squash merge: `94000a20c39eddc89b97eed571f32fe23c76bb96`.

Do not tune `strategic-captain-1.0` against this now-exposed FPL-22C evaluation set. Prospective 2026/27 monitoring may continue independently.

## FPL-22D completion record

PR #50 — `Make production policy and captain audits explicit` — is **COMPLETE**.

Landed behaviour:

- `projection_summary.json` method/limitations are generated from the sticky production policy rather than a development candidate;
- live model, policy status, challenger mode and live weights are exposed explicitly;
- stale wording that described the rejected ensemble as production has been removed from live summaries;
- current-GW captain utility audits expose mean input, bounded ceiling/haul/rank contributions, minutes/availability context and selection basis;
- operational captain and vice audits explicitly state that strategic bonuses are not expected points;
- report/route xPts continue to double mean xPts only;
- `decision_version = fpl-decisions-2.5`;
- `operations_version = fpl-gameweek-operations-1.8`.

Validation evidence:

- clean PR head: `64a654b6a326fe63f4072e1e521ba1f226467a01`;
- exact-head data validation run `34028912769`: SUCCESS;
- exact-head full model build run `34028912763`: SUCCESS;
- exact-head full suite: 157/157 tests passed;
- separate production-shaped source validation also passed a real build and policy/captain output assertions;
- squash merge: `f06c708f5ac8787097c33df270b750618961f238`;
- post-merge live-data run `34029053476`: SUCCESS;
- post-merge fresh dataset commit: `88a6cb710d434edbecb07551014b988f0849345a`;
- post-merge production build `34029081257`: SUCCESS;
- post-merge model-output commit: `ec5b074c517f1dd5b7188c18c5e9f567225f6870`.

Permanent invariant: strategic captain utility selects who is doubled; displayed and route expected points remain mean xPts only.

## Important research conclusions already reached

Do not repeat these without new evidence or a materially different hypothesis:

- component versions 3.1–3.4 improved targeted prior/minutes behaviour but did not clear broader FPL decision gates;
- per-player early-season attenuation was rejected;
- rank-safe/component-tail-only compromise was rejected because top-haul shortlist precision did not generalise;
- the frozen 2025/26 holdout is closed and must not be tuned against after exposure;
- FPL-22C validation is now also exposed and must not become a coefficient-tuning set.

## Current roadmap position

**FPL-22A, FPL-22B, FPL-22C and FPL-22D are complete. FPL-22E is the active package.**

FPL-22E must reassess the actionable Gameweek from fresh production outputs and independent current-news/fixture checks. Do not inherit any earlier captain, vice, transfer, chip or lineup result merely because it appeared during engineering validation.

After FPL-22E, later research is optional and evidence-driven, including prospective 2026/27 challenger evidence and bounded rival/mini-league exposure modelling.

See `ROADMAP.md` for exact scope and acceptance gates.
