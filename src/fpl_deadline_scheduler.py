from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REFRESH_TARGET_HOURS = (24, 8, 4, 1)


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


def deadline_refresh_plan(
    current_gameweek: dict[str, Any],
    now: datetime,
    force: bool = False,
) -> dict[str, Any]:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    next_event = current_gameweek.get("next") or {}
    deadline = parse_time(next_event.get("deadline_time"))
    if not deadline:
        return {
            "should_refresh": force,
            "reason": "manual_force" if force else "deadline_unavailable",
            "target_gameweek": next_event.get("id"),
            "deadline_time": None,
            "hours_remaining": None,
            "matched_window_hours": None,
        }

    hours_remaining = (deadline - now).total_seconds() / 3600
    matched = next(
        (
            target
            for target in REFRESH_TARGET_HOURS
            if target - 1 < hours_remaining <= target
        ),
        None,
    )
    should_refresh = force or matched is not None
    return {
        "should_refresh": should_refresh,
        "reason": (
            "manual_force"
            if force
            else f"deadline_window_{matched}h"
            if matched is not None
            else "outside_deadline_windows"
        ),
        "target_gameweek": next_event.get("id"),
        "deadline_time": deadline.isoformat(),
        "hours_remaining": round(hours_remaining, 3),
        "matched_window_hours": matched,
    }


def write_github_output(path: str, plan: dict[str, Any]) -> None:
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(
            "should_refresh="
            + ("true" if plan["should_refresh"] else "false")
            + "\n"
        )
        handle.write(f"reason={plan['reason']}\n")
        handle.write(
            f"matched_window_hours={plan.get('matched_window_hours') or ''}\n"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Decide whether an hourly run is near an FPL deadline refresh window"
    )
    parser.add_argument(
        "--current-gameweek",
        type=Path,
        default=Path("data/chatgpt/current_gameweek.json"),
    )
    parser.add_argument("--now")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    args = parser.parse_args()
    current = json.loads(args.current_gameweek.read_text(encoding="utf-8"))
    now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
    plan = deadline_refresh_plan(current, now or datetime.now(timezone.utc), args.force)
    if args.github_output:
        write_github_output(args.github_output, plan)
    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
