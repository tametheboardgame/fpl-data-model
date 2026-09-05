from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Missing 3.4 patch anchor in {path}: {old[:180]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "src/component_player_simulator.py",
    'COMPONENT_MODEL_VERSION = "player-sim-3.3-candidate"',
    'COMPONENT_MODEL_VERSION = "player-sim-3.4-candidate"',
)
replace_once(
    "src/component_player_simulator.py",
    '''    usage_prior_weight = math.sqrt(\n        max(0.0, min(1.0, 1.0 - fixtures_6 / 6.0))\n    )\n    effective_start_rate_prior = (''',
    '''    time_prior_weight = math.sqrt(\n        max(0.0, min(1.0, 1.0 - fixtures_6 / 6.0))\n    )\n    previous_season_minutes = max(0.0, number(base_inputs.get("previous_season_minutes")))\n    role_prior_confidence = clamp(previous_season_minutes / (38 * 60), 0, 1)\n    if player_start_rate_prior >= position_start_rate_prior:\n        role_prior_divergence = (\n            (player_start_rate_prior - position_start_rate_prior)\n            / max(1e-9, 1.0 - position_start_rate_prior)\n        )\n    else:\n        role_prior_divergence = (\n            (position_start_rate_prior - player_start_rate_prior)\n            / max(1e-9, position_start_rate_prior)\n        )\n    role_prior_divergence = clamp(role_prior_divergence, 0, 1)\n    usage_prior_weight = (\n        time_prior_weight * role_prior_confidence * role_prior_divergence\n    )\n    effective_start_rate_prior = (''',
)
replace_once(
    "src/component_player_simulator.py",
    '''        "usage_prior_weight": usage_prior_weight,\n        "effective_start_rate_prior": clamp(effective_start_rate_prior, 0, 1),''',
    '''        "usage_prior_weight": usage_prior_weight,\n        "role_prior_confidence": role_prior_confidence,\n        "role_prior_divergence": role_prior_divergence,\n        "effective_start_rate_prior": clamp(effective_start_rate_prior, 0, 1),''',
)

replace_once(
    "src/build_fpl_model.py",
    '    "component_usage_prior_weight",\n    "component_expected_minutes",',
    '    "component_usage_prior_weight",\n    "component_role_prior_confidence",\n    "component_role_prior_divergence",\n    "component_expected_minutes",',
)
replace_once(
    "src/build_fpl_model.py",
    '''                "component_usage_prior_weight": round(\n                    number(component_base_inputs.get("usage_prior_weight")), 4\n                ),\n                "component_expected_minutes": round(''',
    '''                "component_usage_prior_weight": round(\n                    number(component_base_inputs.get("usage_prior_weight")), 4\n                ),\n                "component_role_prior_confidence": round(\n                    number(component_base_inputs.get("role_prior_confidence")), 4\n                ),\n                "component_role_prior_divergence": round(\n                    number(component_base_inputs.get("role_prior_divergence")), 4\n                ),\n                "component_expected_minutes": round(''',
)

replace_once(
    "src/backtest_fpl_model.py",
    '''        inputs["player_appearance_rate_prior"] = clamp(\n            max(\n                number(usage_prior.get("player_start_rate_prior")),\n                number(usage_prior.get("player_appearance_rate_prior")),\n            ),\n            0,\n            1,\n        )\n    # Defensive-contribution points did not exist in the seasons under test.''',
    '''        inputs["player_appearance_rate_prior"] = clamp(\n            max(\n                number(usage_prior.get("player_start_rate_prior")),\n                number(usage_prior.get("player_appearance_rate_prior")),\n            ),\n            0,\n            1,\n        )\n        inputs["previous_season_minutes"] = max(\n            0.0, number(usage_prior.get("previous_season_minutes"))\n        )\n    # Defensive-contribution points did not exist in the seasons under test.''',
)

replace_once(
    "tests/test_component_early_season_prior.py",
    '''            "expected_minutes": 90,\n        }\n        prior = {"start_rate": 0.43, "appearance_rate": 0.62}''',
    '''            "expected_minutes": 90,\n            "previous_season_minutes": 2280,\n        }\n        prior = {"start_rate": 0.43, "appearance_rate": 0.62}''',
)
replace_once(
    "tests/test_component_early_season_prior.py",
    '        self.assertAlmostEqual(nailed["usage_prior_weight"], (2 / 3) ** 0.5, places=3)',
    '''        expected_divergence = (0.92 - 0.43) / (1 - 0.43)\n        self.assertAlmostEqual(\n            nailed["usage_prior_weight"],\n            (2 / 3) ** 0.5 * expected_divergence,\n            places=3,\n        )\n        self.assertEqual(nailed["role_prior_confidence"], 1.0)''',
)

path = Path("tests/test_component_early_season_prior.py")
text = path.read_text(encoding="utf-8")
anchor = '    def test_player_specific_usage_prior_fades_out_after_six_fixtures(self) -> None:\n'
new_test = '''    def test_low_evidence_or_average_role_prior_has_little_influence(self) -> None:\n        feature = {\n            "fixtures_6": 2,\n            "start_rate_6": 1.0,\n            "appearance_rate_6": 1.0,\n            "starter_average_minutes_6": 86,\n            "substitute_average_minutes_6": 18,\n            "minutes_6": 172,\n            "minutes_10": 172,\n        }\n        prior = {"start_rate": 0.43, "appearance_rate": 0.62}\n        base = {\n            "position": "FWD",\n            "availability_probability": 1.0,\n            "start_probability": 1.0,\n            "appearance_probability": 1.0,\n            "expected_minutes": 86,\n        }\n        low_evidence = build_component_inputs(\n            {\n                **base,\n                "previous_season_minutes": 300,\n                "player_start_rate_prior": 0.92,\n                "player_appearance_rate_prior": 0.97,\n            },\n            feature,\n            prior,\n        )\n        average_role = build_component_inputs(\n            {\n                **base,\n                "previous_season_minutes": 2280,\n                "player_start_rate_prior": 0.43,\n                "player_appearance_rate_prior": 0.62,\n            },\n            feature,\n            prior,\n        )\n        strong_role = build_component_inputs(\n            {\n                **base,\n                "previous_season_minutes": 2280,\n                "player_start_rate_prior": 0.92,\n                "player_appearance_rate_prior": 0.97,\n            },\n            feature,\n            prior,\n        )\n        self.assertLess(low_evidence["usage_prior_weight"], strong_role["usage_prior_weight"] * 0.2)\n        self.assertEqual(average_role["usage_prior_weight"], 0.0)\n        self.assertGreater(strong_role["expected_minutes"], low_evidence["expected_minutes"] + 3)\n\n'''
if anchor not in text:
    raise SystemExit("3.4 evidence regression anchor missing")
path.write_text(text.replace(anchor, new_test + anchor, 1), encoding="utf-8")
