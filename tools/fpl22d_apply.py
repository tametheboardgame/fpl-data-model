from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1. Policy-aware production reporting.
replace_once(
    "src/build_fpl_model.py",
    "\ndef ordered_fields(rows: list[dict[str, Any]], preferred: list[str]) -> list[str]:\n",
    '''\ndef production_policy_reporting(\n    policy_path: Path,\n    ensemble_config: dict[str, Any],\n    challenger_status: str,\n) -> dict[str, Any]:\n    \"\"\"Build policy-derived user-facing model governance text.\n\n    This is deliberately sourced from the sticky production policy rather than the\n    development candidate so a rejected challenger cannot be described as live.\n    \"\"\"\n\n    policy: dict[str, Any] = {}\n    if policy_path.is_file():\n        try:\n            loaded = json.loads(policy_path.read_text(encoding=\"utf-8\"))\n            if isinstance(loaded, dict):\n                policy = loaded\n        except (json.JSONDecodeError, OSError, TypeError):\n            policy = {}\n\n    status = str(policy.get(\"status\") or ensemble_config.get(\"status\") or \"unknown\")\n    live_model = str(\n        policy.get(\"live_model_version\")\n        or ensemble_config.get(\"model_version\")\n        or MODEL_VERSION\n    )\n    point_weight = number(\n        policy.get(\"live_point_weight\")\n        if policy.get(\"live_point_weight\") is not None\n        else ensemble_config.get(\"point_weight\")\n    )\n    raw_probability_weights = (\n        policy.get(\"live_probability_weights\")\n        if isinstance(policy.get(\"live_probability_weights\"), dict)\n        else ensemble_config.get(\"probability_weights\", {})\n    )\n    probability_weights = {\n        str(threshold): number((raw_probability_weights or {}).get(str(threshold)))\n        for threshold in (6, 10, 15)\n    }\n    challenger_mode = str(\n        policy.get(\"challenger_mode\")\n        or (\"live_weighted\" if point_weight > 0 else \"shadow_only\")\n    )\n    reason = str(policy.get(\"reason\") or \"\").strip()\n    reconsideration_gate = str(policy.get(\"reconsideration_gate\") or \"\").strip() or None\n\n    policy_summary = {\n        \"status\": status,\n        \"live_model_version\": live_model,\n        \"challenger_model_version\": COMPONENT_MODEL_VERSION,\n        \"challenger_status\": challenger_status,\n        \"challenger_mode\": challenger_mode,\n        \"live_point_weight\": round(point_weight, 6),\n        \"live_probability_weights\": {\n            key: round(value, 6) for key, value in probability_weights.items()\n        },\n        \"reason\": reason or None,\n        \"reconsideration_gate\": reconsideration_gate,\n    }\n    method = (\n        f\"Production uses {live_model} for mean and haul-probability forecasts. \"\n        f\"Production policy is {status}; challenger {COMPONENT_MODEL_VERSION} is \"\n        f\"{challenger_mode} with mean weight {point_weight:.3f} and 6+/10+/15+ \"\n        f\"weights {probability_weights['6']:.3f}/{probability_weights['10']:.3f}/\"\n        f\"{probability_weights['15']:.3f}. Qualitative and timestamped external \"\n        \"context remain separately audited decision layers.\"\n    )\n    limitations = [\n        (\n            f\"Production policy status is {status}. \"\n            + (reason if reason else \"The sticky production policy governs live model selection.\")\n        ),\n        (\n            f\"The challenger {COMPONENT_MODEL_VERSION} is {challenger_mode}; its \"\n            \"diagnostic outputs remain available for audit but do not influence \"\n            \"production selections when live weights are zero.\"\n        ),\n        \"External context is source-weighted and affects the audited decision layer rather than silently changing the production model policy.\",\n        \"Expected minutes are inferred from recent starts, minutes, availability and prior-season usage unless a timestamped decision-layer signal is present.\",\n        \"Previous-season player evidence is shrunk towards positional priors and fades over the first six current-season fixtures.\",\n        \"Bonus and rare disciplinary events use simplified distributions rather than a full event-level match model.\",\n        \"Qualitative observations are prospective signals and must be timestamped before they can be evaluated honestly.\",\n    ]\n    return {\"policy\": policy_summary, \"method\": method, \"limitations\": limitations}\n\n\ndef ordered_fields(rows: list[dict[str, Any]], preferred: list[str]) -> list[str]:\n''',
)

