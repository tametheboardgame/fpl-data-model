# FPL-22C captain-objective validation

Status: PREDECLARED BEFORE RESULT EVALUATION

This note freezes the FPL-22C validation design before the historical validation workflow is run. It is deliberately separate from the implementation/result commit so the gates cannot be weakened after seeing the answer.

## Objective

Validate the already-frozen `strategic-captain-1.0` utility as a captain-selection decision layer. FPL-22C does **not** tune its coefficients.

The utility must continue to satisfy the FPL-22A/B accounting invariant: strategic terms can decide which player is doubled, but only the selected player's mean expected points are doubled in reported xPts.

## Data split

Primary gated retrospective evaluation:

- `2018-19`
- `2019-20`
- `2020-21`
- `2021-22`

Descriptive only, never used to weaken or pass a failed primary gate:

- `2022-23`
- `2023-24`

Explicitly excluded from FPL-22C promotion gates:

- `2024-25`, already exposed during broader model backtesting;
- `2025-26`, the independently exposed/frozen holdout that is closed to further tuning;
- `2026-27`, currently too sparse for a standalone promotion-grade sample, but it remains the required prospective follow-up.

The older primary seasons are intentionally used as an untouched robustness set. Their expected-stat data are less complete than modern seasons, so the result must also report this limitation and the modern descriptive seasons separately.

## Leakage-safe reconstruction

Player forecasts are reconstructed walk-forward within each season. A target Gameweek result is never read before its forecast is generated.

Historical ownership uses a one-Gameweek lag only:

1. deduplicate each previous Gameweek to one selection count per player, important for double Gameweeks;
2. infer the previous Gameweek manager base as `sum(player selections) / 15`;
3. calculate previous-GW ownership as `player selections / inferred managers * 100`;
4. feed that lagged percentage into the shared captain utility for the target Gameweek;
5. never use the target Gameweek's archived selection count as a captain input.

This is intentionally conservative versus live production, where current pre-deadline ownership is available directly.

## Reference squad and captain comparison

Because the archive does not contain this user's historical squads, each evaluable Gameweek uses one deterministic synthetic reference squad:

- legal 15-player FPL structure: 2 GK, 5 DEF, 5 MID, 3 FWD;
- maximum three players per club;
- £100.0m budget using the historical target-GW price;
- squad selected from the production/control mean forecast only;
- starting XI selected from mean forecast only;
- the same starting XI is used for both captain methods.

This isolates captain selection from transfer/squad-selection strategy.

Control captain:

- highest control mean xPts among the fixed starting XI, using the existing mean-lineup optimiser.

Strategic captain:

- `strategic-captain-1.0` over the same XI using control mean xPts, p90, P(10+), P(15+), lagged ownership and position treatment.

A second ownership-neutral strategic result is recorded as sensitivity analysis only. It is not allowed to replace the primary lagged-ownership result after the fact.

## Required metrics

Primary and per-season reporting must include at least:

- actual captain FPL points;
- mean captaincy regret versus the best actual scorer in the fixed starting XI;
- best-captain hit rate;
- actual captain 10+ frequency;
- actual captain 15+ frequency;
- top-three captain-shortlist hit rate;
- captain change rate and changed-choice win/loss/tie counts;
- premium-attacker captain cases;
- high-ownership/high-ceiling captain cases;
- defensive captain frequency;
- defensive-switch false positives;
- lagged-ownership coverage;
- season-by-season stability;
- paired mean-point difference with a normal-approximation 95% interval.

## Predeclared acceptance gates

These constants are frozen before result evaluation.

### Sample and input integrity

- at least `100` primary evaluation Gameweeks;
- lagged-ownership coverage across evaluated starting-XI candidates at least `80%`.

### Non-inferiority

Strategic versus control on the primary set:

- mean actual captain points difference must be at least `-0.10` points per Gameweek;
- mean captaincy-regret increase must be no more than `+0.10` points per Gameweek;
- best-captain hit-rate difference must be at least `-0.005`;
- 10+ captain-rate difference must be at least `-0.005`;
- 15+ captain-rate difference must be at least `-0.0025`.

### Upside requirement

At least one of the following must improve by the stated minimum:

- mean actual captain points: `+0.02` points/Gameweek;
- mean regret: `-0.02` points/Gameweek or better;
- best-captain hit rate: `+0.005`;
- 10+ captain rate: `+0.005`;
- 15+ captain rate: `+0.0025`.

This prevents promotion merely because every downside gate was narrowly avoided.

### Defensive artefact controls

- strategic defensive-captain frequency may exceed control by at most `0.02` absolute;
- if there are at least five strategic switches from an attacking control captain to a GK/DEF, no more than `50%` of those switches may score less than the best attacking starter; below five cases the false-positive rate is reported as too sparse to be a blocking statistic.

### Season stability

A primary season is stable when:

- mean captain-point difference is at least `-0.35` points/Gameweek; and
- mean regret increase is no more than `+0.35` points/Gameweek.

At least `3` of the `4` primary seasons must be stable, and no primary season may have a mean captain-point difference below `-0.50` points/Gameweek.

## Decision rule

- `accepted`: every predeclared blocking gate passes.
- `rejected`: the sample/input-integrity gates are adequate, but one or more performance/safety gates fail.
- `inconclusive`: sample size or lagged-ownership coverage is inadequate to apply the performance gates honestly.

If rejected, do not tune the coefficients against the failed primary set. Restore/retain the simpler validated captain behaviour and record the rejection. A materially different future hypothesis requires a new predeclared experiment.

If accepted, the shared utility may remain the current-GW captain authority, but prospective 2026/27 evidence must still be collected because historical squad reconstruction is synthetic and older seasons are not a perfect rules/data analogue.
