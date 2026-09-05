from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Expected patch anchor not found in {path}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


build = Path("src/build_fpl_model.py")
decisions = Path("src/fpl_decisions.py")

replace_once(
    build,
    '            "previous_season_minutes": number(\n                rows[0].get("previous_season_minutes") if rows else 0\n            ),\n            "bonus_transition_multiplier": (',
    '            "previous_season_minutes": number(\n                rows[0].get("previous_season_minutes") if rows else 0\n            ),\n            "current_season_fixture_count": integer(\n                feature_by_player.get(player_id, {}).get("history_fixture_count")\n            ),\n            "bonus_transition_multiplier": (',
)

replace_once(
    decisions,
    '    completed_gameweeks = max(0, integer(target_gameweek) - 1)\n    minutes_penalty = 0.0\n    observed_usage = None\n    if completed_gameweeks and expected_minutes > 0:\n        start_rate = clamp(\n            number(player.get("starts")) / completed_gameweeks, 0.0, 1.0\n        )\n        minute_share = clamp(\n            number(player.get("minutes")) / (90 * completed_gameweeks),\n            0.0,\n            1.0,\n        )',
    '    completed_gameweeks = max(0, integer(target_gameweek) - 1)\n    observed_fixture_count = integer(horizon.get("current_season_fixture_count"))\n    if observed_fixture_count <= 0:\n        observed_fixture_count = completed_gameweeks\n    minutes_penalty = 0.0\n    observed_usage = None\n    if observed_fixture_count and expected_minutes > 0:\n        start_rate = clamp(\n            number(player.get("starts")) / observed_fixture_count, 0.0, 1.0\n        )\n        minute_share = clamp(\n            number(player.get("minutes")) / (90 * observed_fixture_count),\n            0.0,\n            1.0,\n        )',
)

replace_once(
    decisions,
    '    control_points = horizon_value(horizon, 1, "control_expected_points")\n    component_points = horizon_value(\n        horizon, 1, "component_expected_points"\n    )\n    model_disagreement = (\n        abs(control_points - component_points)\n        if control_points > 0 and component_points > 0\n        else 0.0\n    )',
    '    control_points = horizon_value(horizon, 1, "control_expected_points")\n    component_points = horizon_value(\n        horizon, 1, "component_expected_points"\n    )\n    component_mean_active = (\n        str(horizon.get("ensemble_status") or "")\n        == "recommended_for_live_promotion"\n        and number(horizon.get("ensemble_point_weight")) > 0\n    )\n    model_disagreement = (\n        abs(control_points - component_points)\n        if component_mean_active and control_points > 0 and component_points > 0\n        else 0.0\n    )',
)

replace_once(
    decisions,
    '        "component_expected_minutes_next_1": round(component_expected_minutes, 2),\n        "observed_usage_rate": (',
    '        "component_expected_minutes_next_1": round(component_expected_minutes, 2),\n        "observed_fixture_count": observed_fixture_count,\n        "observed_usage_rate": (',
)
