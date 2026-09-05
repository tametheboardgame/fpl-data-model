from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Expected patch anchor not found in {path}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


sync = Path("src/sync_historical_fpl.py")
backtest = Path("src/backtest_fpl_model.py")

replace_once(
    sync,
    '    "2024-25",\n]',
    '    "2024-25",\n    "2025-26",\n]',
)
replace_once(
    sync,
    '    "saves",\n    "bonus",',
    '    "saves",\n    "defensive_contribution",\n    "bonus",',
)
replace_once(
    sync,
    '        "saves": row.get("saves", ""),\n        "bonus": row.get("bonus", ""),',
    '        "saves": row.get("saves", ""),\n        "defensive_contribution": row.get("defensive_contribution", ""),\n        "bonus": row.get("bonus", ""),',
)
replace_once(
    sync,
    '        self.saves = 0.0\n        self.bonus = 0.0',
    '        self.saves = 0.0\n        self.defensive_contribution = 0.0\n        self.bonus = 0.0',
)
replace_once(
    sync,
    '        self.saves += number(row.get("saves"))\n        self.bonus += number(row.get("bonus"))',
    '        self.saves += number(row.get("saves"))\n        self.defensive_contribution += number(row.get("defensive_contribution"))\n        self.bonus += number(row.get("bonus"))',
)
replace_once(
    sync,
    '            "saves_per_90": round(self.saves * per90, 4),\n            "bonus_per_90": round(self.bonus * per90, 4),',
    '            "saves_per_90": round(self.saves * per90, 4),\n            "defensive_contribution_per_90": round(self.defensive_contribution * per90, 4),\n            "bonus_per_90": round(self.bonus * per90, 4),',
)

replace_once(
    backtest,
    'def clamp(value: float, lower: float, upper: float) -> float:\n    return max(lower, min(upper, value))\n\n\ndef fixture_opponents',
    'def clamp(value: float, lower: float, upper: float) -> float:\n    return max(lower, min(upper, value))\n\n\ndef historical_defensive_contribution_rate(season: str, value: Any) -> float:\n    """DefCon points entered FPL scoring from 2025/26; older backtests must not score them."""\n    try:\n        start_year = int(str(season).split("-", 1)[0])\n    except (TypeError, ValueError):\n        return 0.0\n    return max(0.0, number(value)) if start_year >= 2025 else 0.0\n\n\ndef fixture_opponents',
)
replace_once(
    backtest,
    '    # Defensive-contribution points did not exist in the seasons under test.\n    inputs["defensive_contribution_per_90"] = 0',
    '    inputs["defensive_contribution_per_90"] = historical_defensive_contribution_rate(\n        str(row.get("season") or ""), inputs["defensive_contribution_per_90"]\n    )',
)
replace_once(
    backtest,
    '    component_inputs["defensive_contribution_per_90"] = 0',
    '    component_inputs["defensive_contribution_per_90"] = historical_defensive_contribution_rate(\n        str(row.get("season") or ""),\n        component_inputs["defensive_contribution_per_90"],\n    )',
)
