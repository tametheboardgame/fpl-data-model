# FPL model roadmap

This is the executable roadmap for fresh ChatGPT project chats. Pair it with `PROJECT_STATE.md`.

## How to start from a new chat

Use one of these commands:

- `Start FPL-NEXT` — inspect GitHub and continue the first incomplete phase below. **As of 2026-09-06 this resolves to FPL-22E.**
- `Start FPL-22E` — fresh actionable-Gameweek reassessment after the engineering phases are green.

A requested phase must not bypass incomplete prerequisites. Always read `PROJECT_STATE.md`, re-check current GitHub/CI state, and update both handoff files after material progress.

---

## FPL-22A — Captain/route consistency production landing

**Status: COMPLETE — 2026-09-06**

### Goal

Make the current actionable Gameweek have one coherent captain authority: the player exposed to the user as captain must be the same player whose mean expected return is doubled in route/report xPts.

### Landed change

PR #47 — `Unify current-Gameweek captaincy with route scoring`

- validated PR head: `ec5c2be96b5222c4ba5619a3a341f05b64cc0149`
- exact-head data validation: GREEN
- exact-head full model build: GREEN
- exact-head tests: 140 passed
- squash merge commit: `4e3efbbc946c7055c8088871fcc9ab3ea353d099`
- post-merge production build run: `34022620843` — SUCCESS
- post-merge model-output commit: `d4279c867a0f5d70ae5df8fb1ed44d7e7794a0ec`

The implementation passes the decision layer's strategic captain-score map into the first actionable route Gameweek while retaining mean expected points as the only route/report scoring basis.

### Permanent invariant from FPL-22A

Strategic captain utility decides **who is doubled**. It must never be added to reported expected points.

---

## FPL-22B — One shared strategic captain utility

**Status: COMPLETE — 2026-09-06**

### Goal

Replace the partially duplicated current-Gameweek captain objectives with one reusable strategic captain-selection function.

### Landed change

PR #48 — `Implement FPL-22B shared strategic captain utility`

- validated PR head: `7b35fdf9c04187cc248c6b34dd7019d44e883292`
- exact-head data validation: GREEN
- exact-head full model build: GREEN
- exact-head tests: 147 passed
- squash merge commit: `26be4484fdae7707a3c553f1cc032c10d65405f0`
- post-merge data refresh run `34025234701`: SUCCESS
- post-merge production build run `34025259144`: SUCCESS

The shared `strategic-captain-1.0` utility:

- uses risk-adjusted current-GW mean xPts as its primary component;
- uses bounded p90, P(10+), P(15+) and ownership/rank-pressure terms;
- records expected minutes, availability confidence and selection-risk adjustment without double-penalising them;
- applies bounded position uncertainty so a defensive captain requires a material edge but remains possible;
- is deterministic and has no player/team-specific exceptions;
- drives normal current-GW support, first actionable route GW, Wildcard target-GW captaincy, target-GW Triple Captain and current-GW Free Hit captaincy.

Future Gameweeks may retain a simpler mean-based captain rule until equivalent distribution/reliability inputs are available; that limitation must remain explicit.

### Permanent invariant from FPL-22B

The shared strategic captain utility decides **who is doubled**. Strategic ceiling/rank/position terms are never added to displayed expected points.

---

## FPL-22C — Historical captain-objective validation

**Status: COMPLETE / ACCEPTED — 2026-09-06**

### Goal

Test whether the unified captain utility improves the objective that matters: selecting high-scoring captains without damaging model integrity.

### Predeclared design

The validation design and gates were committed before any result workflow existed in `9373201e509e01221d3c6b5cf18a0197ad6c692a`.

- primary gated seasons: 2018/19–2021/22;
- 2022/23–2023/24 descriptive only;
- 2024/25 and the exposed/closed 2025/26 holdout excluded from promotion gates;
- `strategic-captain-1.0` coefficients frozen, with no tuning in this phase;
- target-GW ownership excluded; lagged ownership reconstructed from previous-GW selected counts;
- one deterministic legal synthetic reference squad/starting XI per Gameweek isolates captain selection.

The first run was correctly `inconclusive` because only 69 primary GWs could be reconstructed. No gate was weakened. Older historical rows were then repaired only for missing structural metadata:

- player ID -> position from `players_raw.csv`;
- fixture ID -> scheduled `team_h`/`team_a`, combined with archived `was_home`, to restore club identity.

No score/stat/result, target-GW ownership, availability or end-of-season player performance field was imported into validation inputs. The final audit repaired 44,350 position rows and 44,350 team rows, with zero unresolved rows.

### Acceptance evidence

PR #49 — `Validate shared captain objective without holdout leakage`

