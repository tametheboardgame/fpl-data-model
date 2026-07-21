from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_RULES = {
    "season": None,
    "status": "rules_not_configured",
    "version": "fpl-2025-26",
    "defensive_contributions": {
        "enabled": True,
        "thresholds": {"GK": 0, "DEF": 10, "MID": 12, "FWD": 12},
        "points": 2,
    },
    "bonus_transition": {
        "enabled": False,
        "fade_after_player_fixtures": 0,
        "position_multipliers": {"GK": 1.0, "DEF": 1.0, "MID": 1.0, "FWD": 1.0},
    },
}


def normalise_season(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).replace("-", "/")


def load_scoring_rules(path: Path, season: str | None) -> dict[str, Any]:
    normalised = normalise_season(season)
    if not path.is_file():
        return {**DEFAULT_RULES, "season": normalised}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {**DEFAULT_RULES, "season": normalised, "status": "rules_unreadable"}
    seasons = payload.get("seasons", {})
    configured = seasons.get(normalised)
    if not isinstance(configured, dict):
        return {**DEFAULT_RULES, "season": normalised}
    return {
        **DEFAULT_RULES,
        **configured,
        "season": normalised,
        "status": "ready",
        "schema_version": payload.get("schema_version"),
    }


def bonus_transition_multiplier(
    position: str,
    fixtures_observed: int,
    rules: dict[str, Any] | None,
) -> float:
    transition = (rules or {}).get("bonus_transition", {})
    if not transition.get("enabled"):
        return 1.0
    initial = float(transition.get("position_multipliers", {}).get(position, 1.0))
    fade_after = max(1, int(transition.get("fade_after_player_fixtures") or 1))
    prior_weight = max(0.0, 1.0 - max(0, fixtures_observed) / fade_after)
    return 1.0 + (initial - 1.0) * prior_weight


def apply_bonus_transition(
    bonus_per_90: float,
    position: str,
    fixtures_observed: int,
    rules: dict[str, Any] | None,
) -> tuple[float, float]:
    multiplier = bonus_transition_multiplier(position, fixtures_observed, rules)
    return max(0.0, bonus_per_90 * multiplier), multiplier
