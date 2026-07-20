from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "external-context-1.0"
SIGNAL_TYPES = {
    "availability_probability",
    "start_probability",
    "expected_minutes",
    "anytime_goal_probability",
    "clean_sheet_probability",
    "attack_multiplier",
    "penalty_taker_probability",
    "set_piece_share",
}
PROBABILITY_SIGNALS = {
    "availability_probability",
    "start_probability",
    "anytime_goal_probability",
    "clean_sheet_probability",
    "penalty_taker_probability",
    "set_piece_share",
}
DEFAULT_SOURCE_REGISTRY = {
    "schema_version": SCHEMA_VERSION,
    "sources": [
        {
            "source_id": "confirmed_lineup",
            "name": "Confirmed starting line-up",
            "reliability": 1.0,
            "freshness_half_life_hours": 8,
        },
        {
            "source_id": "official_club",
            "name": "Official club or competition update",
            "reliability": 1.0,
            "freshness_half_life_hours": 72,
        },
        {
            "source_id": "bookmaker_market",
            "name": "Aggregated bookmaker market",
            "reliability": 0.85,
            "freshness_half_life_hours": 24,
        },
        {
            "source_id": "predicted_lineup",
            "name": "Predicted line-up provider",
            "reliability": 0.7,
            "freshness_half_life_hours": 24,
        },
        {
            "source_id": "trusted_reporter",
            "name": "Trusted reporter",
            "reliability": 0.75,
            "freshness_half_life_hours": 48,
        },
        {
            "source_id": "manual_verified",
            "name": "Manually verified observation",
            "reliability": 0.8,
            "freshness_half_life_hours": 72,
        },
    ],
}


class ContextValidationError(ValueError):
    pass


