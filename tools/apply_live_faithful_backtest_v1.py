from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Missing live-faithful patch anchor in {path}: {old[:180]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "src/backtest_fpl_model.py",
    '    "prior_fixture_rows",\n    "actual_minutes",',
    '    "prior_fixture_rows",\n    "previous_season_minutes",\n    "previous_season_start_rate",\n    "control_usage_prior_weight",\n    "actual_minutes",',
)

replace_once(
    "src/backtest_fpl_model.py",
    '''def player_key(row: dict[str, Any]) -> str:\n    element = str(row.get("element") or "").strip()\n    return element if element else str(row.get("player_name") or "").strip().lower()\n\n\ndef position_code''',
    '''def player_key(row: dict[str, Any]) -> str:\n    element = str(row.get("element") or "").strip()\n    return element if element else str(row.get("player_name") or "").strip().lower()\n\n\ndef cross_season_player_key(row: dict[str, Any]) -> str:\n    return str(row.get("player_name") or "").strip().casefold()\n\n\ndef previous_season_name(season: str) -> str:\n    parts = str(season).split("-")\n    if len(parts) != 2:\n        return ""\n    try:\n        start = int(parts[0])\n    except ValueError:\n        return ""\n    return f"{start - 1}-{start % 100:02d}"\n\n\ndef previous_season_usage(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:\n    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)\n    for row in rows:\n        key = cross_season_player_key(row)\n        if key:\n            grouped[key].append(row)\n    output: dict[str, dict[str, float]] = {}\n    for key, player_rows in grouped.items():\n        minutes = sum(number(row.get("minutes")) for row in player_rows)\n        starts = sum(\n            number(row.get("starts")) > 0 or number(row.get("minutes")) >= 60\n            for row in player_rows\n        )\n        start_rate = clamp(starts / 38, 0, 1)\n        appearance_rate = clamp(max(start_rate, minutes / (38 * 60)), 0, 1)\n        output[key] = {\n            "previous_season_minutes": minutes,\n            "previous_season_average_minutes": min(90, minutes / 38),\n            "previous_season_start_rate": start_rate,\n            "previous_season_appearance_rate": appearance_rate,\n        }\n    return output\n\n\ndef position_code''',
)

replace_once(
    "src/backtest_fpl_model.py",
    '''def fixture_prediction(\n    row: dict[str, Any],\n    history: list[dict[str, Any]],\n    team_histories: dict[str, list[dict[str, Any]]],\n    opponent: str,\n    *,\n    simulations: int,\n) -> dict[str, Any]:''',
    '''def fixture_prediction(\n    row: dict[str, Any],\n    history: list[dict[str, Any]],\n    team_histories: dict[str, list[dict[str, Any]]],\n    opponent: str,\n    usage_prior: dict[str, Any] | None = None,\n    *,\n    simulations: int,\n) -> dict[str, Any]:''',
)