replace_once(
    "src/build_fpl_model.py",
    '''    summary = {\n        "generated_at": generated_at,\n        "model_version": ensemble_config["model_version"],''',
    '''    policy_reporting = production_policy_reporting(\n        data_dir / "model" / "ensemble_production_policy.json",\n        ensemble_config,\n        component_candidate_status,\n    )\n    summary = {\n        "generated_at": generated_at,\n        "model_version": ensemble_config["model_version"],''',
)

replace_once(
    "src/build_fpl_model.py",
    '''        "challenger_status": component_candidate_status,\n        "season": season,''',
    '''        "challenger_status": component_candidate_status,\n        "production_policy": policy_reporting["policy"],\n        "season": season,''',
)

replace_once(
    "src/build_fpl_model.py",
    '''        "method": "Development-selected ensemble with player-specific early-season priors, separately audited control, component, qualitative and freshness-weighted external-context decision layers.",''',
    '''        "method": policy_reporting["method"],''',
)

old_limits = '''        "limitations": [\n            "The ensemble weights were fitted on 2022/23-2023/24 and passed the documented 2024/25 held-out promotion gate.",\n            "The control and component models remain available beside every ensemble recommendation for audit.",\n            "External context is source-weighted and applied only to decision support until prospective evidence justifies changing the validated ensemble.",\n            "Expected minutes are inferred from recent starts, minutes, availability and prior-season usage unless a timestamped decision-layer signal is present.",\n            "Previous-season player evidence is shrunk towards positional priors and fades over the first six current-season fixtures.",\n            "Bonus and rare disciplinary events use simplified distributions rather than a full event-level match model.",\n            "Qualitative observations are prospective signals and must be timestamped before they can be evaluated honestly.",\n        ],'''
replace_once(
    "src/build_fpl_model.py",
    old_limits,
    '''        "limitations": policy_reporting["limitations"],''',
)

# 2. Remove the stale ensemble wording from generated external-context output.
replace_once(
    "src/external_context.py",
    '''            "External signals are timestamped, source-weighted and kept separate "\n            "from the validated ensemble forecast."''',
    '''            "External signals are timestamped, source-weighted and kept separate "\n            "from production model governance; they enter only through the audited "\n            "decision layer."''',
)

# 3. Expose current-GW captain audits without changing the frozen utility.
replace_once(
    "src/fpl_decisions.py",
    'DECISION_VERSION = "fpl-decisions-2.4"',
    'DECISION_VERSION = "fpl-decisions-2.5"',
)

replace_once(
    "src/fpl_decisions.py",
    '''    multi_gameweek_plan = optimise_multi_gameweek_route(\n        fixture_projections or [],\n        [''',
    '''    multi_gameweek_plan = optimise_multi_gameweek_route(\n        fixture_projections or [],\n        [''',
)

replace_once(
    "src/fpl_decisions.py",
    '''    status = "ready" if target_gameweek and any(\n        number(row.get("decision_expected_points")) > 0 for row in evaluated\n    ) else "waiting_for_future_fixtures"''',
    '''    audit_player_ids = {integer(row.get("player_id")) for row in starters}\n    current_route_move = next(\n        (\n            move\n            for move in ((multi_gameweek_plan.get("recommended_route") or {}).get("gameweek_plan", []))\n            if integer(move.get("gameweek")) == integer(target_gameweek)\n        ),\n        {},\n    )\n    audit_player_ids.update(\n        integer(value)\n        for value in current_route_move.get("starter_player_ids", [])\n        if integer(value)\n    )\n    captain_audit_by_player = {\n        str(integer(row.get("player_id"))): row.get("captain_utility")\n        for row in evaluated\n        if integer(row.get("player_id")) in audit_player_ids\n        and isinstance(row.get("captain_utility"), dict)\n    }\n\n    status = "ready" if target_gameweek and any(\n        number(row.get("decision_expected_points")) > 0 for row in evaluated\n    ) else "waiting_for_future_fixtures"''',
)

replace_once(
    "src/fpl_decisions.py",
    '''            "alternatives": captain_pool[:5],\n            "principle": (''',
    '''            "alternatives": captain_pool[:5],\n            "player_audits": captain_audit_by_player if status == "ready" else {},\n            "scoring_basis": {\n                "reported_xpts": "mean_expected_points_only",\n                "strategic_utility_selects_captain": True,\n                "strategic_bonus_is_expected_points": False,\n            },\n            "principle": (''',
)