def number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def integer(value: Any) -> int:
    return int(number(value))


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def source_map(registry: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    registry = registry or DEFAULT_SOURCE_REGISTRY
    return {
        str(item.get("source_id")): item
        for item in registry.get("sources", [])
        if item.get("source_id")
    }


def load_source_registry(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return DEFAULT_SOURCE_REGISTRY
    value = json.loads(path.read_text(encoding="utf-8"))
    validate_source_registry(value)
    return value


def validate_source_registry(registry: dict[str, Any]) -> None:
    sources = registry.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ContextValidationError("Source registry must contain a non-empty sources list")
    seen: set[str] = set()
    for index, source in enumerate(sources, start=1):
        source_id = str(source.get("source_id") or "").strip()
        if not source_id:
            raise ContextValidationError(f"Source {index} is missing source_id")
        if source_id in seen:
            raise ContextValidationError(f"Duplicate source_id: {source_id}")
        seen.add(source_id)
        reliability = number(source.get("reliability"))
        if not 0 <= reliability <= 1:
            raise ContextValidationError(
                f"Source {source_id} reliability must be between 0 and 1"
            )
        if number(source.get("freshness_half_life_hours")) <= 0:
            raise ContextValidationError(
                f"Source {source_id} freshness_half_life_hours must be positive"
            )


def validate_signal(signal: dict[str, Any], sources: dict[str, dict[str, Any]]) -> None:
    signal_id = str(signal.get("signal_id") or "").strip()
    if not signal_id:
        raise ContextValidationError("Signal is missing signal_id")
    signal_type = str(signal.get("signal_type") or "")
    if signal_type not in SIGNAL_TYPES:
        raise ContextValidationError(
            f"Signal {signal_id} has unsupported signal_type {signal_type!r}"
        )
    source_id = str(signal.get("source_id") or "")
    if source_id not in sources:
        raise ContextValidationError(
            f"Signal {signal_id} references unknown source_id {source_id!r}"
        )
    if parse_time(signal.get("observed_at")) is None:
        raise ContextValidationError(f"Signal {signal_id} has invalid observed_at")
    if not any(
        integer(signal.get(field)) > 0
        for field in ("player_id", "team_id", "fixture_id", "gameweek")
    ):
        raise ContextValidationError(
            f"Signal {signal_id} needs a player, team, fixture or gameweek target"
        )
    confidence = number(signal.get("confidence", 1))
    if not 0 <= confidence <= 1:
        raise ContextValidationError(
            f"Signal {signal_id} confidence must be between 0 and 1"
        )
    value = number(signal.get("value"))
    if signal_type in PROBABILITY_SIGNALS and not 0 <= value <= 1:
        raise ContextValidationError(
            f"Signal {signal_id} value must be between 0 and 1"
        )
    if signal_type == "expected_minutes" and not 0 <= value <= 120:
        raise ContextValidationError(
            f"Signal {signal_id} expected minutes must be between 0 and 120"
        )
    if signal_type == "attack_multiplier" and not 0.5 <= value <= 1.5:
        raise ContextValidationError(
            f"Signal {signal_id} attack multiplier must be between 0.5 and 1.5"
        )
    valid_from = parse_time(signal.get("valid_from"))
    expires_at = parse_time(signal.get("expires_at"))
    if signal.get("valid_from") and valid_from is None:
        raise ContextValidationError(f"Signal {signal_id} has invalid valid_from")
    if signal.get("expires_at") and expires_at is None:
        raise ContextValidationError(f"Signal {signal_id} has invalid expires_at")
    if valid_from and expires_at and expires_at <= valid_from:
        raise ContextValidationError(
            f"Signal {signal_id} expires_at must be after valid_from"
        )


def read_context_signals(
    path: Path, registry: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    sources = source_map(registry)
    signals: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            signal = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ContextValidationError(
                f"Invalid JSON on context signal line {line_number}: {exc}"
            ) from exc
        validate_signal(signal, sources)
        signal_id = str(signal["signal_id"])
        if signal_id in seen:
            raise ContextValidationError(f"Duplicate signal_id: {signal_id}")
        seen.add(signal_id)
        signals.append(signal)
    return signals


def signal_weight(
    signal: dict[str, Any],
    source: dict[str, Any],
    as_of: datetime,
) -> tuple[float, str]:
    if str(signal.get("status") or "active") != "active":
        return 0.0, "inactive"
    observed_at = parse_time(signal.get("observed_at"))
    valid_from = parse_time(signal.get("valid_from")) or observed_at
    expires_at = parse_time(signal.get("expires_at"))
    if observed_at is None or observed_at > as_of:
        return 0.0, "not_yet_observed"
    if valid_from and valid_from > as_of:
        return 0.0, "not_yet_valid"
    if expires_at and expires_at <= as_of:
        return 0.0, "expired"
    age_hours = max(0.0, (as_of - observed_at).total_seconds() / 3600)
    half_life = max(1.0, number(source.get("freshness_half_life_hours")))
    freshness = math.pow(0.5, age_hours / half_life)
    weight = (
        number(source.get("reliability"))
        * number(signal.get("confidence", 1))
        * freshness
    )
    return round(clamp(weight, 0, 1), 6), "active"


def signal_matches(
    signal: dict[str, Any],
    player: dict[str, Any],
    fixture: dict[str, Any] | None = None,
) -> bool:
    fixture = fixture or {}
    checks = [
        ("player_id", integer(player.get("player_id"))),
        ("team_id", integer(player.get("team_id"))),
        ("fixture_id", integer(fixture.get("fixture_id"))),
        ("gameweek", integer(fixture.get("gameweek"))),
    ]
    targeted = False
    matched_known_target = False
    for field, actual in checks:
        expected = integer(signal.get(field))
        if expected:
            targeted = True
            if not actual:
                continue
            matched_known_target = True
            if expected != actual:
                return False
    return targeted and matched_known_target


def resolved_context(
    signals: Iterable[dict[str, Any]],
    registry: dict[str, Any],
    player: dict[str, Any],
    fixture: dict[str, Any] | None = None,
    as_of: str | datetime | None = None,
) -> dict[str, Any]:
    if isinstance(as_of, str):
        resolved_as_of = parse_time(as_of)
    else:
        resolved_as_of = as_of
    resolved_as_of = resolved_as_of or datetime.now(timezone.utc)
    sources = source_map(registry)
    grouped: dict[str, list[tuple[dict[str, Any], float]]] = defaultdict(list)
    matched: list[dict[str, Any]] = []
    candidates = [
        signal for signal in signals if signal_matches(signal, player, fixture)
    ]
    latest: dict[tuple[Any, ...], dict[str, Any]] = {}
    for signal in candidates:
        observed_at = parse_time(signal.get("observed_at"))
        if observed_at is None or observed_at > resolved_as_of:
            continue
        key = (
            signal.get("source_id"), signal.get("signal_type"),
            integer(signal.get("player_id")), integer(signal.get("team_id")),
            integer(signal.get("fixture_id")), integer(signal.get("gameweek")),
        )
        current = latest.get(key)
        if current is None or observed_at > (
            parse_time(current.get("observed_at")) or datetime.min.replace(tzinfo=timezone.utc)
        ):
            latest[key] = signal
    effective_ids = {str(signal.get("signal_id")) for signal in latest.values()}
    for signal in candidates:
        if not signal_matches(signal, player, fixture):
            continue
        source = sources.get(str(signal.get("source_id")))
        if not source:
            continue
        if str(signal.get("signal_id")) not in effective_ids:
            weight, state = 0.0, "superseded"
        else:
            weight, state = signal_weight(signal, source, resolved_as_of)
        matched.append(
            {
                "signal_id": signal.get("signal_id"),
                "signal_type": signal.get("signal_type"),
                "source_id": signal.get("source_id"),
                "state": state,
                "effective_weight": weight,
            }
        )
        if weight > 0:
            grouped[str(signal.get("signal_type"))].append((signal, weight))

    values: dict[str, float] = {}
    strengths: dict[str, float] = {}
    for signal_type, items in grouped.items():
        total_weight = sum(weight for _, weight in items)
        values[signal_type] = round(
            sum(number(signal.get("value")) * weight for signal, weight in items)
            / total_weight,
            6,
        )
        strengths[signal_type] = round(
            1 - math.prod(1 - weight for _, weight in items), 6
        )
    active = [item for item in matched if item["effective_weight"] > 0]
    return {
        "schema_version": SCHEMA_VERSION,
        "as_of": resolved_as_of.replace(microsecond=0).isoformat(),
        "signal_count": len(active),
        "signal_ids": [item["signal_id"] for item in active],
        "source_ids": sorted({str(item["source_id"]) for item in active}),
        "values": values,
        "strengths": strengths,
        "signals": matched,
    }


def context_summary(
    signals: list[dict[str, Any]], registry: dict[str, Any], as_of: str | None = None
) -> dict[str, Any]:
    observed = parse_time(as_of) or datetime.now(timezone.utc)
    sources = source_map(registry)
    rows = []
    for signal in signals:
        source = sources[str(signal.get("source_id"))]
        weight, state = signal_weight(signal, source, observed)
        rows.append({**signal, "effective_weight": weight, "state": state})
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": observed.replace(microsecond=0).isoformat(),
        "registered_sources": len(sources),
        "signal_rows": len(signals),
        "active_signal_rows": sum(row["effective_weight"] > 0 for row in rows),
        "expired_signal_rows": sum(row["state"] == "expired" for row in rows),
        "signal_types": dict(
            sorted(
                (kind, sum(row.get("signal_type") == kind for row in rows))
                for kind in SIGNAL_TYPES
                if any(row.get("signal_type") == kind for row in rows)
            )
        ),
        "sources_used": sorted(
            {str(row.get("source_id")) for row in rows if row["effective_weight"] > 0}
        ),
        "principle": (
            "External signals are timestamped, source-weighted and kept separate "
            "from the validated ensemble forecast."
        ),
    }


def write_signal_csv(path: Path, signals: list[dict[str, Any]]) -> None:
    fields = [
        "signal_id",
        "observed_at",
        "source_id",
        "signal_type",
        "value",
        "confidence",
        "player_id",
        "team_id",
        "fixture_id",
        "gameweek",
        "valid_from",
        "expires_at",
        "status",
        "source_url",
        "note",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(signals)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate external FPL context signals")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--signals", type=Path, required=True)
    validate.add_argument("--sources", type=Path, required=True)
    args = parser.parse_args()
    registry = load_source_registry(args.sources)
    signals = read_context_signals(args.signals, registry)
    print(json.dumps(context_summary(signals, registry), indent=2))


if __name__ == "__main__":
    main()
