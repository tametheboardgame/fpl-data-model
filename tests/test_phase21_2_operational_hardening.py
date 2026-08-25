from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.fpl_deadline_scheduler import deadline_refresh_plan


DEADLINE = "2026-08-21T17:30:00Z"


class DeadlineRefreshSchedulerTests(unittest.TestCase):
    def current(self) -> dict:
        return {"next": {"id": 1, "deadline_time": DEADLINE}}

    def at(self, value: str) -> datetime:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)

    def test_triggers_once_inside_each_deadline_window(self) -> None:
        cases = (
            ("2026-08-20T18:00:00", 24),
            ("2026-08-21T10:00:00", 8),
            ("2026-08-21T14:00:00", 4),
            ("2026-08-21T17:00:00", 1),
        )
        for now, target in cases:
            with self.subTest(target=target):
                plan = deadline_refresh_plan(self.current(), self.at(now))
                self.assertTrue(plan["should_refresh"])
                self.assertEqual(plan["matched_window_hours"], target)

    def test_remains_idle_outside_deadline_windows(self) -> None:
        plan = deadline_refresh_plan(
            self.current(), self.at("2026-08-19T17:30:00")
        )
        self.assertFalse(plan["should_refresh"])
        self.assertEqual(plan["reason"], "outside_deadline_windows")

    def test_does_not_refresh_after_deadline(self) -> None:
        plan = deadline_refresh_plan(
            self.current(), self.at("2026-08-21T18:00:00")
        )
        self.assertFalse(plan["should_refresh"])

    def test_manual_force_works_without_a_deadline(self) -> None:
        plan = deadline_refresh_plan({}, self.at("2026-08-21T10:00:00"), True)
        self.assertTrue(plan["should_refresh"])
        self.assertEqual(plan["reason"], "manual_force")


if __name__ == "__main__":
    unittest.main()
