# Free-transfer history hotfix

## Problem

Production currently reports 3 free transfers for GW5, but official FPL history for team 39395 records two zero-cost transfers in GW4, so the correct GW5 state is 1 free transfer.

Root cause identified on main: `src/update_fpl_data.py` writes `data/chatgpt/manager_history.json` with only `past_seasons` and `chips`, while `src/fpl_transfers.py::derive_free_transfer_state()` expects current-season rows under `manager_history["current"]`.

## Required fix

- Preserve current-season manager history in `manager_history.json`.
- Make free-transfer derivation fail safe rather than silently assuming zero historical transfers when required current-season history is absent.
- Add regression coverage for GW1 0 transfers, GW2 0 transfers, GW3 Wildcard preserving banked FTs, GW4 two free transfers used, expected GW5 available free transfers = 1.
- Add dataset-generation coverage proving `manager_history.json` contains `current`, `past_seasons`, and `chips`.
- Ensure downstream transfer optimisation prices a second GW5 transfer at a 4-point hit when only one FT is available.
- Keep player-sim-2.0 production governance unchanged.
- Update PROJECT_STATE.md and ROADMAP.md with the hotfix once validated.

This file is only a task handoff for the hotfix branch and should be removed before the PR is finalised.
