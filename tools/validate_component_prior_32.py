from __future__ import annotations

from pathlib import Path
import textwrap


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Missing 3.2 patch anchor in {path}: {old[:180]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# Reuse the already validated 3.1 base patch rather than duplicating it.
workflow = Path(
    ".github/workflows/validate-component-early-season-prior-v2.yml"
).read_text(encoding="utf-8")
marker = "          python - <<'PY'\n"
start = workflow.index(marker) + len(marker)
end = workflow.index("\n          PY\n", start)
exec(compile(textwrap.dedent(workflow[start:end]), "component-prior-v2-patch", "exec"))

replace_once(
    "src/component_player_simulator.py",
    'COMPONENT_MODEL_VERSION = "player-sim-3.1-candidate"',
    'COMPONENT_MODEL_VERSION = "player-sim-3.2-candidate"',
)
replace_once(
    "src/component_player_simulator.py",
    '''    player_appearance_rate_prior = (\n        number(base_inputs.get("player_appearance_rate_prior"))\n        if "player_appearance_rate_prior" in base_inputs\n        else number(prior.get("appearance_rate"))\n    )\n    if not fixtures_6:''',
    '''    player_appearance_rate_prior = (\n        number(base_inputs.get("player_appearance_rate_prior"))\n        if "player_appearance_rate_prior" in base_inputs\n        else number(prior.get("appearance_rate"))\n    )\n    usage_prior_strength = max(0.0, 2.0 * (1.0 - fixtures_6 / 6.0))\n    if not fixtures_6:''',
)
replace_once(
    "src/component_player_simulator.py",
    '''        smoothed_start = beta_smoothed_rate(\n            start_rate_6,\n            fixtures_6,\n            player_start_rate_prior,\n        )\n        smoothed_appearance = beta_smoothed_rate(\n            max(start_rate_6, appearance_rate_6),\n            fixtures_6,\n            max(player_start_rate_prior, player_appearance_rate_prior),\n        )''',
    '''        smoothed_start = beta_smoothed_rate(\n            start_rate_6,\n            fixtures_6,\n            player_start_rate_prior,\n            prior_strength=usage_prior_strength,\n        )\n        smoothed_appearance = beta_smoothed_rate(\n            max(start_rate_6, appearance_rate_6),\n            fixtures_6,\n            max(player_start_rate_prior, player_appearance_rate_prior),\n            prior_strength=usage_prior_strength,\n        )''',
)
replace_once(
    "src/component_player_simulator.py",
    '''        "position": position,\n        "appearance_probability": clamp(appearance_probability, 0, 1),''',
    '''        "position": position,\n        "usage_prior_strength": usage_prior_strength,\n        "appearance_probability": clamp(appearance_probability, 0, 1),''',
)

replace_once(
    "src/build_fpl_model.py",
    '''    "component_start_rate_prior",\n    "component_appearance_rate_prior",\n    "component_expected_minutes",''',
    '''    "component_start_rate_prior",\n    "component_appearance_rate_prior",\n    "component_usage_prior_strength",\n    "component_expected_minutes",''',
)
replace_once(
    "src/build_fpl_model.py",
    '''                "component_appearance_rate_prior": round(\n                    number(component_base_inputs.get("player_appearance_rate_prior")), 4\n                ),\n                "component_expected_minutes": round(''',
    '''                "component_appearance_rate_prior": round(\n                    number(component_base_inputs.get("player_appearance_rate_prior")), 4\n                ),\n                "component_usage_prior_strength": round(\n                    number(component_base_inputs.get("usage_prior_strength")), 4\n                ),\n                "component_expected_minutes": round(''',
)

replace_once(
    "tests/test_component_early_season_prior.py",
    '        self.assertLess(fringe["start_probability"], 0.6)\n        self.assertGreater(nailed["expected_minutes"], fringe["expected_minutes"] + 25)',
    '        self.assertLess(fringe["start_probability"], 0.7)\n        self.assertAlmostEqual(nailed["usage_prior_strength"], 4 / 3, places=3)\n        self.assertGreater(nailed["expected_minutes"], fringe["expected_minutes"] + 20)',
)
replace_once(
    "tests/test_component_early_season_prior.py",
    '        self.assertGreater(\n            nailed_gw4["component_predicted_minutes"],\n            fringe_gw4["component_predicted_minutes"] + 20,\n        )',
    '        self.assertGreater(\n            nailed_gw4["component_predicted_minutes"],\n            fringe_gw4["component_predicted_minutes"] + 15,\n        )',
)

target = Path("tests/test_component_early_season_prior.py")
text = target.read_text(encoding="utf-8")
anchor = '    def test_live_projection_wires_previous_season_usage_into_component(self) -> None:\n'
new_test = '''    def test_player_specific_usage_prior_fades_out_after_six_fixtures(self) -> None:\n        feature = {\n            "fixtures_6": 6,\n            "start_rate_6": 0.5,\n            "appearance_rate_6": 0.75,\n            "starter_average_minutes_6": 82,\n            "substitute_average_minutes_6": 18,\n            "minutes_6": 360,\n            "minutes_10": 360,\n        }\n        base = {\n            "position": "FWD",\n            "availability_probability": 1.0,\n            "start_probability": 0.5,\n            "appearance_probability": 0.75,\n            "expected_minutes": 50,\n        }\n        prior = {"start_rate": 0.43, "appearance_rate": 0.62}\n        formerly_nailed = build_component_inputs(\n            {\n                **base,\n                "player_start_rate_prior": 0.95,\n                "player_appearance_rate_prior": 1.0,\n            },\n            feature,\n            prior,\n        )\n        formerly_fringe = build_component_inputs(\n            {\n                **base,\n                "player_start_rate_prior": 0.05,\n                "player_appearance_rate_prior": 0.10,\n            },\n            feature,\n            prior,\n        )\n        self.assertEqual(formerly_nailed["usage_prior_strength"], 0.0)\n        self.assertEqual(formerly_fringe["usage_prior_strength"], 0.0)\n        self.assertAlmostEqual(\n            formerly_nailed["start_probability"],\n            formerly_fringe["start_probability"],\n            places=8,\n        )\n        self.assertAlmostEqual(\n            formerly_nailed["expected_minutes"],\n            formerly_fringe["expected_minutes"],\n            places=8,\n        )\n\n'''
if anchor not in text:
    raise SystemExit("Fade-out regression anchor missing")
target.write_text(text.replace(anchor, new_test + anchor, 1), encoding="utf-8")
