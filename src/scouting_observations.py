from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.update_fpl_data import utc_now


SIGNAL_FIELDS = [
    "attacking_role",
    "movement_sharpness",
    "fitness_energy",
    "minutes_security",
    "set_piece_role",
    "team_reliance",
    "tactical_fit",
]
VALID_STATUSES = {"active", "retracted"}
HALF_LIFE_DAYS = 14


def parse_datetime(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_observation(observation: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ("observation_id", "observed_at", "recorded_at", "observer", "raw_note"):
        if not observation.get(field):
            errors.append(f"{field} is required")
    if not observation.get("player_id") and not observation.get("player_code"):
        errors.append("player_id or player_code is required")
    for field in ("observed_at", "recorded_at", "valid_from", "expires_at"):
        if observation.get(field):
            try:
                parse_datetime(observation[field])
            except (TypeError, ValueError):
                errors.append(f"{field} must be an ISO-8601 timestamp with timezone")
    try:
        if observation.get("observed_at") and observation.get("recorded_at") and parse_datetime(
            observation["recorded_at"]
        ) < parse_datetime(observation["observed_at"]):
            errors.append("recorded_at cannot be before observed_at")
    except (TypeError, ValueError):
        pass
    try:
        confidence = float(observation.get("confidence"))
        if not 0 <= confidence <= 1:
            errors.append("confidence must be between 0 and 1")
    except (TypeError, ValueError):
        errors.append("confidence must be between 0 and 1")
    for field in SIGNAL_FIELDS:
        try:
            value = float(observation.get(field, 0))
            if not -2 <= value <= 2:
                errors.append(f"{field} must be between -2 and 2")
        except (TypeError, ValueError):
            errors.append(f"{field} must be between -2 and 2")
    if observation.get("status", "active") not in VALID_STATUSES:
        errors.append("status must be active or retracted")
    if observation.get("status") == "retracted" and not observation.get(
        "retracts_observation_id"
    ):
        errors.append("retracts_observation_id is required for a retraction")
    return errors


def read_observations(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    observations: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        observation = json.loads(line)
        errors = validate_observation(observation)
        if errors:
            raise ValueError(f"Invalid scouting observation on line {line_number}: {'; '.join(errors)}")
        observations.append(observation)
    return observations


def observation_applies(
    observation: dict[str, Any], player: dict[str, Any], cutoff: datetime
) -> bool:
    if observation.get("status", "active") != "active":
        return False
    player_id_matches = observation.get("player_id") and int(observation["player_id"]) == int(
        player.get("player_id") or 0
    )
    player_code_matches = observation.get("player_code") and int(observation["player_code"]) == int(
        player.get("player_code") or 0
    )
    if not player_id_matches and not player_code_matches:
        return False
    observed_at = parse_datetime(observation["observed_at"])
    recorded_at = parse_datetime(observation["recorded_at"])
    valid_from = parse_datetime(observation.get("valid_from") or observation["observed_at"])
    if observed_at > cutoff or recorded_at > cutoff or valid_from > cutoff:
        return False
    if observation.get("expires_at") and cutoff > parse_datetime(observation["expires_at"]):
        return False
    return True


def qualitative_adjustment(
    observations: list[dict[str, Any]], player: dict[str, Any], cutoff_text: str
) -> dict[str, Any]:
    cutoff = parse_datetime(cutoff_text)
    retracted_ids = {
        str(observation.get("retracts_observation_id"))
        for observation in observations
        if observation.get("status") == "retracted"
        and observation.get("retracts_observation_id")
        and parse_datetime(observation["recorded_at"]) <= cutoff
    }
    applicable = [
        observation
        for observation in observations
        if str(observation.get("observation_id")) not in retracted_ids
        and observation_applies(observation, player, cutoff)
    ]
    weighted_signals = {field: 0.0 for field in SIGNAL_FIELDS}
    weights: list[float] = []
    for observation in applicable:
        age_days = max(
            0.0,
            (cutoff - parse_datetime(observation["observed_at"])).total_seconds() / 86400,
        )
        weight = float(observation["confidence"]) * 0.5 ** (age_days / HALF_LIFE_DAYS)
        weights.append(weight)
        for field in SIGNAL_FIELDS:
            weighted_signals[field] += float(observation.get(field, 0)) * weight
    denominator = max(1.0, sum(weights))
    weighted_signals = {
        field: max(-2.0, min(2.0, value / denominator))
        for field, value in weighted_signals.items()
    }
    minutes_delta = max(
        -12.0,
        min(
            12.0,
            3 * (
                weighted_signals["fitness_energy"]
                + weighted_signals["minutes_security"]
            ),
        ),
    )
    attack_delta = (
        0.04
        * (
            weighted_signals["attacking_role"]
            + weighted_signals["movement_sharpness"]
            + weighted_signals["team_reliance"]
            + weighted_signals["tactical_fit"]
        )
        + 0.025 * weighted_signals["set_piece_role"]
    )
    return {
        "observation_count": len(applicable),
        "observation_ids": [str(item["observation_id"]) for item in applicable],
        "combined_confidence": round(min(1.0, sum(weights)), 4),
        "minutes_delta": round(minutes_delta, 2),
        "attack_multiplier": round(max(0.8, min(1.2, 1 + attack_delta)), 4),
        "signals": {field: round(value, 4) for field, value in weighted_signals.items()},
    }


def append_observation(path: Path, observation: dict[str, Any]) -> dict[str, Any]:
    materialised = {
        "observation_id": observation.get("observation_id") or str(uuid.uuid4()),
        "recorded_at": observation.get("recorded_at") or utc_now(),
        "status": observation.get("status") or "active",
        **observation,
    }
    errors = validate_observation(materialised)
    if errors:
        raise ValueError("; ".join(errors))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(materialised, ensure_ascii=False, sort_keys=True) + "\n")
    return materialised


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate or append FPL scouting observations")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--path", type=Path, default=Path("data/scouting/observations.jsonl"))
    add = subparsers.add_parser("add")
    add.add_argument("--path", type=Path, default=Path("data/scouting/observations.jsonl"))
    add.add_argument("--player-id", type=int, required=True)
    add.add_argument("--player-name", required=True)
    add.add_argument("--observed-at", required=True)
    add.add_argument("--observer", required=True)
    add.add_argument("--note", required=True)
    add.add_argument("--confidence", type=float, required=True)
    add.add_argument("--expires-at")
    for field in SIGNAL_FIELDS:
        add.add_argument(f"--{field.replace('_', '-')}", type=float, default=0)
    args = parser.parse_args()
    if args.command == "validate":
        observations = read_observations(args.path)
        print(json.dumps({"valid": True, "observations": len(observations)}, indent=2))
        return
    payload = {
        "player_id": args.player_id,
        "player_name": args.player_name,
        "observed_at": args.observed_at,
        "observer": args.observer,
        "raw_note": args.note,
        "confidence": args.confidence,
        "expires_at": args.expires_at,
        **{field: getattr(args, field) for field in SIGNAL_FIELDS},
    }
    print(json.dumps(append_observation(args.path, payload), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
