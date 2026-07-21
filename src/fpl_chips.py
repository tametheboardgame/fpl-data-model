from __future__ import annotations

from collections import Counter
from typing import Any


CHIP_NAMES = ("wildcard", "freehit", "bboost", "3xc")


def integer(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def derive_chip_state(
    manager_history: dict[str, Any] | None,
    season: str | None,
    rules: dict[str, Any] | None,
    target_gameweek: int | None = None,
) -> dict[str, Any]:
    history = manager_history or {}
    chip_rows = [
        row for row in history.get("chips", []) if str(row.get("name")) in CHIP_NAMES
    ]
    used = Counter(str(row.get("name")) for row in chip_rows)
    season_rules = (rules or {}).get("seasons", {}).get(str(season), {})
    allowances = season_rules.get("allowances")
    configured = isinstance(allowances, dict)
    if not configured:
        return {
            "season": season,
            "target_gameweek": target_gameweek,
            "status": "rules_not_configured",
            "chips": {
                name: {"used": used.get(name, 0), "allowance": None, "remaining": None}
                for name in CHIP_NAMES
            },
            "periods": [],
        }

    periods = season_rules.get("periods") or []
    if target_gameweek is None:
        target_gameweek = max(
            [integer(row.get("event")) for row in history.get("current", [])] + [0]
        ) + 1
    period_states: list[dict[str, Any]] = []
    usable_remaining = Counter()
    for period in periods:
        start = integer(period.get("start_gameweek"))
        end = integer(period.get("end_gameweek"))
        period_used = Counter(
            str(row.get("name"))
            for row in chip_rows
            if start <= integer(row.get("event")) <= end
        )
        status = (
            "expired"
            if target_gameweek > end
            else "future"
            if target_gameweek < start
            else "current"
        )
        chip_state = {}
        for name in CHIP_NAMES:
            allowance = integer(period.get("allowances", {}).get(name))
            remaining = max(0, allowance - period_used.get(name, 0))
            if status != "expired":
                usable_remaining[name] += remaining
            chip_state[name] = {
                "used": period_used.get(name, 0),
                "allowance": allowance,
                "remaining": remaining if status != "expired" else 0,
                "expired_unused": remaining if status == "expired" else 0,
            }
        period_states.append(
            {
                "id": period.get("id"),
                "start_gameweek": start,
                "end_gameweek": end,
                "expires_at_deadline": period.get("expires_at_deadline"),
                "status": status,
                "chips": chip_state,
            }
        )

    chips = {}
    for name in CHIP_NAMES:
        allowance = integer(allowances.get(name))
        remaining = (
            usable_remaining[name]
            if periods
            else max(0, allowance - used.get(name, 0))
        )
        chips[name] = {
            "used": used.get(name, 0),
            "allowance": allowance,
            "remaining": remaining,
        }
    return {
        "season": season,
        "target_gameweek": target_gameweek,
        "status": "ready",
        "chips": chips,
        "periods": period_states,
        "first_set_expiry_gameweek": (
            integer(periods[0].get("end_gameweek")) if periods else None
        ),
    }
