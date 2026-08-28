from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.fpl_deadline_scheduler import deadline_refresh_plan


DEADLINE = "2026-08-21T17:30:00Z"


class DeadlineRefreshSchedulerTests(unittest.TestCase):
    def current(self, generated_at: str | None = None) -> dict:
        value = {"next": {"id": 1, "deadline_time": DEADLINE}}
        if generated_at:
            value["generated_at"] = generated_at
        return value

    def report(
        self,
        official_generated_at: str,
        *,
        frozen: bool = False,
        target_gameweek: int = 1,
    ) -> dict:
        return {
            "target_gameweek": target_gameweek,
            "source_freshness": {
                "official_fpl_generated_at": official_generated_at,
            },
            "deadline_freeze": {
                "status": "frozen" if frozen else "waiting_for_freeze_window",
                "immutable_snapshot": (
                    "prospective/gw01/20260821T100000Z.json" if frozen else None
                ),
            },
        }

    def at(self, value: str) -> datetime:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)

    def test_triggers_at_each_unsatisfied_deadline_checkpoint(self) -> None:
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

    def test_catches_a_checkpoint_after_the_old_one_hour_window_was_missed(self) -> None:
        plan = deadline_refresh_plan(
            self.current("2026-08-20T16:00:00Z"),
            self.at("2026-08-21T11:30:00"),
            gameweek_report=self.report("2026-08-20T16:00:00Z"),
        )

        self.assertTrue(plan["should_refresh"])
        self.assertEqual(plan["matched_window_hours"], 8)
        self.assertEqual(plan["reason"], "deadline_checkpoint_8h_data_due")

    def test_completed_checkpoint_is_idempotent(self) -> None:
        plan = deadline_refresh_plan(
            self.current("2026-08-21T10:02:00Z"),
            self.at("2026-08-21T11:30:00"),
            gameweek_report=self.report(
                "2026-08-21T10:02:00Z",
                frozen=True,
            ),
        )

        self.assertFalse(plan["should_refresh"])
        self.assertEqual(plan["reason"], "deadline_checkpoint_8h_satisfied")
        self.assertTrue(plan["snapshot_ready"])

    def test_later_checkpoint_requires_a_new_refresh(self) -> None:
        plan = deadline_refresh_plan(
            self.current("2026-08-21T10:02:00Z"),
            self.at("2026-08-21T14:30:00"),
            gameweek_report=self.report(
                "2026-08-21T10:02:00Z",
                frozen=True,
            ),
        )

        self.assertTrue(plan["should_refresh"])
        self.assertEqual(plan["matched_window_hours"], 4)
        self.assertEqual(plan["reason"], "deadline_checkpoint_4h_data_due")

    def test_waits_briefly_for_a_model_build_after_fresh_data(self) -> None:
        plan = deadline_refresh_plan(
            self.current("2026-08-21T10:05:00Z"),
            self.at("2026-08-21T10:15:00"),
            gameweek_report=self.report("2026-08-20T18:00:00Z"),
        )

        self.assertFalse(plan["should_refresh"])
        self.assertEqual(plan["reason"], "deadline_checkpoint_8h_model_pending")

    def test_retries_when_model_build_remains_stale_after_grace_period(self) -> None:
        plan = deadline_refresh_plan(
            self.current("2026-08-21T10:05:00Z"),
            self.at("2026-08-21T10:30:00"),
            gameweek_report=self.report("2026-08-20T18:00:00Z"),
        )

        self.assertTrue(plan["should_refresh"])
        self.assertEqual(plan["reason"], "deadline_checkpoint_8h_model_overdue")

    def test_missing_freeze_snapshot_retries_the_checkpoint(self) -> None:
        plan = deadline_refresh_plan(
            self.current("2026-08-21T10:02:00Z"),
            self.at("2026-08-21T10:30:00"),
            gameweek_report=self.report("2026-08-21T10:02:00Z"),
        )

        self.assertTrue(plan["should_refresh"])
        self.assertEqual(plan["reason"], "deadline_checkpoint_8h_snapshot_missing")
        self.assertTrue(plan["snapshot_required"])
        self.assertFalse(plan["snapshot_ready"])

    def test_report_for_another_gameweek_does_not_satisfy_checkpoint(self) -> None:
        plan = deadline_refresh_plan(
            self.current("2026-08-21T10:02:00Z"),
            self.at("2026-08-21T10:30:00"),
            gameweek_report=self.report(
                "2026-08-21T10:02:00Z",
                frozen=True,
                target_gameweek=2,
            ),
        )

        self.assertTrue(plan["should_refresh"])
        self.assertEqual(plan["reason"], "deadline_checkpoint_8h_model_overdue")

    def test_remains_idle_before_first_deadline_checkpoint(self) -> None:
        plan = deadline_refresh_plan(
            self.current(), self.at("2026-08-19T17:30:00")
        )
        self.assertFalse(plan["should_refresh"])
        self.assertEqual(plan["reason"], "before_deadline_checkpoints")

    def test_does_not_refresh_after_deadline(self) -> None:
        plan = deadline_refresh_plan(
            self.current(), self.at("2026-08-21T18:00:00")
        )
        self.assertFalse(plan["should_refresh"])
        self.assertEqual(plan["reason"], "deadline_passed")

    def test_manual_force_works_without_a_deadline(self) -> None:
        plan = deadline_refresh_plan({}, self.at("2026-08-21T10:00:00"), True)
        self.assertTrue(plan["should_refresh"])
        self.assertEqual(plan["reason"], "manual_force")


if __name__ == "__main__":
    unittest.main()