# 4. Carry the actual operational captain/vice basis and compact audit into the deadline report.
replace_once(
    "src/fpl_gameweek_operations.py",
    'OPERATIONS_VERSION = "fpl-gameweek-operations-1.7"',
    'OPERATIONS_VERSION = "fpl-gameweek-operations-1.8"',
)

replace_once(
    "src/fpl_gameweek_operations.py",
    '''\ndef _route_move(decision: dict[str, Any], gameweek: int) -> dict[str, Any]:\n''',
    '''\ndef _compact_captain_audit(\n    audit: dict[str, Any] | None,\n    displayed_mean_xpts: Any,\n    selection_basis: str | None,\n) -> dict[str, Any] | None:\n    if not isinstance(audit, dict):\n        if displayed_mean_xpts in {None, ""}:\n            return None\n        return {\n            "displayed_mean_xpts": round(number(displayed_mean_xpts), 3),\n            "selection_basis": selection_basis or "mean_xpts_fallback",\n            "strategic_utility_available": False,\n            "strategic_bonus_is_expected_points": False,\n        }\n    return {\n        "utility_version": audit.get("version"),\n        "player_id": integer(audit.get("player_id")) or None,\n        "displayed_mean_xpts": round(number(displayed_mean_xpts), 3),\n        "risk_adjusted_mean_input": audit.get("mean_expected_points"),\n        "strategic_score": audit.get("captain_score"),\n        "selection_basis": selection_basis or "strategic_utility",\n        "components": {\n            "bounded_strategic_bonus": audit.get("bounded_strategic_bonus"),\n            "ceiling_contribution": audit.get("ceiling_contribution"),\n            "rank_pressure_contribution": audit.get("rank_pressure_contribution"),\n            "position_uncertainty_penalty": audit.get("position_uncertainty_penalty"),\n            "defensive_exception_margin": audit.get("defensive_exception_margin"),\n            "selection_risk_penalty": audit.get("selection_risk_penalty"),\n            "expected_minutes": audit.get("expected_minutes"),\n            "availability_confidence": audit.get("availability_confidence"),\n            "points_p90": audit.get("points_p90"),\n            "probability_10_plus": audit.get("probability_10_plus"),\n            "probability_15_plus": audit.get("probability_15_plus"),\n            "ownership_percent": audit.get("ownership_percent"),\n        },\n        "strategic_utility_available": True,\n        "strategic_bonus_is_expected_points": False,\n    }\n\n\ndef _captaincy_audit(\n    decision: dict[str, Any], selection: dict[str, Any]\n) -> dict[str, Any]:\n    captaincy = decision.get("captaincy") or {}\n    audits = captaincy.get("player_audits") or {}\n    captain = selection.get("captain") or {}\n    vice = selection.get("vice_captain") or {}\n    captain_id = integer(captain.get("player_id"))\n    vice_id = integer(vice.get("player_id"))\n    return {\n        "utility_version": captaincy.get("utility_version"),\n        "captain": _compact_captain_audit(\n            audits.get(str(captain_id)),\n            captain.get("expected_points"),\n            selection.get("captain_selection_basis"),\n        ),\n        "vice_captain": _compact_captain_audit(\n            audits.get(str(vice_id)),\n            vice.get("expected_points"),\n            selection.get("vice_captain_selection_basis"),\n        ),\n        "reported_xpts_basis": "mean_expected_points_only",\n        "strategic_bonus_is_expected_points": False,\n        "principle": (\n            "Strategic captain utility selects who is doubled; ceiling, haul, ownership "\n            "and uncertainty terms are never added to displayed or route expected points."\n        ),\n    }\n\n\ndef _route_move(decision: dict[str, Any], gameweek: int) -> dict[str, Any]:\n''',
)

replace_once(
    "src/fpl_gameweek_operations.py",
    '''            "captain": _player(captain_id, players, points) if captain_id else None,\n            "vice_captain": _player(vice_id, players, points) if vice_id else None,\n            "transfers": [],''',
    '''            "captain": _player(captain_id, players, points) if captain_id else None,\n            "vice_captain": _player(vice_id, players, points) if vice_id else None,\n            "captain_selection_basis": "initial_squad_plan",\n            "vice_captain_selection_basis": "initial_squad_plan",\n            "transfers": [],''',
)

