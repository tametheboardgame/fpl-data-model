from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_decisions() -> None:
    path = Path("src/fpl_decisions.py")
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'DECISION_VERSION = "fpl-decisions-2.1"',
        'DECISION_VERSION = "fpl-decisions-2.2"',
        "decision version",
    )
    text = replace_once(
        text,
        '''    bench_points = sum(\n        number(row.get("selection_expected_points")) for row in bench\n    )\n    captain = captain_pool[0] if captain_pool else None\n    multi_gameweek_plan = optimise_multi_gameweek_route(''',
        '''    bench_points = sum(\n        number(row.get("selection_expected_points")) for row in bench\n    )\n    captain = captain_pool[0] if captain_pool else None\n    first_gameweek_multiplier = {\n        integer(row.get("player_id")): (\n            number(row.get("selection_expected_points"))\n            / number(row.get("model_expected_points"))\n            if number(row.get("model_expected_points")) > 0\n            else 1.0\n        )\n        for row in evaluated\n    }\n    multi_gameweek_plan = optimise_multi_gameweek_route(''',
        "shared first-gameweek multiplier",
    )
    text = replace_once(
        text,
        '''        target_gameweek,\n        first_gameweek_multiplier={\n            integer(row.get("player_id")): (\n                number(row.get("selection_expected_points"))\n                / number(row.get("model_expected_points"))\n                if number(row.get("model_expected_points")) > 0\n                else 1.0\n            )\n            for row in evaluated\n        },\n    )''',
        '''        target_gameweek,\n        first_gameweek_multiplier=first_gameweek_multiplier,\n    )''',
        "multiweek multiplier argument",
    )
    text = replace_once(
        text,
        '''        multi_gameweek_plan,\n        target_gameweek,\n    )\n    first_gameweek_multiplier = {\n        integer(row.get("player_id")): (\n            number(row.get("selection_expected_points"))\n            / number(row.get("model_expected_points"))\n            if number(row.get("model_expected_points")) > 0\n            else 1.0\n        )\n        for row in evaluated\n    }\n    initial_squad_plan = build_initial_squad_plan(''',
        '''        multi_gameweek_plan,\n        target_gameweek,\n        first_gameweek_multiplier=first_gameweek_multiplier,\n    )\n    initial_squad_plan = build_initial_squad_plan(''',
        "chip multiplier argument",
    )
    path.write_text(text, encoding="utf-8")


def patch_chip_optimizer() -> None:
    path = Path("src/fpl_chip_optimizer.py")
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''    target_gameweek: int | None,\n    discount: float = 0.96,\n) -> dict[str, Any]:''',
        '''    target_gameweek: int | None,\n    discount: float = 0.96,\n    first_gameweek_multiplier: dict[int, float] | None = None,\n) -> dict[str, Any]:''',
        "chip optimiser signature",
    )
    text = replace_once(
        text,
        "    matrix = projection_matrix(fixture_projections, gameweeks)",
        '''    matrix = projection_matrix(\n        fixture_projections, gameweeks, first_gameweek_multiplier\n    )''',
        "chip projection matrix",
    )
    text = replace_once(
        text,
        '''        "wildcard_objective": {\n            "version": WILDCARD_OBJECTIVE_VERSION,''',
        '''        "context_wiring": {\n            "first_gameweek_multiplier_applied": bool(first_gameweek_multiplier),\n            "adjusted_player_count": sum(\n                abs(number(value) - 1.0) > 1e-9\n                for value in (first_gameweek_multiplier or {}).values()\n            ),\n            "principle": (\n                "The target-Gameweek mean follows the same decision-layer market and "\n                "selection-risk adjustment as the transfer optimiser; raw tail "\n                "probabilities remain unchanged."\n            ),\n        },\n        "wildcard_objective": {\n            "version": WILDCARD_OBJECTIVE_VERSION,''',
        "chip context audit",
    )
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_decisions()
    patch_chip_optimizer()


if __name__ == "__main__":
    main()