- final validated head: `5eef04298f0f7bac30d6c9f49a65181433f024a8`;
- captain validation run `34027036338`: SUCCESS;
- normal data validation run `34027036319`: SUCCESS;
- exact-head full suite: 155/155 tests passed;
- primary evaluated Gameweeks: `136`, gate minimum `100`;
- lagged ownership coverage: `93.38%`;
- mean captain points difference: `+1.9412` points/GW, 95% CI `+1.0381` to `+2.8442`;
- mean regret difference: `-1.9412`;
- best-captain hit-rate difference: `+11.76` percentage points;
- 10+ captain rate difference: `+13.24pp`;
- 15+ captain rate difference: `+3.68pp`;
- all four primary seasons passed stability checks;
- failed gates: none;
- final validation status: `accepted`;
- squash merge commit: `94000a20c39eddc89b97eed571f32fe23c76bb96`.

The frozen utility therefore remains the current-GW captain authority. FPL-22C is now exposed evidence and must not become a coefficient-tuning set. Prospective 2026/27 evidence may continue independently.

---

## FPL-22D — Policy-aware reporting and audit cleanup

**Status: COMPLETE — 2026-09-06**

### Goal

Make conversational/operational outputs accurately describe the model that is actually live and make captaincy reasoning inspectable.

### Landed change

PR #50 — `Make production policy and captain audits explicit`

- clean PR head: `64a654b6a326fe63f4072e1e521ba1f226467a01`
- exact-head data validation run `34028912769`: SUCCESS
- exact-head full model build run `34028912763`: SUCCESS
- exact-head full suite: 157/157 tests passed
- squash merge commit: `f06c708f5ac8787097c33df270b750618961f238`
- post-merge data refresh run `34029053476`: SUCCESS
- post-merge fresh dataset commit: `88a6cb710d434edbecb07551014b988f0849345a`
- post-merge production build run `34029081257`: SUCCESS
- post-merge model-output commit: `ec5b074c517f1dd5b7188c18c5e9f567225f6870`

FPL-22D now:

- derives production-policy text from `ensemble_production_policy.json`;
- exposes live model, challenger mode/status and production weights explicitly;
- removes stale live-output wording that described the rejected ensemble as production;
- separates captain/vice mean xPts from strategic utility;
- exposes bounded ceiling/haul/ownership/minutes/availability audit inputs;
- records the captain selection basis;
- explicitly states strategic bonuses are not expected points;
- preserves agreement between report captain, route captain and mean-xPts scoring.

Output contracts are now `fpl-decisions-2.5` and `fpl-gameweek-operations-1.8`.

### Permanent invariant from FPL-22D

Production governance text must reflect the sticky production policy, and strategic captain utility must remain auditable but separate from mean expected-points accounting.

---

## FPL-22E — Fresh actionable-Gameweek reassessment

**Status: NEXT / ACTIVE ROADMAP ITEM**

### Goal

Reassess the currently actionable Gameweek from scratch after the captain model and reporting have been made internally coherent.

### Procedure

1. Refresh official FPL data and production model outputs.
2. Confirm operational readiness and exact deadline state.
3. Use the production report as the quantitative source of truth.
4. Independently sanity-check material decisions against current official club/FPL news and trusted late team-news/predicted-lineup sources.
5. Review transfers, XI, bench, captain, vice and chip state.
6. Compare mean xPts with ceiling/haul/rank considerations without overriding the model through ad-hoc player preferences.

### Acceptance gates

- use fresh post-FPL-22D official data and production outputs;
- confirm report/model versions and production policy are current;
- confirm registered squad and operational recommendation are valid;
- independently check material injury/availability/role/fixture assumptions against current sources;
- explicitly identify provisional versus firm/final advice based on deadline timing and source freshness;
- do not inherit any earlier engineering-validation recommendation merely because it appeared previously;
- record the resulting actionable recommendation and any unresolved checks in the handoff state.

### Important

Do not inherit `Haaland` captain / `João Pedro` vice, `roll_or_hold`, or any previous live-week result simply because it appeared in an earlier validation build. Recompute from fresh inputs.

---

## Later research backlog

These are not prerequisites for FPL-22 unless new evidence makes them urgent:

- prospective 2026/27 evidence collection for the shadow component challenger;
- only reconsider component/ensemble production after sufficient prospective evidence plus an explicit `ensemble_production_policy.json` approval change;
- mini-league/rival-specific exposure modelling with bounded influence;
- broader bookmaker/team-news source redundancy;
- Parquet/DuckDB historical analysis layer.

## Permanent safety rules

Across all future phases:

- no hard-coded current players as model fixes;
- no post-hoc gate weakening;
- no result leakage into pre-deadline forecasts;
- no unfinished fixture rows as completed form/usage evidence;
- no rejected challenger influencing production selections;
- no strategic utility added to mean expected-points accounting;
- every model promotion must be auditable and reversible.