old_captain_block = '''    captain_id = (\n        route_captain_id\n        if route_captain_id in starter_ids\n        else decision_captain_id\n    )\n    if captain_id not in starter_ids:\n        captain_id = next(\n            (\n                player_id\n                for player_id in sorted(\n                    starter_ids, key=lambda item: points.get(item, 0), reverse=True\n                )\n            ),\n            0,\n        )\n    vice_id = integer(\n        ((decision.get("captaincy") or {}).get("vice_captain") or {}).get("player_id")\n    )\n    if vice_id not in starter_ids or vice_id == captain_id:\n        vice_id = next(\n            (\n                player_id\n                for player_id in sorted(starter_ids, key=lambda item: points.get(item, 0), reverse=True)\n                if player_id != captain_id\n            ),\n            0,\n        )'''
new_captain_block = '''    if route_captain_id in starter_ids:\n        captain_id = route_captain_id\n        captain_selection_basis = "route_strategic_utility"\n    else:\n        captain_id = decision_captain_id\n        captain_selection_basis = "decision_strategic_utility"\n    if captain_id not in starter_ids:\n        captain_id = next(\n            (\n                player_id\n                for player_id in sorted(\n                    starter_ids, key=lambda item: points.get(item, 0), reverse=True\n                )\n            ),\n            0,\n        )\n        captain_selection_basis = "mean_xpts_fallback"\n    vice_id = integer(\n        ((decision.get("captaincy") or {}).get("vice_captain") or {}).get("player_id")\n    )\n    vice_captain_selection_basis = "decision_strategic_utility"\n    if vice_id not in starter_ids or vice_id == captain_id:\n        vice_id = next(\n            (\n                player_id\n                for player_id in sorted(starter_ids, key=lambda item: points.get(item, 0), reverse=True)\n                if player_id != captain_id\n            ),\n            0,\n        )\n        vice_captain_selection_basis = "mean_xpts_fallback"'''
replace_once("src/fpl_gameweek_operations.py", old_captain_block, new_captain_block)

replace_once(
    "src/fpl_gameweek_operations.py",
    '''        "captain": _player(captain_id, players, points) if captain_id else None,\n        "vice_captain": _player(vice_id, players, points) if vice_id else None,\n        "transfers": transfers_public,''',
    '''        "captain": _player(captain_id, players, points) if captain_id else None,\n        "vice_captain": _player(vice_id, players, points) if vice_id else None,\n        "captain_selection_basis": captain_selection_basis,\n        "vice_captain_selection_basis": vice_captain_selection_basis,\n        "transfers": transfers_public,''',
)

replace_once(
    "src/fpl_gameweek_operations.py",
    '''            "captain": _player(captain_id, players, wildcard_points),\n            "vice_captain": _player(vice_id, players, wildcard_points) if vice_id else None,\n            "transfers": [],''',
    '''            "captain": _player(captain_id, players, wildcard_points),\n            "vice_captain": _player(vice_id, players, wildcard_points) if vice_id else None,\n            "captain_selection_basis": "chip_strategic_utility",\n            "vice_captain_selection_basis": "mean_xpts_fallback",\n            "transfers": [],''',
)

replace_once(
    "src/fpl_gameweek_operations.py",
    '''        "recommendation": selection,\n        "chip_recommendation":''',
    '''        "recommendation": selection,\n        "captaincy_audit": _captaincy_audit(decision, selection),\n        "chip_recommendation":''',
)

replace_once(
    "src/fpl_gameweek_operations.py",
    '''        lines.extend(["", f"Captain: {captain.get('web_name') or 'Not available'}", f"Vice-captain: {vice.get('web_name') or 'Not available'}", "", "## Bench order", ""])''',
    '''        captain_audit = (report.get("captaincy_audit") or {}).get("captain") or {}\n        vice_audit = (report.get("captaincy_audit") or {}).get("vice_captain") or {}\n        captain_detail = (\n            f"{captain.get('web_name') or 'Not available'} "\n            f"({captain_audit.get('displayed_mean_xpts', captain.get('expected_points'))} mean xPts; "\n            f"strategic score {captain_audit.get('strategic_score')})"\n            if captain_audit.get("strategic_utility_available")\n            else f"{captain.get('web_name') or 'Not available'} ({captain.get('expected_points')} mean xPts)"\n        )\n        vice_detail = (\n            f"{vice.get('web_name') or 'Not available'} "\n            f"({vice_audit.get('displayed_mean_xpts', vice.get('expected_points'))} mean xPts; "\n            f"strategic score {vice_audit.get('strategic_score')})"\n            if vice_audit.get("strategic_utility_available")\n            else f"{vice.get('web_name') or 'Not available'} ({vice.get('expected_points')} mean xPts)"\n        )\n        lines.extend([\n            "",\n            f"Captain: {captain_detail}",\n            f"Vice-captain: {vice_detail}",\n            "Captaincy note: strategic utility selects who is doubled; strategic bonuses are not added to displayed xPts.",\n            "",\n            "## Bench order",\n            "",\n        ])''',
)

