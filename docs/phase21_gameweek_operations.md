# Phase 21: Live Gameweek operations and deadline reporting

Phase 21 converts the model outputs into one concise, auditable report for human review before every FPL deadline. It remains advisory and never calls an endpoint that changes the manager's team.

## Outputs

- `data/chatgpt/gameweek_report.json` is the structured current report.
- `data/chatgpt/gameweek_report.md` is the concise human-readable report.
- `data/operations/gwXX/` retains an immutable JSON and Markdown report whenever the material decision state changes.
- `data/chatgpt/fpl_decisions.json` contains a compact `gameweek_operations` status block linking to the reports.

## Report contract

When decision support is ready, the report contains:

- target Gameweek, deadline in UTC and UK time, and remaining hours;
- recommended transfers or an explicit roll/hold action;
- starting XI, bench order, captain and vice-captain;
- current chip action and the six-Gameweek route;
- player availability risks, provider health and input freshness;
- material changes since the previous report;
- the latest immutable Phase 19 pre-deadline snapshot.

Before launch or whenever future projections are unavailable, all named recommendation fields remain empty and the report uses `waiting_for_recommendations`.

## Material changes

The decision fingerprint excludes generation timestamps and other refresh noise. A new archive is produced only when one or more of these change:

- target Gameweek or deadline;
- starting XI or bench order;
- captain or vice-captain;
- transfer or chip recommendation;
- squad availability information;
- known fixture structure;
- operational readiness or warning state.

## Freshness and safety

Official FPL data may be no more than eight hours old during normal operation and no more than three hours old inside the eight-hour deadline freeze window. Missing, stale or internally contradictory data raises a warning. A high-severity warning changes the report status to `review_required` rather than silently presenting the recommendation as ready.

The API-Football plan restriction is reported transparently as a low-severity limitation. It does not block the report while official FPL data, bookmaker data and other configured sources remain usable.

## Deadline freeze

Phase 19 already creates immutable prospective snapshots during the final eight hours before a deadline. Phase 21 exposes the latest matching snapshot and reports one of:

- `waiting_for_freeze_window`;
- `frozen`;
- `snapshot_missing`;
- `deadline_passed`.

This preserves the exact pre-deadline recommendation for later evaluation. The latest valid snapshot before the deadline is authoritative.

## Automation

The existing six-hour official-data refresh starts the production model build after validation. Material external-context changes also rebuild decisions in their existing workflow. Phase 21 therefore refreshes alongside every operationally meaningful model run without consuming additional Odds API credits.

No transfer, chip, line-up or captain action is performed automatically. The manager must review and confirm all changes in FPL.
