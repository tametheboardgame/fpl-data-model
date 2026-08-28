from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REFRESH_TARGET_HOURS = (24, 8, 4, 1)
FREEZE_WINDOW_HOURS = 8
MODEL_BUILD_GRACE_MINUTES = 20


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
    gameweek_report: dict[str, Any] | None = None,
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
            "checkpoint_time": None,
        }

    hours_remaining = (deadline - now).total_seconds() / 3600
    matched = min(
        (
            target
            for target in REFRESH_TARGET_HOURS
            if 0 < hours_remaining <= target
        ),
        default=None,
    )
    checkpoint_time = (
        deadline - timedelta(hours=matched) if matched is not None else None
    )
    current_generated = parse_time(current_gameweek.get("generated_at"))

    report = gameweek_report or {}
    report_matches_gameweek = bool(report) and (
        report.get("target_gameweek") == next_event.get("id")
    )
    model_generated = (
        parse_time((report.get("source_freshness") or {}).get("official_fpl_generated_at"))
        if report_matches_gameweek
        else None
    )
    freeze = report.get("deadline_freeze") or {}
    snapshot_required = matched is not None and matched <= FREEZE_WINDOW_HOURS
    snapshot_ready = (
        not snapshot_required
        or (
            report_matches_gameweek
            and freeze.get("status") == "frozen"
            and bool(freeze.get("immutable_snapshot"))
        )
    )
    data_fresh = bool(
        checkpoint_time
        and current_generated
        and current_generated >= checkpoint_time
    )
    model_fresh = bool(
        checkpoint_time
        and model_generated
        and model_generated >= checkpoint_time
    )
    model_build_in_grace = bool(
        data_fresh
        and not model_fresh
        and current_generated
        and now - current_generated < timedelta(minutes=MODEL_BUILD_GRACE_MINUTES)
    )

    if force:
        should_refresh = True
        reason = "manual_force"
    elif matched is None:
        should_refresh = False
        reason = (
            "deadline_passed" if hours_remaining <= 0 else "before_deadline_checkpoints"
        )
    elif not data_fresh:
        should_refresh = True
        reason = f"deadline_checkpoint_{matched}h_data_due"
    elif model_build_in_grace:
        should_refresh = False
        reason = f"deadline_checkpoint_{matched}h_model_pending"
    elif not model_fresh:
        should_refresh = True
        reason = f"deadline_checkpoint_{matched}h_model_overdue"
    elif not snapshot_ready:
        should_refresh = True
        reason = f"deadline_checkpoint_{matched}h_snapshot_missing"
    else:
        should_refresh = False
        reason = f"deadline_checkpoint_{matched}h_satisfied"

    return {
        "should_refresh": should_refresh,
        "reason": reason,
        "target_gameweek": next_event.get("id"),
        "deadline_time": deadline.isoformat(),
        "hours_remaining": round(hours_remaining, 3),
        "matched_window_hours": matched,
        "checkpoint_time": checkpoint_time.isoformat() if checkpoint_time else None,
        "data_generated_at": (
            current_generated.isoformat() if current_generated else None
        ),
        "model_data_generated_at": (
            model_generated.isoformat() if model_generated else None
        ),
        "snapshot_required": snapshot_required,
        "snapshot_ready": snapshot_ready,
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
        description="Decide whether an FPL deadline refresh checkpoint is outstanding"
    )
    parser.add_argument(
        "--current-gameweek",
        type=Path,
        default=Path("data/chatgpt/current_gameweek.json"),
    )
    parser.add_argument("--now")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--gameweek-report",
        type=Path,
        default=Path("data/chatgpt/gameweek_report.json"),
    )
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    args = parser.parse_args()
    current = json.loads(args.current_gameweek.read_text(encoding="utf-8"))
    report = (
        json.loads(args.gameweek_report.read_text(encoding="utf-8"))
        if args.gameweek_report.is_file()
        else None
    )
    now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
    plan = deadline_refresh_plan(
        current,
        now or datetime.now(timezone.utc),
        args.force,
        report,
    )
    if args.github_output:
        write_github_output(args.github_output, plan)
    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
