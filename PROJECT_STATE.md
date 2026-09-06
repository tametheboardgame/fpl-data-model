# FPL project state

This file is the fresh-chat handoff for the repository. Read it before starting new model-development work.

Last updated: 2026-09-06
Repository: `tametheboardgame/fpl-data-model`
FPL team ID: `39395`
Season: `2026/27`

## Fresh-chat bootstrap

A new project chat can simply say:

- `Start FPL-NEXT` — continue the first incomplete item in `ROADMAP.md`; **currently FPL-22D**.
- `Start FPL-22D` — policy-aware reporting and captain-audit cleanup.
- `Start FPL-22E` — fresh actionable-Gameweek reassessment after FPL-22D is green.

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
- recommendation: retain `strategic-captain-1.0` as current-GW captain authority.

Squash merge: `94000a20c39eddc89b97eed571f32fe23c76bb96`.

Do not tune `strategic-captain-1.0` against this now-exposed FPL-22C evaluation set. Prospective 2026/27 monitoring may continue independently.

## Current live-output caveat / FPL-22D target

`data/chatgpt/projection_summary.json` is structurally correct about `player-sim-2.0`, `holdout_rejected` and zero challenger weights, but its human-readable method/limitations still describe a development-selected/validated ensemble as though it were production. This is stale and misleading.

FPL-22D must:

- make projection-summary method/limitations production-policy aware;
- remove any remaining live-output wording that calls the rejected ensemble production;
- expose live model/challenger status/weights clearly;
- expose captain mean xPts separately from strategic utility;
- expose bounded ceiling/haul/ownership/minutes audit contributions for captain and vice;
- explicitly state strategic captain bonuses are not part of displayed xPts;
- keep deadline reports concise;
- preserve agreement between report captain, route captain and mean-xPts scoring basis.

## Important research conclusions already reached

Do not repeat these without new evidence or a materially different hypothesis:

- component versions 3.1–3.4 improved targeted prior/minutes behaviour but did not clear broader FPL decision gates;
- per-player early-season attenuation was rejected;
- rank-safe/component-tail-only compromise was rejected because top-haul shortlist precision did not generalise;
- the frozen 2025/26 holdout is closed and must not be tuned against after exposure;
- FPL-22C validation is now also exposed and must not become a coefficient-tuning set.

## Current roadmap position

**FPL-22A, FPL-22B and FPL-22C are complete. FPL-22D is the active package.**

After FPL-22D:

1. FPL-22E — fresh actionable-Gameweek reassessment from newly generated production outputs plus independent current team-news/fixture sanity checks.
2. Later research only if justified, including prospective 2026/27 challenger evidence and bounded rival/mini-league exposure modelling.

See `ROADMAP.md` for exact scope and acceptance gates.