# 5. Add focused regressions for the output contract.
Path("tests/test_fpl_22d_reporting.py").write_text(
    '''from __future__ import annotations\n\nimport json\nimport tempfile\nimport unittest\nfrom pathlib import Path\n\nfrom src.build_fpl_model import production_policy_reporting\nfrom src.fpl_gameweek_operations import _captaincy_audit\n\n\nclass Fpl22DReportingTests(unittest.TestCase):\n    def test_rejected_policy_prose_matches_live_control_and_zero_weights(self) -> None:\n        with tempfile.TemporaryDirectory() as directory:\n            path = Path(directory) / "ensemble_production_policy.json"\n            path.write_text(\n                json.dumps(\n                    {\n                        "status": "holdout_rejected",\n                        "live_model_version": "player-sim-2.0",\n                        "live_point_weight": 0.0,\n                        "live_probability_weights": {"6": 0.0, "10": 0.0, "15": 0.0},\n                        "challenger_mode": "shadow_only",\n                        "reason": "Independent holdout rejected the challenger.",\n                    }\n                ),\n                encoding="utf-8",\n            )\n            result = production_policy_reporting(\n                path,\n                {\n                    "status": "holdout_rejected",\n                    "model_version": "player-sim-2.0",\n                    "point_weight": 0.0,\n                    "probability_weights": {"6": 0.0, "10": 0.0, "15": 0.0},\n                },\n                "shadow_candidate",\n            )\n        self.assertEqual(result["policy"]["status"], "holdout_rejected")\n        self.assertEqual(result["policy"]["live_model_version"], "player-sim-2.0")\n        self.assertEqual(result["policy"]["challenger_mode"], "shadow_only")\n        self.assertEqual(result["policy"]["live_point_weight"], 0.0)\n        self.assertEqual(result["policy"]["live_probability_weights"], {"6": 0.0, "10": 0.0, "15": 0.0})\n        self.assertIn("Production uses player-sim-2.0", result["method"])\n        self.assertIn("holdout_rejected", result["method"])\n        self.assertNotIn("Development-selected ensemble", result["method"])\n\n    def test_operational_captain_audit_separates_mean_xpts_from_strategy(self) -> None:\n        audit = {\n            "version": "strategic-captain-1.0",\n            "player_id": 11,\n            "captain_score": 7.25,\n            "mean_expected_points": 5.4,\n            "bounded_strategic_bonus": 1.3,\n            "ceiling_contribution": 1.0,\n            "rank_pressure_contribution": 0.3,\n            "position_uncertainty_penalty": 0.0,\n            "defensive_exception_margin": 0.0,\n            "selection_risk_penalty": 0.2,\n            "expected_minutes": 87.0,\n            "availability_confidence": 1.0,\n            "points_p90": 12.0,\n            "probability_10_plus": 0.31,\n            "probability_15_plus": 0.12,\n            "ownership_percent": 58.0,\n        }\n        decision = {\n            "captaincy": {\n                "utility_version": "strategic-captain-1.0",\n                "player_audits": {"11": audit},\n            }\n        }\n        selection = {\n            "captain": {"player_id": 11, "expected_points": 5.1},\n            "vice_captain": {"player_id": 12, "expected_points": 4.8},\n            "captain_selection_basis": "route_strategic_utility",\n            "vice_captain_selection_basis": "mean_xpts_fallback",\n        }\n        result = _captaincy_audit(decision, selection)\n        self.assertEqual(result["captain"]["displayed_mean_xpts"], 5.1)\n        self.assertEqual(result["captain"]["risk_adjusted_mean_input"], 5.4)\n        self.assertEqual(result["captain"]["strategic_score"], 7.25)\n        self.assertEqual(result["captain"]["components"]["bounded_strategic_bonus"], 1.3)\n        self.assertFalse(result["captain"]["strategic_bonus_is_expected_points"])\n        self.assertFalse(result["vice_captain"]["strategic_utility_available"])\n        self.assertEqual(result["vice_captain"]["selection_basis"], "mean_xpts_fallback")\n        self.assertEqual(result["reported_xpts_basis"], "mean_expected_points_only")\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
    encoding="utf-8",
)

print("FPL-22D source transform applied")
