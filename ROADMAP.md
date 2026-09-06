# FPL model roadmap

This is the executable roadmap for fresh ChatGPT project chats. Pair it with `PROJECT_STATE.md`.

## How to start from a new chat

Use one of these commands:

- `Start FPL-NEXT` — inspect GitHub and continue the first incomplete phase below. **As of 2026-09-06 this resolves to FPL-22C.**
- `Start FPL-22C` — historical/prospective validation of the shared captain objective.
- `Start FPL-22D` — reporting and audit cleanup.
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

The implementation:

- passes the decision layer's strategic captain-score map into the first actionable Gameweek of multi-Gameweek routing;
- still calculates all reported route points from mean expected points only;
- makes the route captain the operational scoring authority, with the decision captain only a fallback;
- bumps operations output to `fpl-gameweek-operations-1.7`.

### Post-merge acceptance evidence

Fresh production output generated `2026-09-06T08:44:35Z` proves the safeguards simultaneously:

- production model: `player-sim-2.0`;
- `ensemble_status = holdout_rejected`;
- ensemble point weight: `0.0`;
- ensemble 6+/10+/15+ probability weights: all `0.0`;
- challenger remains `player-sim-3.0-candidate`, shadow-only / not applied live;
- raw fixture-history rows: `1889`;
- completed fixture-history rows admitted to live features: `1236`;
- unfinished current-GW history therefore remains excluded;
- `gameweek_report.json` captain and first route captain both resolve to player `426` / `B.Fernandes` for the current provisional GW4 build;
- route/report expected points agree at `44.474` and use that captain's mean return in the doubled-score arithmetic;
- report status is `ready` and the production build completed successfully.

The named GW4 output above is validation evidence only, not a permanent player rule and not final advice. FPL-22E must recompute from fresh inputs.

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
- refreshed-data commit: `59929b9cbc2bcb3b876c99e17740cb732ad8033f`
- post-merge production build run `34025259144`: SUCCESS
- post-merge model-output commit: `aa2f8884b0a760a5a06cf549a4d7b36e9c73f54e`

The shared `strategic-captain-1.0` utility:

- uses risk-adjusted current-Gameweek mean xPts as the primary component;
- uses bounded p90, P(10+), P(15+) and ownership/rank-pressure terms;
- records expected minutes, availability confidence and selection-risk adjustment in the audit without double-penalising them;
- applies bounded position uncertainty so a defensive captain requires a material edge but remains possible when evidence genuinely dominates;
- is deterministic and contains no player/team-specific exceptions;
- centralises the already-tested Wildcard captain coefficients rather than fitting new coefficients against the exposed 2025/26 holdout.

The same utility now drives:

- normal current-Gameweek decision support;
- the first actionable Gameweek of multi-Gameweek routing;
- Wildcard target-Gameweek captaincy;
- target-Gameweek Triple Captain selection;
- target-Gameweek Free Hit strategic squad/captain selection.

Future Gameweeks may retain a simpler mean-based captain rule until equivalent future-GW distribution/reliability inputs are available; that limitation is explicit.

### Acceptance evidence

Fresh production output generated `2026-09-06T09:40:45Z` confirms:

- `decision_version = fpl-decisions-2.4`;
- report status remains `ready`;
- production model remains `player-sim-2.0`;
- `ensemble_status = holdout_rejected`;
- ensemble point and 6+/10+/15+ challenger weights remain `0.0`;
- challenger remains shadow-only;
- provisional GW4 report captain = player `411` / `Haaland`;
- first GW4 route captain = the same player;
- report and route expected points agree at `44.563` using mean xPts accounting;
- strategic utility therefore changed the selected captain without adding the strategic score to reported xPts;
- no player-specific special case is present in the implementation.

The named GW4 result is validation evidence only. FPL-22E must recompute the actionable recommendation from fresh inputs and independent team-news checks.

### Permanent invariant from FPL-22B

The shared strategic captain utility decides **who is doubled**. Strategic ceiling/rank/position terms are never added to displayed expected points.

---

## FPL-22C — Historical captain-objective validation

**Status: NEXT / ACTIVE ROADMAP ITEM**

### Goal

Test whether the unified captain utility improves the objective that matters: selecting high-scoring captains without damaging model integrity.

### Validation design

Use leakage-safe historical Gameweek reconstruction. Do not tune specifically for a current player or current fixture. The frozen 2025/26 holdout has already been exposed and is closed; do not tune new coefficients against it.

Use development/validation splits that keep final evaluation separate from coefficient selection. If genuinely fresh historical data are unavailable, prefer prospective 2026/27 evaluation over repeated tuning on an already-exposed holdout.

### Required metrics

At minimum compare shared strategic captaincy with the current/control captain method for:

- actual captain FPL points;
- mean captaincy regret versus best available squad captain;
- best-captain hit rate;
- frequency of actual captain scores 10+;
- frequency of actual captain scores 15+;
- top-haul shortlist quality where relevant;
- premium-attacker cases;
- high-ownership/high-ceiling cases;
- defensive-captain false positives;
- stability across seasons, not only pooled averages.

### Promotion rule

Predeclare acceptance criteria before looking at the final evaluation. Do not weaken a gate after seeing a desired live-week outcome.

If the shared objective fails, keep the simpler validated behaviour and record the rejection in `PROJECT_STATE.md` rather than forcing promotion.

---

## FPL-22D — Policy-aware reporting and audit cleanup

**Status: PLANNED; can develop after FPL-22B, finalise after FPL-22C**

### Goal

Make conversational/operational outputs accurately describe the model that is actually live and make captaincy reasoning inspectable.

### Known current defect

`data/chatgpt/projection_summary.json` correctly reports `player-sim-2.0`, `holdout_rejected` and zero challenger weights, but its human-readable `method` string still says `Development-selected ensemble ...`. Treat that text as stale until this phase fixes it.

### Required changes

- make `projection_summary.json` method/limitations policy-aware;
- remove any remaining live-output text that describes the rejected ensemble as production;
- expose live model version, challenger status and production weights clearly;
- expose captain mean xPts separately from strategic captain utility;
- include an audit of bounded ceiling/haul/ownership/minutes contributions used to select captain and vice;
- explicitly state that strategic captain bonuses are not part of displayed xPts;
- keep reports concise enough for deadline use.

### Acceptance gates

- production-policy text matches `ensemble_production_policy.json`;
- no output calls a rejected ensemble the live model;
- report captain, route captain and captain scoring basis agree;
- schema/version bumps and regression tests where output contracts change;
- full suite green.

---

## FPL-22E — Fresh actionable-Gameweek reassessment

**Status: PLANNED; requires FPL-22B and should normally follow FPL-22C–22D**

### Goal

Only after the captain model and reporting are internally coherent, reassess the currently actionable Gameweek from scratch.

### Procedure

1. Refresh official FPL data and production model outputs.
2. Confirm operational readiness and exact deadline state.
3. Use the production report as the quantitative source of truth.
4. Independently sanity-check material decisions against current official club/FPL news and trusted late team-news/predicted-lineup sources.
5. Review transfers, XI, bench, captain, vice and chip state.
6. Compare mean xPts with ceiling/haul/rank considerations without overriding the model through ad-hoc player preferences.

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
