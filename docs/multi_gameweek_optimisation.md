# Multi-Gameweek squad and transfer-route optimisation

Phase 17 turns fixture-level player forecasts into legal, cost-aware transfer routes across the next six Gameweeks.

## Objective

Each route maximises the discounted expected points of the best legal starting XI plus captain points in every Gameweek, after deducting transfer hits and a small decision-friction cost for speculative transfers. Later Gameweeks are discounted by 4% per step because their minutes, availability and fixture forecasts are less certain.

The output compares every route with holding the current squad. It reports projected net points, uplift against hold, transfer hits, bank, free-transfer balance, captain and starting XI for each Gameweek.

## State carried between Gameweeks

- The complete 15-player squad.
- Player selling prices and current bank.
- Accumulated free transfers, capped by the active season rules.
- Four-point transfer hits.
- Three-player-per-club and positional squad limits.
- The best legal formation and captain for each Gameweek.

The search can bank a transfer, make one transfer, or make two linked transfers in a Gameweek. This allows it to find routes that deliberately wait for a fixture swing or use a downgrade to finance an upgrade.

## Search method

An exact search over every possible Premier League squad and six-Gameweek transfer sequence is computationally impractical. The optimiser therefore uses a documented beam search:

- Ten forecast candidates per position, plus current squad players.
- Up to two transfers per Gameweek.
- The 60 best distinct legal states retained after each Gameweek.
- Five best final routes included in the conversational output.

Candidate and state pruning use only information available in the current forecast. The player ensemble remains unchanged.

## Current assumptions

- Player prices remain constant over the six-Gameweek horizon.
- New signings can later be sold for their purchase price because no price changes are forecast.
- Transfers preserve player position.
- No chip is assumed inside a Phase 17 route.
- First-Gameweek external context multipliers are included; later Gameweeks use the underlying fixture projections until newer context arrives.
- Every planned transfer carries 0.75 points of decision friction, and a short-horizon reversal carries a further 1.5-point penalty.
- A transfer route must retain at least a one-point decision-adjusted edge over holding before it is promoted as the recommendation.

Blank and Double Gameweeks already flow through the fixture-level projection matrix. Explicit chip optimisation across those schedules remains Phase 18.

## Output contract

`data/chatgpt/fpl_decisions.json` now uses `fpl-decisions-1.3` and adds `multi_gameweek_plan` containing:

- Horizon Gameweeks and objective.
- Hold-squad expected points.
- Recommended route and four alternatives.
- Gameweek-by-Gameweek transfers, hit costs, bank, line-up and captain.
- Final squad, bank and free-transfer balance.
- Search parameters and modelling assumptions.

When future projections are unavailable, the field returns a clean waiting state and no route.
