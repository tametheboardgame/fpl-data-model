from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def integer(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def official_events(data_dir: Path) -> tuple[list[dict[str, Any]], str]:
    """Return current-season events, preferring live authoritative snapshots.

    ``data/chatgpt/gameweeks.json`` can be supplied by the historical sync and may
    describe a previous season. It is therefore a last-resort fallback only.
    """

    bootstrap_path = data_dir / "raw" / "latest" / "bootstrap-static.json"
    bootstrap = _read_json(bootstrap_path, {})
    bootstrap_events = bootstrap.get("events", []) if isinstance(bootstrap, dict) else []
    if bootstrap_events:
        return bootstrap_events, str(bootstrap_path.relative_to(data_dir))

    current_path = data_dir / "chatgpt" / "current_gameweek.json"
    current = _read_json(current_path, {})
    if isinstance(current, dict):
        current_events = [
            event
            for event in (current.get("current"), current.get("next"))
            if isinstance(event, dict) and integer(event.get("id"))
        ]
        if current_events:
            return current_events, str(current_path.relative_to(data_dir))

    gameweeks_path = data_dir / "chatgpt" / "gameweeks.json"
    gameweeks = _read_json(gameweeks_path, [])
    if isinstance(gameweeks, list):
        return gameweeks, str(gameweeks_path.relative_to(data_dir))
    return [], "unavailable"


def gameweek_finality(data_dir: Path) -> tuple[dict[int, bool], str]:
    events, source = official_events(data_dir)
    return (
        {
            integer(event.get("id")): truthy(event.get("finished"))
            and truthy(event.get("data_checked"))
            for event in events
            if integer(event.get("id"))
        },
        source,
    )