replace_once(
    "src/backtest_fpl_model.py",
    '''    average_minutes = 0.7 * number(metrics_6.get("average_minutes_6")) + 0.3 * number(\n        metrics_3.get("average_minutes_3")\n    )\n    start_probability = clamp(\n        0.7 * number(metrics_6.get("start_rate_6"))\n        + 0.3 * number(metrics_3.get("start_rate_3")),\n        0,\n        1,\n    )\n    appearance_probability = clamp(\n        max(\n            start_probability,\n            0.7 * number(metrics_6.get("appearance_rate_6"))\n            + 0.3 * number(metrics_3.get("appearance_rate_3")),\n        ),\n        0,\n        1,\n    )''',
    '''    current_average_minutes = (\n        0.7 * number(metrics_6.get("average_minutes_6"))\n        + 0.3 * number(metrics_3.get("average_minutes_3"))\n    )\n    current_start_rate = clamp(\n        0.7 * number(metrics_6.get("start_rate_6"))\n        + 0.3 * number(metrics_3.get("start_rate_3")),\n        0,\n        1,\n    )\n    current_appearance_rate = clamp(\n        max(\n            current_start_rate,\n            0.7 * number(metrics_6.get("appearance_rate_6"))\n            + 0.3 * number(metrics_3.get("appearance_rate_3")),\n        ),\n        0,\n        1,\n    )\n    fixtures_6 = integer(metrics_6.get("fixtures_6"))\n    control_usage_prior_weight = 0.0\n    if usage_prior and number(usage_prior.get("previous_season_minutes")) > 0:\n        current_weight = min(1.0, fixtures_6 / 6)\n        control_usage_prior_weight = 1.0 - current_weight\n        average_minutes = (\n            current_weight * current_average_minutes\n            + control_usage_prior_weight\n            * number(usage_prior.get("previous_season_average_minutes"))\n        )\n        start_probability = clamp(\n            current_weight * current_start_rate\n            + control_usage_prior_weight\n            * number(usage_prior.get("previous_season_start_rate")),\n            0,\n            1,\n        )\n        appearance_probability = clamp(\n            max(\n                start_probability,\n                current_weight * current_appearance_rate\n                + control_usage_prior_weight\n                * number(usage_prior.get("previous_season_appearance_rate")),\n            ),\n            0,\n            1,\n        )\n    else:\n        average_minutes = current_average_minutes\n        start_probability = current_start_rate\n        appearance_probability = current_appearance_rate''',
)

replace_once(
    "src/backtest_fpl_model.py",
    '    return {"legacy": legacy, "component": component}\n\n\ndef walk_forward_season(',
    '''    return {\n        "legacy": legacy,\n        "component": component,\n        "previous_season_minutes": number((usage_prior or {}).get("previous_season_minutes")),\n        "previous_season_start_rate": number((usage_prior or {}).get("previous_season_start_rate")),\n        "control_usage_prior_weight": control_usage_prior_weight,\n    }\n\n\ndef walk_forward_season(''',
)

replace_once(
    "src/backtest_fpl_model.py",
    '''def walk_forward_season(\n    season_rows: list[dict[str, Any]], *, simulations: int = BACKTEST_SIMULATIONS\n) -> list[dict[str, Any]]:\n    by_gameweek: dict[int, list[dict[str, Any]]] = defaultdict(list)''',
    '''def walk_forward_season(\n    season_rows: list[dict[str, Any]],\n    previous_season_rows: list[dict[str, Any]] | None = None,\n    *,\n    simulations: int = BACKTEST_SIMULATIONS,\n) -> list[dict[str, Any]]:\n    usage_priors = previous_season_usage(previous_season_rows or [])\n    by_gameweek: dict[int, list[dict[str, Any]]] = defaultdict(list)''',
)

replace_once(
    "src/backtest_fpl_model.py",
    '''                        team_histories,\n                        opponent,\n                        simulations=simulations,''',
    '''                        team_histories,\n                        opponent,\n                        usage_priors.get(cross_season_player_key(sample)),\n                        simulations=simulations,''',
)

replace_once(
    "src/backtest_fpl_model.py",
    '''                "prior_fixture_rows": len(history),\n                "actual_minutes": round(actual_minutes, 2),''',
    '''                "prior_fixture_rows": len(history),\n                "previous_season_minutes": round(\n                    number(simulation_rows[0].get("previous_season_minutes"))\n                    if simulation_rows\n                    else 0,\n                    2,\n                ),\n                "previous_season_start_rate": round(\n                    number(simulation_rows[0].get("previous_season_start_rate"))\n                    if simulation_rows\n                    else 0,\n                    4,\n                ),\n                "control_usage_prior_weight": round(\n                    number(simulation_rows[0].get("control_usage_prior_weight"))\n                    if simulation_rows\n                    else 0,\n                    4,\n                ),\n                "actual_minutes": round(actual_minutes, 2),''',
)

