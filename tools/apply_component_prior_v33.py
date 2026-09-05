from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Missing 3.3 patch anchor in {path}: {old[:180]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "src/component_player_simulator.py",
    'COMPONENT_MODEL_VERSION = "player-sim-3.2-candidate"',
    'COMPONENT_MODEL_VERSION = "player-sim-3.3-candidate"',
)
replace_once(
    "src/component_player_simulator.py",
    '''    usage_prior_strength = max(0.0, 2.0 * (1.0 - fixtures_6 / 6.0))\n    if not fixtures_6:''',
    '''    position_start_rate_prior = number(prior.get("start_rate"))\n    position_appearance_rate_prior = max(\n        position_start_rate_prior, number(prior.get("appearance_rate"))\n    )\n    usage_prior_weight = max(0.0, min(1.0, 1.0 - fixtures_6 / 6.0))\n    effective_start_rate_prior = (\n        position_start_rate_prior\n        + usage_prior_weight\n        * (player_start_rate_prior - position_start_rate_prior)\n    )\n    effective_appearance_rate_prior = (\n        position_appearance_rate_prior\n        + usage_prior_weight\n        * (\n            max(player_start_rate_prior, player_appearance_rate_prior)\n            - position_appearance_rate_prior\n        )\n    )\n    if not fixtures_6:''',
)
replace_once(
    "src/component_player_simulator.py",
    '''        smoothed_start = beta_smoothed_rate(\n            start_rate_6,\n            fixtures_6,\n            player_start_rate_prior,\n            prior_strength=usage_prior_strength,\n        )\n        smoothed_appearance = beta_smoothed_rate(\n            max(start_rate_6, appearance_rate_6),\n            fixtures_6,\n            max(player_start_rate_prior, player_appearance_rate_prior),\n            prior_strength=usage_prior_strength,\n        )''',
    '''        smoothed_start = beta_smoothed_rate(\n            start_rate_6,\n            fixtures_6,\n            effective_start_rate_prior,\n        )\n        smoothed_appearance = beta_smoothed_rate(\n            max(start_rate_6, appearance_rate_6),\n            fixtures_6,\n            effective_appearance_rate_prior,\n        )''',
)
replace_once(
    "src/component_player_simulator.py",
    '''        "position": position,\n        "usage_prior_strength": usage_prior_strength,\n        "appearance_probability": clamp(appearance_probability, 0, 1),''',
    '''        "position": position,\n        "usage_prior_weight": usage_prior_weight,\n        "effective_start_rate_prior": clamp(effective_start_rate_prior, 0, 1),\n        "effective_appearance_rate_prior": clamp(\n            effective_appearance_rate_prior, 0, 1\n        ),\n        "appearance_probability": clamp(appearance_probability, 0, 1),''',
)

replace_once(
    "src/build_fpl_model.py",
    '    "component_usage_prior_strength",',
    '    "component_usage_prior_weight",',
)
replace_once(
    "src/build_fpl_model.py",
    '''                "component_usage_prior_strength": round(\n                    number(component_base_inputs.get("usage_prior_strength")), 4\n                ),''',
    '''                "component_usage_prior_weight": round(\n                    number(component_base_inputs.get("usage_prior_weight")), 4\n                ),''',
)

replace_once(
    "tests/test_component_early_season_prior.py",
    '        self.assertAlmostEqual(nailed["usage_prior_strength"], 4 / 3, places=3)',
    '        self.assertAlmostEqual(nailed["usage_prior_weight"], 2 / 3, places=3)',
)
replace_once(
    "tests/test_component_early_season_prior.py",
    '        self.assertEqual(formerly_nailed["usage_prior_strength"], 0.0)\n        self.assertEqual(formerly_fringe["usage_prior_strength"], 0.0)',
    '        self.assertEqual(formerly_nailed["usage_prior_weight"], 0.0)\n        self.assertEqual(formerly_fringe["usage_prior_weight"], 0.0)',
)

path = Path("tests/test_component_early_season_prior.py")
text = path.read_text(encoding="utf-8")
anchor = '    def test_player_specific_usage_prior_fades_out_after_six_fixtures(self) -> None:\n'
new_test = '''    def test_missing_player_usage_prior_preserves_positional_smoothing(self) -> None:\n        feature = {\n            "fixtures_6": 2,\n            "start_rate_6": 1.0,\n            "appearance_rate_6": 1.0,\n            "starter_average_minutes_6": 84,\n            "substitute_average_minutes_6": 18,\n            "minutes_6": 168,\n            "minutes_10": 168,\n        }\n        base = {\n            "position": "FWD",\n            "availability_probability": 1.0,\n            "start_probability": 1.0,\n            "appearance_probability": 1.0,\n            "expected_minutes": 84,\n        }\n        prior = {"start_rate": 0.43, "appearance_rate": 0.62}\n        implicit = build_component_inputs(base, feature, prior)\n        explicit = build_component_inputs(\n            {\n                **base,\n                "player_start_rate_prior": 0.43,\n                "player_appearance_rate_prior": 0.62,\n            },\n            feature,\n            prior,\n        )\n        self.assertAlmostEqual(implicit["start_probability"], explicit["start_probability"], places=8)\n        self.assertAlmostEqual(implicit["expected_minutes"], explicit["expected_minutes"], places=8)\n\n'''
if anchor not in text:
    raise SystemExit("3.3 fallback regression anchor missing")
path.write_text(text.replace(anchor, new_test + anchor, 1), encoding="utf-8")
