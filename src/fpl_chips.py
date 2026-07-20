from __future__ import annotations

from collections import Counter
from typing import Any


CHIP_NAMES = ("wildcard", "freehit", "bboost", "3xc")


def derive_chip_state(
    manager_history: dict[str, Any] | None,
    season: str | None,
    rules: dict[str, Any] | None,
) -> dict[str, Any]:
    history = manager_history or {}
    used = Counter(str(row.get("name")) for row in history.get("chips", []))
    season_rules = (rules or {}).get("seasons", {}).get(str(season), {})
    allowances = season_rules.get("allowances")
    configured = isinstance(allowances, dict)
    chips = {}
    for name in CHIP_NAMES:
        allowance = int(allowances.get(name, 0)) if configured else None
        chips[name] = {
            "used": used.get(name, 0),
            "allowance": allowance,
            "remaining": max(0, allowance - used.get(name, 0)) if configured else None,
        }
    return {
        "season": season,
        "status": "ready" if configured else "rules_not_configured",
        "chips": chips,
    }