replace_once(
    "src/backtest_fpl_model.py",
    '''    seasons = seasons or DEFAULT_SEASONS\n    historical_path = data_dir / "history" / "historical_player_gameweeks.csv.gz"\n    rows = read_historical(historical_path, seasons)\n    by_season: dict[str, list[dict[str, Any]]] = defaultdict(list)''',
    '''    seasons = seasons or DEFAULT_SEASONS\n    historical_path = data_dir / "history" / "historical_player_gameweeks.csv.gz"\n    prior_context_seasons = [\n        previous_season_name(season)\n        for season in seasons\n        if previous_season_name(season)\n    ]\n    source_seasons = list(dict.fromkeys([*prior_context_seasons, *seasons]))\n    rows = read_historical(historical_path, source_seasons)\n    by_season: dict[str, list[dict[str, Any]]] = defaultdict(list)''',
)

replace_once(
    "src/backtest_fpl_model.py",
    '''        predictions.extend(\n            walk_forward_season(by_season.get(season, []), simulations=simulations)\n        )''',
    '''        predictions.extend(\n            walk_forward_season(\n                by_season.get(season, []),\n                by_season.get(previous_season_name(season), []),\n                simulations=simulations,\n            )\n        )''',
)

replace_once(
    "src/backtest_fpl_model.py",
    '''        "held_out_season": HELD_OUT_SEASON,\n        "historical_source_rows": len(rows),''',
    '''        "held_out_season": HELD_OUT_SEASON,\n        "prior_context_seasons": prior_context_seasons,\n        "historical_source_rows": len(rows),''',
)

# Add regressions that prove the historical control now follows the same
# early-season previous-season usage blend as the live projection layer while
# the unchanged component arm remains independent of that signal after current
# season fixtures exist.
path = Path("tests/test_backtest_fpl_model.py")
text = path.read_text(encoding="utf-8")
anchor = '    def test_end_to_end_backtest_writes_held_out_report(self) -> None:\n'
new_tests = '''    def test_previous_season_usage_is_used_by_control_then_fades_by_fixture_six(self) -> None:\n        rows = synthetic_rows("2024-25")\n        nailed_prior = []\n        fringe_prior = []\n        for fixture in range(1, 39):\n            for player in ("Alpha", "Bravo", "Charlie", "Delta"):\n                base = {\n                    "player_name": player,\n                    "minutes": 90,\n                    "starts": 1,\n                }\n                nailed_prior.append(dict(base))\n                fringe_prior.append(\n                    {\n                        **base,\n                        "minutes": 90 if player != "Alpha" or fixture <= 2 else 0,\n                        "starts": 1 if player != "Alpha" or fixture <= 2 else 0,\n                    }\n                )\n        nailed = walk_forward_season(rows, nailed_prior, simulations=200)\n        fringe = walk_forward_season(rows, fringe_prior, simulations=200)\n        nailed_gw4 = next(\n            row for row in nailed if row["gameweek"] == 4 and row["player_name"] == "Alpha"\n        )\n        fringe_gw4 = next(\n            row for row in fringe if row["gameweek"] == 4 and row["player_name"] == "Alpha"\n        )\n        self.assertEqual(nailed_gw4["control_usage_prior_weight"], 0.5)\n        self.assertGreater(nailed_gw4["predicted_minutes"], fringe_gw4["predicted_minutes"] + 20)\n        self.assertEqual(\n            nailed_gw4["component_predicted_minutes"],\n            fringe_gw4["component_predicted_minutes"],\n        )\n\n        nailed_gw7 = next(\n            row for row in nailed if row["gameweek"] == 7 and row["player_name"] == "Alpha"\n        )\n        fringe_gw7 = next(\n            row for row in fringe if row["gameweek"] == 7 and row["player_name"] == "Alpha"\n        )\n        self.assertEqual(nailed_gw7["control_usage_prior_weight"], 0.0)\n        self.assertEqual(nailed_gw7["predicted_minutes"], fringe_gw7["predicted_minutes"])\n\n'''
if anchor not in text:
    raise SystemExit("Missing backtest test anchor")
path.write_text(text.replace(anchor, new_tests + anchor, 1), encoding="utf-8")
