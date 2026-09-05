# FPL model roadmap

This is the executable roadmap for fresh ChatGPT project chats. Pair it with `PROJECT_STATE.md`.

## How to start from a new chat

Use one of these commands:

- `Start FPL-NEXT` — inspect GitHub and continue the first incomplete phase below.
- `Start FPL-22A` — merge/validate the current captain-route consistency fix.
- `Start FPL-22B` — implement the shared strategic captain utility, after prerequisites.
- `Start FPL-22C` — historical validation of the shared captain objective.
- `Start FPL-22D` — reporting and audit cleanup.
- `Start FPL-22E` — fresh current-Gameweek reassessment after the engineering phases are green.

A requested phase must not bypass incomplete prerequisites. Always read `PROJECT_STATE.md`, re-check current GitHub/CI state, and update both handoff files after material progress.

---

## FPL-22A — Captain/route consistency production landing

**Status:** READY / ACTIVE

**Current implementation:** PR #47, `Unify current-Gameweek captaincy with route scoring`.

### Goal

Make the current actionable Gameweek have one coherent captain authority: the player exposed to the user as captain must be the same player whose mean expected return is doubled in route/report xPts.

### Required actions

1. Re-check PR #47 state, head SHA and exact-head CI.
2. Merge only if the PR is still mergeable and all required checks remain green.
3. Run/observe a clean production build on `main` after merge.
4. Inspect fresh production outputs rather than relying on PR-run generated files.

### Acceptance gates

The post-merge production build must prove all of the following simultaneously:

- `ensemble_status = holdout_rejected`;
- production component/ensemble point and probability weights remain zero;
- live expected points are driven by `player-sim-2.0` control;
- component challenger remains shadow-only;
- unfinished current-GW history remains excluded from rolling features;
- completed-vs-raw history counts remain auditable;
- captain displayed in `gameweek_report.json` matches the first actionable route captain;
- reported mean xPts are calculated by doubling that same captain's mean return;
- no illegal XI/bench/captain or recommendation-field regression;
- full test/production build is green.

### Do not

- do not alter model coefficients merely to make the current captain a preferred named player;
- do not re-enable the rejected component challenger;
- do not treat strategic captain utility as extra expected points.

### Completion

Mark FPL-22A complete in this file and `PROJECT_STATE.md`, recording the merge commit and post-merge validation result.

---

## FPL-22B — One shared strategic captain utility

**Status:** PLANNED; requires FPL-22A

### Goal

Replace the partially duplicated current-Gameweek captain objectives with one reusable strategic captain-selection function.

The shared current-GW utility should have auditable inputs for:

- mean expected points;
- p90 / ceiling;
- P(10+);
- P(15+);
- expected minutes / availability confidence;
- bounded ownership/rank exposure;
- sensible position/uncertainty treatment.

### Scope

Use the same utility wherever a current actionable Gameweek captain is selected:

- normal weekly decision support;
- first actionable Gameweek of multi-Gameweek routing;
- Wildcard target-Gameweek captain selection;
- chip decisions where equivalent current-GW distribution inputs exist.

Future Gameweeks may retain a simpler mean-based captain rule until equivalent future-GW distribution inputs are available. If so, that limitation must be explicit in output/audit data.

### Core invariant

The strategic captain score decides **who is doubled**. It must never be added to reported expected points. Route/report xPts remain the sum of mean player xPts plus the selected captain's mean xPts.

### Design requirements

- one implementation, not separately tuned weekly/Wildcard coefficient copies where avoidable;
- no hard-coded players, teams or IDs;
- bounded strategic terms so weak mean projections cannot be rescued by ownership/ceiling alone;
- deterministic output for unchanged inputs;
- explicit component audit showing why captain A outranked captain B;
- preserve exceptional defender captaincy when evidence genuinely dominates, while avoiding small-edge defensive artefacts.

### Acceptance gates before FPL-22C

- focused captain utility unit tests;
- weekly, multiweek, Wildcard and chip wiring regressions;
- proof strategic utility changes selection without fabricating mean xPts;
- proof all user-facing current-GW captain fields agree;
- full existing suite green.

---

## FPL-22C — Historical captain-objective validation

**Status:** PLANNED; requires FPL-22B

### Goal

Test whether the unified captain utility improves the objective that actually matters: selecting high-scoring captains without damaging model integrity.

### Validation design

Use leakage-safe historical Gameweek reconstruction. Do not tune specifically for a current player or current fixture. Do not reopen/tune against the frozen 2025/26 holdout after its prior exposure.

Use development/validation splits that keep final evaluation separate from coefficient selection. If genuinely fresh data are unavailable, prefer prospective 2026/27 evaluation over repeated tuning on an already-exposed holdout.

### Required metrics

At minimum compare shared strategic captaincy with the current/control captain method for:

- actual captain FPL points;
- mean captaincy regret versus best available squad captain;
- best-captain hit rate;
- P(actual captain scores 10+);
- P(actual captain scores 15+);
- top-10/top-haul shortlist quality where relevant;
- premium-attacker cases;
- high-ownership/high-ceiling cases;
- defensive-captain false positives;
- stability across seasons, not only pooled averages.

### Promotion rule

Predeclare the acceptance criteria before looking at the final evaluation. Do not weaken a gate after seeing a desired live-week outcome.

If the shared objective fails, keep the simpler validated behaviour and record the rejection in `PROJECT_STATE.md` rather than forcing promotion.

---

## FPL-22D — Policy-aware reporting and audit cleanup

**Status:** PLANNED; can develop after FPL-22A, finalise after FPL-22C

### Goal

Make all conversational/operational outputs accurately describe the model that is actually live and make captaincy reasoning inspectable.

### Required changes

- remove/replace stale text that describes the development-selected ensemble as live while production policy is `holdout_rejected`;
- make `projection_summary.json` method/limitations policy-aware;
- expose live model version, challenger status and production weights clearly;
- expose captain mean xPts separately from strategic captain utility;
- include an audit of the bounded ceiling/haul/ownership/minutes contributions used to select captain and vice;
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

**Status:** PLANNED; requires FPL-22A and should normally follow FPL-22B–22D

### Goal

Only after the model is internally coherent, reassess the currently actionable Gameweek from scratch.

### Procedure

1. Refresh official FPL data and production model outputs.
2. Confirm operational readiness and deadline state.
3. Use the production report as the quantitative source of truth.
4. Independently sanity-check material decisions against current official club/FPL news and trusted late team-news/predicted-lineup sources.
5. Review transfers, XI, bench, captain, vice and chip state.
6. Compare mean xPts with ceiling/haul/rank considerations without overriding the model through ad-hoc player preferences.

### Important

Do not inherit `B.Fernandes` captain / `Haaland` vice or any previous live-week result simply because it appeared in an earlier validation build. Recompute from fresh inputs.

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
