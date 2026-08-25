from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from src.evaluate_external_context import evaluate_external_signals, write_external_evaluation
from src.external_context import load_source_registry, read_context_signals
from src.fpl_chips import derive_chip_state
from src.fpl_decisions import DECISION_VERSION
from src.fpl_finality import official_events
from src.fpl_transfers import derive_free_transfer_state


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def finalise(data_dir: Path) -> dict[str, Any]:
    chatgpt = data_dir / "chatgpt"
    registry = load_source_registry(data_dir / "context" / "sources.json")
    signals = read_context_signals(data_dir / "context" / "signals.jsonl", registry)
    gameweeks, finality_source = official_events(data_dir)
    rows, evaluation = evaluate_external_signals(
        signals,
        read_csv(chatgpt / "player_fixtures.csv"),
        read_csv(chatgpt / "fixtures.csv"),
        gameweeks,
    )
    evaluation["finality_source"] = finality_source
    write_external_evaluation(chatgpt, rows, evaluation)

    manifest = read_json(chatgpt / "manifest.json", {})
    manager_history = read_json(chatgpt / "manager_history.json", {})
    chip_rules = read_json(data_dir / "context" / "chip_rules.json", {})
    season = manifest.get("season")
    current_gameweek = read_json(chatgpt / "current_gameweek.json", {})
    target_gameweek = int(
        (current_gameweek.get("next") or {}).get("id")
        or int((current_gameweek.get("current") or {}).get("id") or 0) + 1
    )
    season_rules = chip_rules.get("seasons", {}).get(str(season), {})
    chip_state = derive_chip_state(
        manager_history,
        season,
        chip_rules,
        target_gameweek=target_gameweek,
    )
    transfer_state = derive_free_transfer_state(
        manager_history, target_gameweek, season_rules
    )

    decision_path = chatgpt / "fpl_decisions.json"
    if decision_path.is_file():
        decision = read_json(decision_path, {})
        decision["decision_version"] = DECISION_VERSION
        decision["free_transfer_state"] = transfer_state
        decision.setdefault("chip_indicators", {})["chip_state"] = chip_state
        decision["chip_indicators"]["reason"] = (
            "Phase 18 compares each available chip with the no-chip transfer routes, "
            "accounts for half-season expiry and enforces one chip per Gameweek."
        )
        decision_path.write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")

    datasets = manifest.setdefault("datasets", [])
    existing = {item.get("path") for item in datasets}
    for path in (
        "data/chatgpt/external_context_accuracy.csv",
        "data/chatgpt/external_context_evaluation.json",
    ):
        if path not in existing:
            datasets.append({"path": path})
    if manifest:
        (chatgpt / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

    projection_path = chatgpt / "projection_summary.json"
    if projection_path.is_file():
        projection = read_json(projection_path, {})
        projection["evaluated_external_context_signals"] = evaluation["evaluated_signals"]
        projection["chip_state_status"] = chip_state["status"]
        projection["free_transfer_state_status"] = transfer_state["status"]
        projection_path.write_text(
            json.dumps(projection, indent=2) + "\n", encoding="utf-8"
        )
    return {
        "external_evaluation": evaluation,
        "chip_state": chip_state,
        "free_transfer_state": transfer_state,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score external signals and attach manager rule state"
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    print(json.dumps(finalise(args.data_dir), indent=2))


if __name__ == "__main__":
    main()
