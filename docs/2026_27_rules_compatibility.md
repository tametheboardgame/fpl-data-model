# 2026/27 rules compatibility

Phase 16 makes scoring, chips, free transfers and evaluation finality season-aware.

## Scoring

Live builds read `data/context/scoring_rules.json` and label every projection with the selected season's rules version. Historical backtests continue to use their original simulator defaults, so the validated 2022/23 to 2024/25 evidence is not silently rewritten.

The 2026/27 Bonus Points System changes cannot be reconstructed exactly from the current player-history feed because it does not expose every tackled, CBI, inside-box-save and big-chance-save event. The live model therefore uses a small, documented position-level transition prior:

- Goalkeeper: 1.08
- Defender: 1.00
- Midfielder: 1.05
- Forward: 1.04

The adjustment fades linearly to 1.00 after eight observed player fixtures. It changes the historical bonus-rate input only; the original rate and the applied multiplier remain auditable in generated projections. This is intentionally conservative until 2026/27 evidence can replace it.

Defensive-contribution thresholds remain 10 for defenders and 12 for midfielders and forwards.

## Chips

Chip rules are configured by season and half. For 2026/27 each chip has one first-half allocation expiring after the Gameweek 19 deadline and one second-half allocation. Unused first-half chips are marked expired rather than incorrectly counted as available later.

## Transfers

The decision layer replays the manager's official Gameweek transfer counts and transfer costs to infer the free-transfer balance. It supports a maximum of five, preserves banked transfers through Wildcard and Free Hit use, and represents season-specific top-ups. A transfer's three-Gameweek gain is reduced by a four-point hit whenever no free transfer is available.

Single-transfer hit accounting is Phase 16 scope. Joint multi-transfer route optimisation remains Phase 17.

## Evaluation finality

The collector stores the complete FPL event metadata in `gameweeks.json`. Prediction and external-context evaluation only score a Gameweek when both `finished` and `data_checked` are true. This protects prospective metrics from the 2026/27 09:00 UK next-day finalisation window and later Opta corrections.

## Sources

- Premier League, “All you need to know about changes to FPL for 2026/27”, 20 July 2026.
- Premier League, “What’s new in 2026/27 Fantasy: Changes to Bonus Points System”, 20 July 2026.
