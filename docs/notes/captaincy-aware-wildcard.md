# Captaincy-aware Wildcard objective

The Wildcard optimiser must not treat squad construction as a pure aggregate mean-EV problem.

## Objective

Mean expected points remains the foundation, but Wildcard squad selection also uses bounded strategic value for:

- weekly captaincy access;
- upper-tail/haul potential (`points_p90`, `P(10+)`, `P(15+)`);
- highly-owned captain rank exposure;
- the greater uncertainty of defensive captaincy.

These strategic adjustments choose **which** Wildcard squad to own. They do not inflate the expected-points edge used to decide whether the Wildcard itself is worth playing.

## Search safety

The beam-search pruning heuristic includes bounded ceiling and potential-captain access. This prevents expensive explosive players from being removed before the authoritative full-squad strategic scorer evaluates them.

## Guardrails

- No player is hard-coded or mandatory.
- Ownership is a bounded captaincy-risk input, not a blanket selection bonus.
- A materially superior mean projection can still beat a popular player.
- Chip timing thresholds remain based on expected-points gain.
- The strategic components are emitted in the candidate audit for review and future calibration.

Current objective version: `captaincy-ceiling-1.1`.
