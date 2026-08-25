# Phase 20: 2026/27 launch and initial-squad readiness

Phase 20 prepares the decision system to construct the opening squad without using closed-season player names, prices or fixtures.

## Activation gate

The optimiser remains in `waiting_for_launch_data` until all of the following are true:

- the official API identifies the season as `2026/27`;
- Gameweek 1 is the next event and has a deadline;
- 20 clubs and a complete, uniquely identified player pool are present;
- every player has an official club, position, name and price;
- at least three future Gameweeks have fixture projections beginning with Gameweek 1; and
- the 2026/27 scoring configuration is active.

While any check fails, `recommended_squad` and `strategy_comparison` are empty. The system therefore cannot accidentally publish a squad made from the previous season's data.

## Optimisation

The launch optimiser enforces:

- a £100.0m budget;
- 15 unique players;
- two goalkeepers, five defenders, five midfielders and three forwards;
- no more than three players from one club; and
- a legal Gameweek 1 starting formation.

It creates three explicit structures:

- **Balanced:** expected points with useful bench depth.
- **Aggressive:** additional weight for upside and lower ownership.
- **Ownership-protected:** additional weight for highly owned players to reduce early rank volatility.

Balanced is the default recommendation. Each structure includes an XI, bench order, captain and vice-captain. Each strategy also publishes `lineup_correlation` and `selection_objective`. Balanced adds modest upside and ownership insurance while keeping expected points primary. Its bench receives a lower points weight and a soft £19.0m budget target so useful cover does not consume money that should improve the starting XI. The aggressive strategy can trade a small amount of mean for reduced opposing attacker-defender exposure. The balanced structure is then passed to the Phase 17 six-Gameweek route optimiser to identify fixture swings and planned transfers.

## Live behaviour

The plan is regenerated whenever the model builds before the Gameweek 1 deadline. Official price, fixture, availability or contextual changes can therefore alter the candidate structures. Once Gameweek 1 has passed, the initial-squad plan becomes `not_applicable_after_gameweek_1` and ordinary squad and transfer optimisation takes over.

The standalone output is `data/chatgpt/initial_squad_plan.json`; the same block is embedded in `fpl_decisions.json`.
