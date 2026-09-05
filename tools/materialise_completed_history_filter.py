from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Expected patch anchor not found in {path}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


build = Path("src/build_fpl_model.py")
tests = Path("tests/test_build_fpl_model.py")

replace_once(
    build,
    '\n\ndef build_player_features(\n    players: list[dict[str, Any]], fixture_history: list[dict[str, Any]]\n) -> list[dict[str, Any]]:\n',
    '''\n\ndef completed_fixture_history(\n    fixture_history: list[dict[str, Any]], fixtures: list[dict[str, Any]]\n) -> list[dict[str, Any]]:\n    """Return only player-history rows whose official fixture is complete.\n\n    The live element-summary endpoint can expose a current-Gameweek history row\n    after the FPL deadline but before that player's match has finished. Treating\n    those zero/partial rows as completed appearances dilutes minutes, starts and\n    team-form rates. Production features therefore admit history only when the\n    matching fixture has `finished=true`.\n    """\n\n    finished_fixture_ids = {\n        integer(row.get("fixture_id"))\n        for row in fixtures\n        if truthy(row.get("finished"))\n    }\n    return [\n        row\n        for row in fixture_history\n        if integer(row.get("fixture")) in finished_fixture_ids\n    ]\n\n\ndef build_player_features(\n    players: list[dict[str, Any]], fixture_history: list[dict[str, Any]]\n) -> list[dict[str, Any]]:\n''',
)

replace_once(
    build,
    '    player_features = build_player_features(players, fixture_history)\n    team_features = build_team_features(teams, fixture_history, fixtures)\n',
    '    completed_history = completed_fixture_history(fixture_history, fixtures)\n    player_features = build_player_features(players, completed_history)\n    team_features = build_team_features(teams, completed_history, fixtures)\n',
)

replace_once(
    build,
    '        "player_feature_rows": len(player_features),\n        "team_feature_rows": len(team_features),\n',
    '        "player_feature_rows": len(player_features),\n        "team_feature_rows": len(team_features),\n        "raw_fixture_history_rows": len(fixture_history),\n        "completed_fixture_history_rows": len(completed_history),\n',
)

replace_once(
    tests,
    '    build_model,\n    build_player_features,\n',
    '    build_model,\n    build_player_features,\n    completed_fixture_history,\n',
)

anchor = '''    def test_builds_rolling_features_and_projection(self) -> None:\n'''
new_test = '''    def test_unfinished_current_gameweek_history_is_excluded_from_live_features(self) -> None:\n        history = [\n            self.history[0],\n            self.history[1],\n            {\n                **self.history[2],\n                "fixture": 99,\n                "round": 3,\n                "kickoff_time": "2026-01-10T15:00:00Z",\n                "minutes": 0,\n                "starts": 0,\n                "total_points": 0,\n                "expected_goals": 0,\n                "expected_assists": 0,\n                "expected_goal_involvements": 0,\n            },\n        ]\n        fixtures = [\n            {"fixture_id": 1, "finished": True},\n            {"fixture_id": 2, "finished": True},\n            {"fixture_id": 99, "finished": False},\n        ]\n\n        completed = completed_fixture_history(history, fixtures)\n        player_features = build_player_features(self.players, completed)\n        team_features = build_team_features(self.teams, completed)\n\n        self.assertEqual([row["fixture"] for row in completed], [1, 2])\n        self.assertEqual(player_features[0]["history_fixture_count"], 2)\n        self.assertEqual(player_features[0]["appearance_rate_3"], 1.0)\n        self.assertEqual(player_features[0]["start_rate_3"], 1.0)\n        self.assertEqual(player_features[0]["average_minutes_3"], 90.0)\n        self.assertEqual(team_features[0]["matches_3"], 2)\n\n'''
replace_once(tests, anchor, new_test + anchor)
