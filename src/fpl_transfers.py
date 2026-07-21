from __future__ import annotations

from typing import Any


TRANSFER_CHIPS = {"wildcard", "freehit"}


def integer(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def derive_free_transfer_state(
    manager_history: dict[str, Any] | None,
    target_gameweek: int | None,
    season_rules: dict[str, Any] | None,
) -> dict[str, Any]:
    transfer_rules = (season_rules or {}).get("transfer_rules")
    if not isinstance(transfer_rules, dict):
        return {
            "status": "rules_not_configured",
            "target_gameweek": target_gameweek,
            "available": None,
            "maximum": None,
            "hit_cost": None,
        }

    maximum = integer(transfer_rules.get("maximum_free_transfers")) or 5
    hit_cost = integer(transfer_rules.get("hit_cost")) or 4
    history = manager_history or {}
    rows = {
        integer(row.get("event")): row
        for row in history.get("current", [])
        if integer(row.get("event"))
    }
    chip_by_event = {
        integer(row.get("event")): str(row.get("name"))
        for row in history.get("chips", [])
        if integer(row.get("event"))
    }
    if not target_gameweek:
        target_gameweek = max(rows, default=0) + 1 if rows else 1

    available = 0
    trace: list[dict[str, Any]] = []
    top_ups = {
        integer(gameweek): integer(value)
        for gameweek, value in transfer_rules.get("free_transfer_top_ups", {}).items()
    }
    for gameweek in range(1, max(1, target_gameweek)):
        if gameweek in top_ups:
            available = min(maximum, top_ups[gameweek])
        row = rows.get(gameweek, {})
        chip = chip_by_event.get(gameweek)
        transfers = integer(row.get("event_transfers"))
        paid = min(transfers, integer(row.get("event_transfers_cost")) // hit_cost)
        free_used = min(available, max(0, transfers - paid))
        before = available
        if chip in TRANSFER_CHIPS:
            after = available
        else:
            after = min(maximum, max(0, available - free_used) + 1)
        trace.append(
            {
                "gameweek": gameweek,
                "available_before": before,
                "transfers": transfers,
                "paid_transfers": paid,
                "chip": chip,
                "available_after": after,
            }
        )
        available = after

    if target_gameweek in top_ups:
        available = min(maximum, top_ups[target_gameweek])
    return {
        "status": "ready",
        "target_gameweek": target_gameweek,
        "available": available,
        "maximum": maximum,
        "hit_cost": hit_cost,
        "calculation": "Replayed from official transfer counts, hit costs and transfer-chip use.",
        "trace": trace,
    }


def transfer_hit_cost(
    transfers_required: int,
    free_transfers_available: int | None,
    hit_cost: int = 4,
) -> int | None:
    if free_transfers_available is None:
        return None
    paid = max(0, transfers_required - max(0, free_transfers_available))
    return paid * max(0, hit_cost)
