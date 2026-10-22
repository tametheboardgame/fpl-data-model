# Issue #55 — Groß versus Mbeumo: GW8 diagnostic findings

**Snapshot:** production decisions generated 2026-10-22 05:27:51 UTC; team 39395; target GW8. **Status:** preliminary, read-only, no FPL actions authorised.

## Verified evidence

- The production recommendation uses both GW8 free transfers: João Pedro → Calvert-Lewin and Szoboszlai → Mbeumo. Projected GW8 XI mean xPts **58.723**, six-GW net xPts **348.805**, discounted route objective **308.683**, projected six-GW gain versus holding **32.607**.
- Groß is **not excluded** from the direct transfer shortlist. Szoboszlai → Groß appears with **11.898** projected incremental three-GW points because the current Szoboszlai baseline is zero. This number **must not** be compared directly with Mbeumo's **5.602** GW8 individual expected points; they measure different things.
- All five published route variants start with the same GW8 Mbeumo purchase. Route 5 buys Groß in **GW11** for Schade and has discounted objective **308.628** versus **308.683** for the winner, a difference of **0.055**. It is *not* a Groß-in-GW8 counterfactual.
- Optimiser configuration: beam width **60**, candidate players per position **10**, maximum **2** transfers/GW, friction **1.25** points per transfer, round-trip penalty **1.5**, minimum route edge **4**, minimum separation **1.5**. Candidate/beam pruning is a plausible explanation for why the output lacks a Groß-first route; this has **not** been proven.
- The sticky ensemble policy is **holdout_rejected**, live control **player-sim-2.0**, challenger **shadow_only**, all live ensemble point/haul weights **0**.

## Preliminary interpretation

The available evidence supports a **route optimisation / timing** question, not a missing-player issue. The optimiser shows some willingness to own Groß later, but the published routes are too similar to establish whether Mbeumo is superior to Groß as a GW8 acquisition.

## Remaining acceptance gates (not yet passed)

1. Force a Groß-first route through the same optimiser with the same registered squad, deadline-state and forecasts. Include best feasible companion transfer; compare against the published winner and a hold route.
2. Compare GW8, 3, 5, 6 and 8 GW horizons, clearly flagging any horizons unsupported by existing projection data.
3. Check completed-match underlying statistics, minutes, role, availability and fixture context against dated official/trusted evidence.
4. Assess ownership, ceiling, haul and mini-league rank utility without converting strategic utility to mean xPts.
5. Validate diagnostic tests and full CI. No production model changes, no transfer actions.

## Reproduce current published-route audit

`python -m src.diagnostic_transfer_challenge --candidate Groß --chosen Mbeumo`

The script reads existing JSON and prints JSON to stdout. It neither runs the optimiser nor writes production files. **No verdict that a Groß-first transfer is better or worse can be supported until gate 1 passes.**
